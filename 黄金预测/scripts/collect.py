#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金价格 + 影响因素 每日采集脚本
================================
数据源（全部免费、无需 API Key）：
  1. 新浪财经国际期货日线  -> 黄金(GC) 白银(SI) 原油(CL) 铜(HG) 十年历史
  2. 新浪财经实时行情      -> 伦敦金现货(hf_XAU) COMEX黄金(hf_GC) 上海金T+D(gds_AUTD)
  3. FRED (圣路易斯联储)   -> 实际利率 / 美元指数 / VIX / 通胀预期 / 收益率 / 信用利差

产物：
  data/gold.db        SQLite 数据库（唯一事实来源，增量更新）
  data/market.csv     宽表（日期 x 全部指标），供建模直接使用
  data/latest.json    最新快照（实时价 + 最近一日因子）
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB = DATA / "gold.db"
CST = timezone(timedelta(hours=8))

# 关键坑：FRED 的 WAF 会拦截「浏览器型」User-Agent（Mozilla/...）导致请求挂到超时，
# 但放行 curl / python-requests 型 UA。因此两个数据源必须用不同的 Session。
UA_BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122 Safari/537.36")

# 新浪财经：需要浏览器 UA + Referer
S = requests.Session()
S.headers.update({"User-Agent": UA_BROWSER})

# FRED：保持 requests 默认 UA（"python-requests/x.y.z"），勿改成 Mozilla
F = requests.Session()

_adapter = requests.adapters.HTTPAdapter(max_retries=3)
S.mount("https://", _adapter)
F.mount("https://", _adapter)

# ----------------------------------------------------------------------------
# 配置：国际期货品种（新浪）
# ----------------------------------------------------------------------------
FUTURES = {
    "GC": "黄金COMEX",
    "SI": "白银COMEX",
    "CL": "WTI原油",
    "HG": "铜COMEX",
}

# ----------------------------------------------------------------------------
# 配置：FRED 宏观因子
#   cat 用于前端分组；dir 是该因子对金价的理论方向（前端标注用）
# ----------------------------------------------------------------------------
FRED_SERIES = {
    "DFII10":     ("10年期实际利率(TIPS)",      "利率", -1),
    "DGS10":      ("10年期美债收益率",           "利率", -1),
    "DGS2":       ("2年期美债收益率",            "利率", -1),
    "T10Y2Y":     ("10Y-2Y期限利差",             "利率", +1),
    "FEDFUNDS":   ("联邦基金有效利率",           "利率", -1),
    "DTWEXBGS":   ("美元指数(贸易加权)",         "汇率", -1),
    "T10YIE":     ("10年期通胀预期",             "通胀", +1),
    "CPIAUCSL":   ("美国CPI指数",                "通胀", +1),
    "DCOILWTICO": ("WTI原油(FRED)",              "商品", +1),
    "SP500":      ("标普500指数",                "风险", +1),
    "VIXCLS":     ("VIX恐慌指数",                "风险", +1),
    "BAMLH0A0HYM2": ("高收益债信用利差",         "风险", -1),
}

# 实时行情代码
RT_CODES = {
    "hf_XAU":   "伦敦金现货",
    "hf_GC":    "COMEX黄金",
    "gds_AUTD": "上海金T+D",
}


def log(msg: str) -> None:
    print(f"[{datetime.now(CST):%H:%M:%S}] {msg}", flush=True)


