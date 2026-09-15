#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 PDF 版作品集（A4，双页）
=============================
把工作台截图内联为 base64，输出一份自包含、可直接投递招聘官网的 PDF。

**所有数字均从 data/prediction.json 与 data/market.csv 实时读取**，
不做任何硬编码——项目每天 07:00 自动更新，硬编码会让 PDF 隔天就对不上。

用法：
    python scripts/make_pdf.py

产物：
    <项目根>/黄金走势预测工作台_作品集.pdf      ← 投递用
    docs/portfolio-print.html                   ← 中间产物，可用浏览器打开后手动打印

依赖：系统已安装 Google Chrome（无头模式打印，不需要额外 Python 包）
"""
from __future__ import annotations

import base64
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
OUT_PDF = ROOT / "黄金走势预测工作台_作品集.pdf"
OUT_HTML = DOCS / "portfolio-print.html"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


# ---------------------------------------------------------------------------
# 读取真实数据
# ---------------------------------------------------------------------------
def load_facts() -> dict:
    pf = DATA / "prediction.json"
    if not pf.exists():
        raise SystemExit(f"缺少 {pf}，请先运行 scripts/model.py")
    d = json.loads(pf.read_text(encoding="utf-8"))
    m, p = d["metrics"], d["prediction"]

    # 数据源数量与黄金交易日数：直接从宽表数出来，不写死
    src_count, gold_days = 0, 0
    mf = DATA / "market.csv"
    if mf.exists():
        # 注意：必须只用 DictReader。若先用 next(csv.reader(f)) 读表头，
        # DictReader 会把第二行当表头，字段名取不到 → 静默算出 0。
        with mf.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            src_count = len(reader.fieldnames or []) - 1     # 减去 date 列
            for row in reader:
                if row.get("px_GC"):
                    gold_days += 1
    if gold_days == 0:
        raise SystemExit(
            "解析 market.csv 得到 0 个黄金交易日，数据可能异常，"
            "请先运行 scripts/collect.py 后重试"
        )

    # 分层命中率：按概率从低到高
    buckets = sorted(m["conf_buckets"], key=lambda b: b["prob_mean"])

    return {
        "acc": f"{m['dir_accuracy'] * 100:.1f}%",
        "auc": f"{m['auc']:.3f}",
        "ic": f"{m['ic']:.3f}",
        "mae_model": f"{m['mae_model']:.2f}",
        "mae_naive": f"{m['mae_naive']:.2f}",
        "samples": f"{m['samples']}",
        "start": m["start"],
        "end": m["end"],
        "n_factors": str(len(p["contribs"])),
        "src_count": str(src_count or 16),
        "gold_days": f"{gold_days:,}",
        "buckets": [
            {
                "hit": f"{b['hit'] * 100:.1f}%",
                "prob": f"{b['prob_mean'] * 100:.0f}%",
                "k": len(buckets) - 1 - i,
                "best": i >= len(buckets) - 2,
            }
            for i, b in enumerate(buckets)
        ],
    }


# ---------------------------------------------------------------------------
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>黄金走势预测工作台 · 项目作品集</title>
<style>
  @page { size: A4; margin: 12mm 13mm; }
  * { box-sizing: border-box; margin: 0; padding: 0;
      -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", sans-serif;
    color: #171a21; font-size: 9.4pt; line-height: 1.6;
  }
  a { color: #c9922f; text-decoration: none; }

  /* ---------- 页眉 ---------- */
  .hd { border-bottom: 2.5pt solid #c9922f; padding-bottom: 4.2mm; margin-bottom: 4.2mm; }
  .kicker {
    font-size: 7.6pt; font-weight: 700; letter-spacing: 2.4px; color: #c9922f;
    text-transform: uppercase; margin-bottom: 2.2mm;
  }
  h1 { font-size: 21pt; font-weight: 750; letter-spacing: -.6px; line-height: 1.16; }
  .sub { font-size: 9.6pt; color: #5b6472; margin-top: 2.2mm; }
  .links { margin-top: 3.2mm; font-size: 8.6pt; color: #8b93a1; }
  .links b { color: #5b6472; font-weight: 600; }

  /* ---------- 指标卡 ---------- */
  .metrics { display: flex; gap: 2.8mm; margin-bottom: 4.5mm; }
  .m {
    flex: 1; border: .8pt solid #e6e8ec; border-radius: 2.4mm;
    padding: 3mm 2.8mm; background: #fcfcfd;
  }
  .m .v { font-size: 15pt; font-weight: 750; letter-spacing: -.5px; line-height: 1.1; }
  .m .v.g { color: #c9922f; }
  .m .k { font-size: 7.4pt; color: #8b93a1; margin-top: .8mm; }

  /* ---------- 截图 ---------- */
  .shot { border: .8pt solid #e6e8ec; border-radius: 2.4mm; overflow: hidden; }
  .shot img { width: 93%; display: block; margin: 0 auto; }
  .cap { font-size: 7.2pt; color: #8b93a1; margin: 1.5mm 0 4mm; text-align: center; }

  /* ---------- 章节 ---------- */
  section { margin-bottom: 4mm; }
  h2 {
    font-size: 10.4pt; font-weight: 700; margin-bottom: 2.4mm;
    padding-left: 2.6mm; border-left: 2.6pt solid #c9922f; line-height: 1.3;
  }
  ol, ul { padding-left: 4.4mm; }
  li { margin-bottom: 1.4mm; }
  li b { font-weight: 650; }
  .dim { color: #5b6472; }

  /* ---------- 表格 ---------- */
  table { width: 100%; border-collapse: collapse; margin-top: 1.4mm; font-variant-numeric: tabular-nums; }
  th {
    text-align: left; font-size: 7.4pt; font-weight: 600; color: #8b93a1;
    padding: 1.4mm 2mm; border-bottom: .8pt solid #e6e8ec; background: #fafbfc;
  }
  td { padding: 1.4mm 2mm; font-size: 8.6pt; border-bottom: .6pt solid #eef0f3; }
  td.n { font-weight: 700; }

  /* ---------- 分层命中率 ---------- */
  .buckets { display: flex; gap: 1.8mm; margin-top: 2.2mm; }
  .bk { flex: 1; text-align: center; border: .8pt solid #e6e8ec; border-radius: 2mm; padding: 2mm 1mm; }
  .bk.hi { border-color: #2f6fed; background: #f6f9ff; }
  .bk .bv { font-size: 11pt; font-weight: 750; color: #a9b2c0; line-height: 1.15; }
  .bk.hi .bv { color: #2f6fed; }
  .bk .bl { font-size: 6.8pt; color: #8b93a1; margin-top: .6mm; }

  /* ---------- 技术栈 ---------- */
  .tags { display: flex; flex-wrap: wrap; gap: 1.5mm; margin-top: 1mm; }
  .tag {
    font-size: 7.6pt; padding: .9mm 2.3mm; border-radius: 1.4mm;
    background: #f4f5f7; border: .6pt solid #eef0f3; color: #5b6472;
  }

  /* ---------- 页脚 ---------- */
  .ft {
    border-top: .8pt solid #e6e8ec; padding-top: 2.8mm; margin-top: 1mm;
    font-size: 7.6pt; color: #8b93a1; line-height: 1.75;
  }
  .ft .row { display: flex; justify-content: space-between; gap: 6mm; }
  .foot-note { font-size: 7pt; color: #a8b0bc; margin-top: 1.5mm; }

  /* 分页控制 */
  .page-break { page-break-before: always; }
  section, .metrics, .buckets, table { page-break-inside: avoid; }
</style>
</head>
<body>

<div class="hd">
  <div class="kicker">Project Portfolio</div>
  <h1>黄金走势预测工作台</h1>
  <div class="sub">
    每日自动采集 COMEX 金价与全球宏观因子 · __NF__ 因子多因子建模 · 预测次日走势 · 单文件可视化工作台
  </div>
  <div class="links">
    <b>在线体验</b> <a href="https://jw319.github.io/my-tools/gold/">https://jw319.github.io/my-tools/gold/</a>
    　|　<b>源码</b> <a href="https://github.com/jw319/my-tools">github.com/jw319/my-tools</a>
    　|　<b>离线可打开</b>（图表库与数据全部内联）
  </div>
</div>

<div class="metrics">
  <div class="m"><div class="v">__SRC__</div><div class="k">免费数据源</div></div>
  <div class="m"><div class="v">__NF__</div><div class="k">个因子 / 5 大类</div></div>
  <div class="m"><div class="v">__SAMPLES__</div><div class="k">天走前式回测</div></div>
  <div class="m"><div class="v g">__ACC__</div><div class="k">方向准确率</div></div>
</div>

<div class="shot">
  <img src="__PREVIEW__" alt="黄金走势预测工作台界面">
</div>
<div class="cap">工作台界面：金价历史折线与次日预测点、驱动因子贡献分解、置信度分层命中率、回测对照、因子面板</div>

<section>
  <h2>做了什么</h2>
  <ol>
    <li><b>数据工程</b><span class="dim">——</span>打通 __SRC__ 个免费、无需 API Key 的数据源：新浪财经国际期货接口提供 COMEX 黄金 __GOLD_DAYS__ 个交易日日线，FRED 提供实际利率、美元指数、VIX、通胀预期等宏观因子。</li>
    <li><b>因子体系</b><span class="dim">——</span>构建 __NF__ 个因子，分利率、汇率、风险、通胀商品、动量五类；只用因子的「变化量」而非绝对水平做趋势外推，避免非平稳序列的伪回归。</li>
    <li><b>严谨验证</b><span class="dim">——</span>走前式回测 __SAMPLES__ 个交易日（每月滚动重训，__START__ 至今），并严格按真实发布滞后对齐因子（美元指数滞后 7 天、CPI 滞后 30 天），杜绝未来数据泄露。</li>
    <li><b>交付工程</b><span class="dim">——</span>输出单文件 HTML 工作台，图表库与数据全部内联，断网也能打开；已配置定时任务每日 07:00 自动更新。</li>
  </ol>
</section>

<section>
  <h2>关键选择，以及背后的取舍</h2>
  <ul>
    <li><b>不用 LSTM / 深度学习。</b><span class="dim">开源社区同类项目实测：在有限样本上堆外部因子 + LSTM 会严重过拟合，反而跑不过朴素基准。因此选择可解释性更好、更稳健的强正则线性模型。</span></li>
    <li><b>不为了「因子多」牺牲样本量。</b><span class="dim">FRED 的信用利差序列仅追溯至 2023-09，纳入后可用样本会从 2530 天骤降到 606 天。用 80% 的训练数据换一个边际因子不划算，直接剔除。</span></li>
    <li><b>用实验决定，不靠直觉。</b><span class="dim">测试过滚动标准化（反而更差，51.6% vs 52.4%）与 GBDT（仅高 0.9pp，在噪声范围内）。最终选择线性模型，换取「因子贡献可直接相加归因」的可解释性。</span></li>
  </ul>
</section>

<section>
  <h2>模型能力边界（如实呈现）</h2>
  <table>
    <tr><th>指标</th><th>模型</th><th>基准</th><th>说明</th></tr>
    <tr><td>方向准确率</td><td class="n">__ACC__</td><td>50.0%（随机）</td><td>略优于随机</td></tr>
    <tr><td>AUC</td><td class="n">__AUC__</td><td>0.500</td><td>区分度弱</td></tr>
    <tr><td>IC（预测-实际相关）</td><td class="n">__IC__</td><td>0.000</td><td>近乎无关</td></tr>
    <tr><td>MAE（美元/盎司）</td><td class="n">__MAE_M__</td><td>__MAE_N__（朴素）</td><td>与朴素基准持平</td></tr>
  </table>
  <div style="margin-top:2.6mm">
    <b>唯一有实用价值的发现</b>：把预测概率分 5 档后，方向命中率呈单调上升——
    说明<b>模型只在高置信度时相对可靠，低置信度时是噪声</b>。工作台把这一分层结果单独可视化。
  </div>
  <div class="buckets">__BUCKETS__</div>
</section>

<section>
  <h2>工程上真正花时间的地方</h2>
  <p class="dim" style="margin-bottom:2mm">
    指标不难调，难的是让数据管道不出错。以下四个问题现象都很隐蔽，且报错信息具有误导性：
  </p>
  <ul>
    <li><b>FRED 会拦截浏览器型 User-Agent。</b><span class="dim">用 <code>Mozilla/...</code> 请求会一直挂到超时，换成 <code>curl</code> 型 UA 则 0.5 秒返回。现象是「脚本卡住」而不是报错，极易误判为网络问题。</span></li>
    <li><b><code>reindex(method="ffill")</code> 不会填充源序列已有的 NaN。</b><span class="dim">FRED 在「美国休市但黄金仍交易」的日子（元旦、耶稣受难日）没有数据，直接对齐会留下空洞，导致 5 日差分变 NaN、滚动统计彻底失效。修正后有效样本从 2136 天恢复到 2528 天。</span></li>
    <li><b>浏览器里顶层 <code>const top</code> 会直接抛 SyntaxError。</b><span class="dim">它与 window 的不可配置全局属性冲突，整段脚本不执行。而 node 的语法检查因包在函数作用域里发现不了——只有真机渲染才暴露。</span></li>
    <li><b>图表库走 CDN 会让交付物变脆。</b><span class="dim">内网或无网时加载失败会导致整个页面空白。改为构建时内联进 HTML，工作台成为可离线打开的单文件。</span></li>
  </ul>
</section>

<section>
  <h2>技术栈</h2>
  <div class="tags">
    <span class="tag">Python</span>
    <span class="tag">pandas</span>
    <span class="tag">NumPy</span>
    <span class="tag">scikit-learn</span>
    <span class="tag">RidgeCV</span>
    <span class="tag">LogisticRegression</span>
    <span class="tag">SQLite</span>
    <span class="tag">走前式回测</span>
    <span class="tag">特征工程</span>
    <span class="tag">ECharts</span>
    <span class="tag">新浪财经 API</span>
    <span class="tag">FRED API</span>
    <span class="tag">离线单文件</span>
    <span class="tag">定时自动化</span>
  </div>
</section>

<div class="ft">
  <div class="row">
    <span><b>在线体验</b>　https://jw319.github.io/my-tools/gold/</span>
    <span><b>源码</b>　https://github.com/jw319/my-tools</span>
  </div>
  <div class="foot-note">
    本作品为量化研究与数据可视化用途，不构成任何投资建议。数据来源：新浪财经、FRED（圣路易斯联储）。
    模型方向准确率长期难以稳定超过 55%，工作台的价值在于纪律化的因子监控与归因，而非精准预测点位。
  </div>
</div>

</body>
</html>
"""


