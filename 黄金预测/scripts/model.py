#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金次日走势预测模型
====================
设计要点（吸取 GitHub 同类项目的经验教训）：
  1. 多个开源项目实测发现「堆外部因子 + LSTM」在有限样本上严重过拟合，
     故本模型主线用「强正则化线性模型 + 逻辑回归方向模型」，稳定且可解释。
  2. 严格处理数据发布滞后：FRED 各序列按其真实发布延迟回移，
     避免用「未来才知道的数据」预测过去（look-ahead bias）。
  3. 只使用「因子的变化量」而非绝对水平，避免非平稳趋势造成的伪回归。
  4. 走前式回测（walk-forward），滚动重训，指标诚实呈现。

产物：
  data/features.csv     特征矩阵（含目标列）
  data/prediction.json  明日预测结果（点位/概率/区间/因子贡献/回测指标）
"""
from __future__ import annotations

import json
import sqlite3
import sys
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "gold.db"
CST = timezone(timedelta(hours=8))

# 目标：预测的是「次日」还是「未来N日累计」
HORIZON = 1
# 走前式回测的最小训练窗口
MIN_TRAIN = 750

# ---------------------------------------------------------------------------
# FRED 序列的真实发布滞后（自然日）。0 = 当日收盘后即可得
# ---------------------------------------------------------------------------
FRED_LAG = {
    "DFII10": 0, "DGS10": 0, "DGS2": 0, "T10Y2Y": 0, "VIXCLS": 0,
    "DCOILWTICO": 0, "SP500": 0, "BAMLH0A0HYM2": 0,
    "T10YIE": 1,
    "DTWEXBGS": 7,      # 贸易加权美元指数，周度发布
    "CPIAUCSL": 30,     # CPI 月度，留足滞后
    "FEDFUNDS": 30,     # 月度均值
}

# 因子中文名 + 对金价的理论方向，用于前端展示
# 注意：FRED 的 BAMLH0A0HYM2（高收益债信用利差）历史仅追溯至 2023-09，
# 纳入后会令可用样本从 2530 天骤降至 606 天。用 80% 的训练数据换一个边际因子
# 得不偿失（GitHub 同类项目也实测到"堆因子反而变差"），因此该序列仍在采集入库，
# 但**不进入模型特征**。若后续要启用，把下面这行加回即可：
#   "d_credit_5d": ("信用利差 5日变化", -1, "风险"),
FACTOR_META = {
    "d_realyield_5d":  ("实际利率 5日变化",        -1, "利率"),
    "d_dxy_5d":        ("美元指数 5日变化",        -1, "汇率"),
    "d_vix_5d":        ("VIX 5日变化",             +1, "风险"),
    "d_breakeven_5d":  ("通胀预期 5日变化",        +1, "通胀"),
    "d_oil_5d":        ("原油 5日变化",            +1, "商品"),
    "d_spx_5d":        ("标普500 5日变化",         +1, "风险"),
    "term_spread":     ("10Y-2Y 期限利差",         +1, "利率"),
    "realyield_level": ("实际利率 水平",           -1, "利率"),
    "gold_silver":     ("金银比 水平",             -1, "商品"),
    "d_gold_silver_5d":("金银比 5日变化",          -1, "商品"),
    "gold_copper":     ("金铜比 水平",             -1, "商品"),
    "mom_1d":          ("1日动量",                 +1, "动量"),
    "mom_5d":          ("5日动量",                 +1, "动量"),
    "mom_20d":         ("20日动量",                +1, "动量"),
    "ma_gap_20":       ("偏离20日均线",            -1, "动量"),
    "ma_gap_60":       ("偏离60日均线",            -1, "动量"),
    "vol_20d":         ("20日波动率",              -1, "动量"),
    "rsi_14":          ("RSI(14)",                 -1, "动量"),
    "dist_high_20":    ("距20日高点",              +1, "动量"),
    "dxy_level":       ("美元指数 水平",           -1, "汇率"),
}


def log(m: str) -> None:
    print(m, flush=True)


# ---------------------------------------------------------------------------
# 读音数据
# ---------------------------------------------------------------------------
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = sqlite3.connect(DB)
    fut = pd.read_sql("SELECT * FROM futures_daily", conn)
    mac = pd.read_sql("SELECT * FROM macro_daily", conn)
    conn.close()
    fut["date"] = pd.to_datetime(fut["date"])
    mac["date"] = pd.to_datetime(mac["date"])
    return fut, mac


def asof(series: pd.Series, target: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    """
    把某因子序列按发布滞后对齐到目标日期（只使用当时已知的值）。

    关键实现细节（踩过的坑）：
      reindex(method="ffill") 只填充「目标索引里缺失的标签」，**不会**填充源序列
      自身已有的 NaN。而 FRED 在「美国休市但黄金仍交易」的日子（元旦、耶稣受难日、
      哥伦布日、感恩节…）根本没有数据，pivot 后就是 NaN，直接 reindex 会留下空洞，
      导致 5 日差分变 NaN、滚动统计无法计算。
      因此必须先 dropna()，再在「并集索引」上 ffill，最后取目标日期。
    """
    s = series.dropna().astype(float)
    if s.empty:
        return pd.Series(np.nan, index=target)
    s.index = s.index + pd.Timedelta(days=lag_days)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    union = s.index.union(target)
    return s.reindex(union).ffill().reindex(target)


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------
def build_features(fut: pd.DataFrame, mac: pd.DataFrame) -> pd.DataFrame:
    px = fut.pivot(index="date", columns="symbol", values="close").sort_index()
    gold = px["GC"].dropna()
    idx = gold.index  # 以黄金交易日为基准日历

    f = pd.DataFrame(index=idx)
    f["gold"] = gold

    # --- 价格衍生特征（当日收盘即可知，无滞后） ---
    f["mom_1d"] = gold.pct_change(1)
    f["mom_5d"] = gold.pct_change(5)
    f["mom_20d"] = gold.pct_change(20)
    f["ma_gap_20"] = gold / gold.rolling(20).mean() - 1
    f["ma_gap_60"] = gold / gold.rolling(60).mean() - 1
    f["vol_20d"] = gold.pct_change().rolling(20).std()

    # RSI(14)
    d = gold.diff()
    up = d.clip(lower=0).rolling(14).mean()
    dn = (-d.clip(upper=0)).rolling(14).mean()
    f["rsi_14"] = (100 - 100 / (1 + up / dn.replace(0, np.nan))) / 100
    f["dist_high_20"] = gold / gold.rolling(20).max() - 1

    # --- 跨品种比价 ---
    silver, copper = px["SI"], px["HG"]
    f["gold_silver"] = np.log(gold / silver)
    f["gold_copper"] = np.log(gold / copper)
    f["d_gold_silver_5d"] = f["gold_silver"].diff(5)

    # --- 宏观因子：按发布滞后对齐，再取变化量 ---
    macw = mac.pivot(index="date", columns="series", values="value").sort_index()
    aligned = {}
    for sid in macw.columns:
        aligned[sid] = asof(macw[sid], idx, FRED_LAG.get(sid, 1))
    A = pd.DataFrame(aligned, index=idx)

    def chg(col: str, n: int = 5) -> pd.Series:
        s = A[col]
        # 对利率类用「绝对变化」（单位：百分点），对指数类用「百分比变化」
        if col in ("DFII10", "DGS10", "DGS2", "T10Y2Y", "T10YIE", "VIXCLS", "BAMLH0A0HYM2"):
            return s.diff(n)
        return s.pct_change(n)

    f["d_realyield_5d"] = chg("DFII10")
    f["realyield_level"] = A["DFII10"] / 100
    f["d_dxy_5d"] = chg("DTWEXBGS")
    f["dxy_level"] = np.log(A["DTWEXBGS"])
    f["d_vix_5d"] = chg("VIXCLS")
    f["d_breakeven_5d"] = chg("T10YIE")
    f["d_oil_5d"] = chg("DCOILWTICO")
    f["d_spx_5d"] = chg("SP500")
    f["d_credit_5d"] = chg("BAMLH0A0HYM2")
    f["term_spread"] = A["T10Y2Y"] / 100

    # --- 目标：次日对数收益 ---
    f["target_ret"] = np.log(gold.shift(-HORIZON) / gold)
    f["target_price"] = gold.shift(-HORIZON)
    f["target_dir"] = (f["target_ret"] > 0).astype(int)

    return f


FEATURES = list(FACTOR_META.keys())


# ---------------------------------------------------------------------------
# 走前式回测
# ---------------------------------------------------------------------------
def walk_forward(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """滚动重训，逐日预测，返回预测序列与汇总指标"""
    ok = f.dropna(subset=FEATURES + ["target_ret"]).copy()
    n = len(ok)
    # 自适应训练窗口：至少 400 天，且不少于总样本的 30%
    min_train = max(400, min(MIN_TRAIN, int(n * 0.3)))
    step = 21  # 每月重训一次
    model_r = model_c = None
    rows: list[dict] = []

    for i in range(min_train, n):
        if (i - min_train) % step == 0:
            tr = ok.iloc[:i]
            model_r = make_pipeline(
                StandardScaler(),
                RidgeCV(alphas=np.logspace(-1, 3, 30)),
            ).fit(tr[FEATURES], tr["target_ret"])

            model_c = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.05, max_iter=2000, solver="lbfgs"),
            ).fit(tr[FEATURES], tr["target_dir"])

        x = ok[FEATURES].iloc[[i]]
        rows.append({
            "date": ok.index[i],
            "actual_price": ok["gold"].iloc[i],
            "actual_next": ok["target_price"].iloc[i],
            "pred_ret": float(model_r.predict(x)[0]),
            "prob_up": float(model_c.predict_proba(x)[0][1]),
        })

    if not rows:
        raise RuntimeError(f"样本不足，无法回测（有效样本 {n}）")
    wf = pd.DataFrame(rows).set_index("date")
    wf["pred_price"] = wf["actual_price"] * np.exp(wf["pred_ret"])
    wf["hit"] = ((wf["pred_ret"] > 0) == (wf["actual_next"] > wf["actual_price"])).astype(int)
    wf["err_naive"] = (wf["actual_next"] - wf["actual_price"]).abs()
    wf["err_model"] = (wf["actual_next"] - wf["pred_price"]).abs()

    # 残差标准差 -> 预测区间
    resid = wf["pred_ret"] - np.log(wf["actual_next"] / wf["actual_price"])
    sigma = float(resid.std())

    metrics = {
        "samples": int(len(wf)),
        "start": str(wf.index.min().date()),
        "end": str(wf.index.max().date()),
        "dir_accuracy": round(float(wf["hit"].mean()), 4),
        "mae_model": round(float(wf["err_model"].mean()), 3),
        "mae_naive": round(float(wf["err_naive"].mean()), 3),
        "rmse_ret": round(float(np.sqrt((resid ** 2).mean())), 5),
        "ic": round(float(wf["pred_ret"].corr(np.log(wf["actual_next"] / wf["actual_price"]))), 4),
        "auc": round(float(roc_auc_score(
            (wf["actual_next"] > wf["actual_price"]).astype(int), wf["prob_up"]
        )), 4),
        "resid_sigma": sigma,
        # 概率分层命中率：高置信度预测是否更准
        "conf_buckets": [],
    }

    # 分位数分层：把 prob_up 分 5 档，看方向命中率是否单调
    wf["bucket"] = pd.qcut(wf["prob_up"], 5, labels=False, duplicates="drop")
    for b, g in wf.groupby("bucket"):
        metrics["conf_buckets"].append({
            "bucket": int(b),
            "n": int(len(g)),
            "prob_mean": round(float(g["prob_up"].mean()), 3),
            "hit": round(float(g["hit"].mean()), 3),
        })
    return wf, metrics


# ---------------------------------------------------------------------------
# 最终模型：全样本训练 + 明日预测
# ---------------------------------------------------------------------------
def fit_final(f: pd.DataFrame) -> dict:
    ok = f.dropna(subset=FEATURES + ["target_ret"]).copy()
    X, y = ok[FEATURES], ok["target_ret"]
    yd = ok["target_dir"]

    sc = StandardScaler().fit(X)
    ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-1, 3, 30))).fit(X, y)
    clf = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.05, max_iter=2000, solver="lbfgs")
    ).fit(X, yd)
    gbr = make_pipeline(
        StandardScaler(),
        GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.03,
                                  subsample=0.8, random_state=42),
    ).fit(X, y)

    # 最新可用特征行（最后一个数据完整的交易日）
    live = f.dropna(subset=FEATURES).iloc[-1]
    xl = live[FEATURES].to_frame().T
    as_of = f.dropna(subset=FEATURES).index[-1]

    pred_ret = float(ridge.predict(xl)[0])
    prob_up = float(clf.predict_proba(xl)[0][1])
    gbr_ret = float(gbr.predict(xl)[0])

    # --- 因子贡献分解（标准化系数 x 标准化因子值）---
    coefs = ridge.named_steps["ridgecv"].coef_
    z = sc.transform(xl)[0]
    contrib = coefs * z
    order = np.argsort(-np.abs(contrib))
    contribs = []
    for i in order:
        name = FEATURES[i]
        meta = FACTOR_META.get(name, (name, 0, "其他"))
        contribs.append({
            "key": name,
            "name": meta[0],
            "group": meta[2],
            "expect_dir": meta[1],
            "value": round(float(live[name]), 6),
            "contrib_bp": round(float(contrib[i] * 1e4), 2),   # 对次日收益的贡献（基点）
            "coef": round(float(coefs[i]), 6),
        })

    # --- 预测价位 ---
    last_price = float(f["gold"].dropna().iloc[-1])
    last_date = f["gold"].dropna().index[-1]
    pred_price = last_price * np.exp(pred_ret)

    return {
        "as_of": str(as_of.date()),
        "last_price_date": str(last_date.date()),
        "last_price": round(last_price, 2),
        "pred_ret": pred_ret,
        "pred_price": round(pred_price, 2),
        "pred_change_abs": round(pred_price - last_price, 2),
        "pred_change_pct": round((np.exp(pred_ret) - 1) * 100, 3),
        "prob_up": round(prob_up, 4),
        "gbr_pred_price": round(last_price * np.exp(gbr_ret), 2),
        "contribs": contribs,
    }


# ---------------------------------------------------------------------------
def main() -> int:
    fut, mac = load()
    log(f"读取 期货 {len(fut)} 行 / 宏观 {len(mac)} 行")

    f = build_features(fut, mac)
    f.to_csv(DATA / "features.csv")
    log(f"特征矩阵 {f.shape}  有效样本 {f.dropna(subset=FEATURES+['target_ret']).shape[0]}")

    log("走前式回测中 ...")
    wf, metrics = walk_forward(f)
    wf.to_csv(DATA / "backtest.csv")
    log(f"  样本 {metrics['samples']} 日 ({metrics['start']} ~ {metrics['end']})")
    log(f"  方向准确率 {metrics['dir_accuracy']:.1%}  |  AUC {metrics['auc']:.3f}  |  IC {metrics['ic']:.3f}")
    log(f"  模型MAE {metrics['mae_model']}  vs  朴素MAE {metrics['mae_naive']}")

    pred = fit_final(f)
    log(f"明日预测  {pred['last_price']} -> {pred['pred_price']}  "
        f"({pred['pred_change_pct']:+.2f}%)  上涨概率 {pred['prob_up']:.1%}")

    # 历史价格序列（最近 1800 个交易日，供前端画图）
    hist = f[["gold"]].dropna().tail(1800)
    history = [
        {"date": d.strftime("%Y-%m-%d"), "price": round(float(v), 2)}
        for d, v in hist["gold"].items()
    ]

    # 回测曲线（最近 400 日）
    bt = wf.tail(400)
    backtest_curve = [
        {"date": d.strftime("%Y-%m-%d"),
         "actual": round(float(r.actual_next), 2),
         "pred": round(float(r.pred_price), 2),
         "prob": round(float(r.prob_up), 4),
         "hit": int(r.hit)}
        for d, r in bt.iterrows()
    ]

    # 因子面板：最近 120 日的关键因子走势
    panel = f[FEATURES].dropna().tail(120)
    factor_series = [
        {"key": k, "name": FACTOR_META[k][0], "group": FACTOR_META[k][2],
         "data": [round(float(v), 6) if pd.notna(v) else None for v in panel[k]]}
        for k in FEATURES
    ]
    panel_dates = [d.strftime("%Y-%m-%d") for d in panel.index]

    out = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "horizon_days": HORIZON,
        "prediction": pred,
        "metrics": metrics,
        "history": history,
        "backtest_curve": backtest_curve,
        "factor_series": factor_series,
        "panel_dates": panel_dates,
    }
    (DATA / "prediction.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log("已写出 data/prediction.json")

    log("\n===== 因子贡献 Top 8（对明日收益的贡献，基点）=====")
    for c in pred["contribs"][:8]:
        log(f"  {c['name']:<22} {c['contrib_bp']:>+8.2f} bp   (当前值 {c['value']:+.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