# ----------------------------------------------------------------------------
# 数据库
# ----------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS futures_daily (
        symbol TEXT NOT NULL, date TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL,
        PRIMARY KEY (symbol, date)
    );
    CREATE TABLE IF NOT EXISTS macro_daily (
        series TEXT NOT NULL, date TEXT NOT NULL, value REAL,
        PRIMARY KEY (series, date)
    );
    CREATE TABLE IF NOT EXISTS realtime (
        ts TEXT NOT NULL, code TEXT NOT NULL, price REAL,
        open REAL, prev_close REAL, high REAL, low REAL,
        PRIMARY KEY (ts, code)
    );
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY, value TEXT
    );
    """)


# ----------------------------------------------------------------------------
# 采集：新浪国际期货日线
# ----------------------------------------------------------------------------
def fetch_sina_futures(symbol: str) -> pd.DataFrame:
    url = (
        "https://stock.finance.sina.com.cn/futures/api/jsonp.php/"
        f"var%20_{symbol}=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={symbol}"
    )
    r = S.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=30)
    r.raise_for_status()
    m = re.search(r"=\((\[.*\])\)", r.text, re.S)
    if not m:
        raise RuntimeError(f"新浪 {symbol} 返回格式异常")
    rows = json.loads(m.group(1))
    df = pd.DataFrame(rows)
    df = df[["date", "open", "high", "low", "close"]].copy()
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = df["date"].astype(str)
    return df.dropna(subset=["close"])


# ----------------------------------------------------------------------------
# 采集：新浪实时行情
# ----------------------------------------------------------------------------
def fetch_sina_realtime() -> dict:
    codes = ",".join(RT_CODES)
    r = S.get(
        f"https://hq.sinajs.cn/list={codes}",
        headers={"Referer": "https://finance.sina.com.cn"},
        timeout=20,
    )
    r.encoding = "gbk"
    out = {}
    for line in r.text.strip().split("\n"):
        m = re.match(r'var hq_str_(\w+)="(.*)";', line.strip())
        if not m:
            continue
        code, payload = m.group(1), m.group(2)
        f = payload.split(",")
        if len(f) < 8:
            continue
        try:
            out[code] = {
                "name": RT_CODES.get(code, code),
                # hf_* 与 gds_* 字段顺序不同，统一取第 1 个字段为最新价
                "price": float(f[0]) if f[0] else None,
                "open": float(f[2]) if f[2] else None,
                "prev_close": float(f[7]) if len(f) > 7 and f[7] else None,
                "high": float(f[4]) if f[4] else None,
                "low": float(f[5]) if f[5] else None,
            }
        except (ValueError, IndexError):
            continue
    return out


def fetch_spot_gold() -> float | None:
    """无 key 的现货金兜底源"""
    try:
        r = S.get("https://api.gold-api.com/price/XAU", timeout=15)
        return float(r.json()["price"])
    except Exception:
        return None


# ----------------------------------------------------------------------------
# 采集：FRED
# ----------------------------------------------------------------------------
def fetch_fred(series: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    r = F.get(url, timeout=25)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["date"] = df["date"].astype(str)
    return df.dropna(subset=["value"])


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def main() -> int:
    conn = sqlite3.connect(DB)
    init_db(conn)
    errors: list[str] = []

    # 1) 期货日线
    for sym in FUTURES:
        try:
            df = fetch_sina_futures(sym)
            conn.executemany(
                "INSERT OR REPLACE INTO futures_daily VALUES (?,?,?,?,?,?)",
                [(sym, r.date, r.open, r.high, r.low, r.close) for r in df.itertuples()],
            )
            conn.commit()
            log(f"期货 {sym:<3} {FUTURES[sym]:<10} {len(df):>5} 条  最新 {df['date'].iloc[-1]}  {df['close'].iloc[-1]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"futures:{sym}:{e}")
            log(f"!! 期货 {sym} 失败: {e}")
        time.sleep(0.4)

    # 2) FRED 宏观
    for sid in FRED_SERIES:
        try:
            df = fetch_fred(sid)
            conn.executemany(
                "INSERT OR REPLACE INTO macro_daily VALUES (?,?,?)",
                [(sid, r.date, r.value) for r in df.itertuples()],
            )
            conn.commit()
            log(f"宏观 {sid:<12} {FRED_SERIES[sid][0]:<22} {len(df):>6} 条  最新 {df['date'].iloc[-1]}  {df['value'].iloc[-1]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"fred:{sid}:{e}")
            log(f"!! FRED {sid} 失败: {e}")
        time.sleep(0.3)

    # 3) 实时快照
    rt: dict = {}
    try:
        rt = fetch_sina_realtime()
        ts = datetime.now(CST).isoformat(timespec="seconds")
        conn.executemany(
            "INSERT OR REPLACE INTO realtime VALUES (?,?,?,?,?,?,?)",
            [
                (ts, c, v["price"], v["open"], v["prev_close"], v["high"], v["low"])
                for c, v in rt.items()
            ],
        )
        conn.commit()
        log("实时 " + " | ".join(f"{v['name']} {v['price']}" for v in rt.values()))
    except Exception as e:  # noqa: BLE001
        errors.append(f"realtime:{e}")
        log(f"!! 实时行情失败: {e}")

    if "hf_XAU" not in rt:
        spot = fetch_spot_gold()
        if spot:
            rt["XAU_spot_fallback"] = {"name": "现货黄金(兜底源)", "price": spot}
            log(f"实时 兜底现货金 {spot}")

    # 4) 导出宽表
    fut = pd.read_sql("SELECT * FROM futures_daily", conn)
    mac = pd.read_sql("SELECT * FROM macro_daily", conn)
    wide = fut.pivot(index="date", columns="symbol", values="close").add_prefix("px_")
    macw = mac.pivot(index="date", columns="series", values="value")
    wide = wide.join(macw, how="outer").sort_index()
    wide.index.name = "date"
    wide.to_csv(DATA / "market.csv")
    log(f"导出 market.csv  {wide.shape[0]} 行 x {wide.shape[1]} 列  ({wide.index.min()} -> {wide.index.max()})")

    # 5) 最新快照 json
    snap = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "realtime": rt,
        "last_market_date": str(wide.index.max()),
        "rows": int(wide.shape[0]),
        "errors": errors,
    }
    (DATA / "latest.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.execute(
        "INSERT OR REPLACE INTO meta VALUES ('last_collect', ?)",
        (snap["generated_at"],),
    )
    conn.commit()
    conn.close()

    log(f"完成。成功 {len(FUTURES) + len(FRED_SERIES) - len(errors)} 项，失败 {len(errors)} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