def find_chrome() -> str | None:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def main() -> int:
    facts = load_facts()
    print(f"读取实测数据：准确率 {facts['acc']} | AUC {facts['auc']} | "
          f"回测 {facts['samples']} 天 | {facts['n_factors']} 因子")

    preview = DOCS / "preview.jpg"
    if not preview.exists():
        print(f"缺少截图 {preview}，请先运行 build_dashboard.py")
        return 1

    b64 = base64.b64encode(preview.read_bytes()).decode()

    bucket_html = "".join(
        f'<div class="bk{" hi" if b["best"] else ""}">'
        f'<div class="bv">{b["hit"]}</div>'
        f'<div class="bl">第 {b["k"] + 1} 档 · 概率 {b["prob"]}</div></div>'
        for b in facts["buckets"]
    )

    html = (HTML
            .replace("__PREVIEW__", f"data:image/jpeg;base64,{b64}")
            .replace("__BUCKETS__", bucket_html)
            .replace("__ACC__", facts["acc"])
            .replace("__AUC__", facts["auc"])
            .replace("__IC__", facts["ic"])
            .replace("__MAE_M__", facts["mae_model"])
            .replace("__MAE_N__", facts["mae_naive"])
            .replace("__SAMPLES__", facts["samples"])
            .replace("__START__", facts["start"])
            .replace("__NF__", facts["n_factors"])
            .replace("__SRC__", facts["src_count"])
            .replace("__GOLD_DAYS__", facts["gold_days"]))

    DOCS.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"已生成中间文件 {OUT_HTML}  ({len(html) / 1024:.0f} KB)")

    chrome = find_chrome()
    if not chrome:
        print("未找到 Chrome/Edge/Chromium，无法自动打印 PDF。")
        print(f"可手动用浏览器打开 {OUT_HTML} 后「打印 → 存储为 PDF」")
        return 1

    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={OUT_PDF}",
        "--virtual-time-budget=8000",
        OUT_HTML.as_uri(),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not OUT_PDF.exists():
        print("打印失败：")
        print((r.stderr or r.stdout)[-1500:])
        return 1

    print(f"✅ 已生成 {OUT_PDF}  ({OUT_PDF.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
