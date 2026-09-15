#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data/prediction.json + data/latest.json 注入 template.html，生成 dashboard.html"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
TPL = ROOT / "scripts" / "template.html"
OUT = ROOT / "dashboard.html"
CST = timezone(timedelta(hours=8))


def inline_echarts(html: str) -> str:
    """
    把 ECharts 库内联进 HTML，使工作台成为**完全离线的单文件**。
    否则一旦 CDN 不可达（内网、无网、被墙），所有图表都会空白。
    若本地库文件不存在，则保留模板里的 CDN <script> 作为回退。
    """
    lib_file = ASSETS / "echarts.min.js"
    if not lib_file.exists():
        print("提示：未找到 assets/echarts.min.js，保留 CDN 引用（需要联网才能看图）")
        return html
    lib = lib_file.read_text(encoding="utf-8")
    if "</script>" in lib:                      # 保险：转换可能提前闭合的标签
        lib = lib.replace("</script>", "<\\/script>")
    block = f"<script>{lib}</script>"
    new, n = re.subn(r"<!--ECHARTS_START-->.*?<!--ECHARTS_END-->", lambda _: block,
                     html, flags=re.S)
    if n == 0:
        print("警告：模板中未找到 ECHARTS 标记，跳过内联")
        return html
    print(f"已内联 ECharts（{len(lib)/1024:.0f} KB），工作台可离线打开")
    return new


def main() -> int:
    pred_f = DATA / "prediction.json"
    if not pred_f.exists():
        print("缺少 data/prediction.json，请先运行 scripts/model.py")
        return 1

    payload = json.loads(pred_f.read_text(encoding="utf-8"))

    # 合并实时快照（若采集过）
    snap_f = DATA / "latest.json"
    if snap_f.exists():
        payload["realtime"] = json.loads(snap_f.read_text(encoding="utf-8")).get("realtime", {})

    html = TPL.read_text(encoding="utf-8")
    html = inline_echarts(html)
    # 用 replace 而非 format，避免 CSS/JS 中的花括号被误解析
    html = html.replace("/*__DATA__*/{}", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    OUT.write_text(html, encoding="utf-8")

    size = OUT.stat().st_size / 1024
    print(f"已生成 {OUT}  ({size:.0f} KB)")
    print(f"  预测: {payload['prediction']['last_price']} -> {payload['prediction']['pred_price']}"
          f"  ({payload['prediction']['pred_change_pct']:+.2f}%)"
          f"  上涨概率 {payload['prediction']['prob_up']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
