#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成双项目作品集 PDF（A4，两页）：黄金预测 + 杯里挑一
=====================================================
数字全部实时读取：黄金从 黄金预测/data/prediction.json，
奶茶从 milktea/menu-data.js（通过 node 导出 JSON）。
截图在 portfolio/shots/ 下，由 CDP 脚本 /tmp/mt-test/portfolio-shots.js 更新。

用法：
    python make_portfolio_pdf.py

产物：
    作品集_黄金预测与杯里挑一.pdf     ← 可直接投递
    portfolio/portfolio-print.html    ← 中间产物
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOLD_DATA = ROOT / "黄金预测" / "data"
OUT_PDF = ROOT / "作品集_黄金预测与杯里挑一.pdf"
OUT_HTML = ROOT / "portfolio" / "portfolio-print.html"
SHOT_GOLD = ROOT / "portfolio" / "shots" / "gold.jpg"
SHOT_MILKTEA = ROOT / "portfolio" / "shots" / "milktea.jpg"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def load_gold_facts() -> dict:
    d = json.loads((GOLD_DATA / "prediction.json").read_text(encoding="utf-8"))
    m, p = d["metrics"], d["prediction"]
    return {
        "acc": f"{m['dir_accuracy'] * 100:.1f}%",
        "auc": f"{m['auc']:.3f}",
        "ic": f"{m['ic']:.3f}",
        "samples": f"{m['samples']}",
        "start": m["start"],
        "nf": str(len(p["contribs"])),
    }


def load_milktea_facts() -> dict:
    """通过 node 读 menu-data.js；失败时用保守兜底值。"""
    try:
        r = subprocess.run(
            ["/Users/weijiang/.workbuddy/binaries/node/versions/22.22.2-3/bin/node", "-e",
             "global.window={};require('./menu-data.js');const d=window.MT_DATA;"
             "let n=0;let news=0;d.brands.forEach(b=>{n+=b.menu.length;b.menu.forEach(m=>{if(m.isNew)news++})});"
             "console.log(JSON.stringify({brands:d.brands.length,skus:n,news:news,version:d.version}));"],
            cwd=ROOT / "milktea", capture_output=True, text=True, timeout=30)
        d = json.loads(r.stdout.strip())
        return {"brands": str(d["brands"]), "skus": str(d["skus"]),
                "news": str(d["news"]), "version": d["version"]}
    except Exception as e:
        print(f"警告：读取奶茶数据失败（{e}），用兜底值")
        return {"brands": "25", "skus": "432", "news": "57", "version": "2.4.0"}


def b64img(p: Path) -> str:
    return f"data:image/jpeg;base64,{base64.b64encode(p.read_bytes()).decode()}"


CSS = """
  @page { size: A4; margin: 10mm 12mm; }
  * { box-sizing: border-box; margin: 0; padding: 0;
      -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", sans-serif;
         color: #171a21; font-size: 8.9pt; line-height: 1.5; }
  a { color: #c9922f; text-decoration: none; }

  .hd { border-bottom: 2.5pt solid var(--ac, #c9922f); padding-bottom: 2.4mm; margin-bottom: 2.4mm; }
  .kicker { font-size: 7.6pt; font-weight: 700; letter-spacing: 2.4px; color: var(--ac, #c9922f);
            text-transform: uppercase; margin-bottom: 2mm; }
  h1 { font-size: 17pt; font-weight: 750; letter-spacing: -.6px; line-height: 1.16; }
  h1 .en { font-size: 9pt; font-weight: 500; color: #8b93a1; margin-left: 2mm; }
  .sub { font-size: 9pt; color: #5b6472; margin-top: 1.6mm; }
  .links { margin-top: 2.2mm; font-size: 8.2pt; color: #8b93a1; }
  .links b { color: #5b6472; font-weight: 600; }

  .metrics { display: flex; gap: 2.4mm; margin-bottom: 2.2mm; }
  .m { flex: 1; border: .8pt solid #e6e8ec; border-radius: 2.4mm; padding: 2mm 2.4mm; background: #fcfcfd; }
  .m .v { font-size: 12.5pt; font-weight: 750; letter-spacing: -.5px; line-height: 1.1; }
  .m .v.g { color: var(--ac, #c9922f); }
  .m .k { font-size: 7.4pt; color: #8b93a1; margin-top: .8mm; }

  .shot { border: .8pt solid #e6e8ec; border-radius: 2.4mm; overflow: hidden; background:#fff; }
  .shot img { display: block; margin: 0 auto; }
  .cap { font-size: 7pt; color: #8b93a1; margin: 1.2mm 0 2.4mm; text-align: center; }

  section { margin-bottom: 2.2mm; }
  h2 { font-size: 9.8pt; font-weight: 700; margin-bottom: 1.6mm;
       padding-left: 2.6mm; border-left: 2.6pt solid var(--ac, #c9922f); line-height: 1.3; }
  ol, ul { padding-left: 4.4mm; }
  li { margin-bottom: .9mm; }
  li b { font-weight: 650; }
  .dim { color: #5b6472; }

  table { width: 100%; border-collapse: collapse; margin-top: 1.4mm; font-variant-numeric: tabular-nums; }
  th { text-align: left; font-size: 7.2pt; font-weight: 600; color: #8b93a1;
       padding: 1mm 2mm; border-bottom: .8pt solid #e6e8ec; background: #fafbfc; }
  td { padding: 1mm 2mm; font-size: 8.2pt; border-bottom: .6pt solid #eef0f3; }
  td.n { font-weight: 700; }

  .tags { display: flex; flex-wrap: wrap; gap: 1.5mm; margin-top: 1mm; }
  .tag { font-size: 7.6pt; padding: .9mm 2.3mm; border-radius: 1.4mm;
         background: #f4f5f7; border: .6pt solid #eef0f3; color: #5b6472; }

  .ft { page-break-inside: avoid; border-top: .8pt solid #e6e8ec; padding-top: 1.6mm; margin-top: .4mm;
        font-size: 7.6pt; color: #8b93a1; line-height: 1.75; }
  .ft .row { display: flex; justify-content: space-between; gap: 6mm; }
  .foot-note { font-size: 7pt; color: #a8b0bc; margin-top: 1.2mm; }

  .page2 { page-break-before: always; }
  section, .metrics, table, .shot { page-break-inside: avoid; }
"""


def gold_page(g: dict, img: str) -> str:
    return f"""
<div style="--ac:#c9922f">
<div class="hd">
  <div class="kicker">Project 1 · Quant Research</div>
  <h1>黄金走势预测工作台</h1>
  <div class="sub">每日自动采集 COMEX 金价与全球宏观因子 · {g['nf']} 因子多因子建模 · 预测次日走势 · 单文件可视化工作台</div>
  <div class="links"><b>在线体验</b> <a href="https://jw319.github.io/my-tools/gold/">jw319.github.io/my-tools/gold/</a>
  　|　<b>源码</b> github.com/jw319/my-tools　|　离线可打开（图表库与数据全部内联）</div>
</div>

<div class="metrics">
  <div class="m"><div class="v">16+</div><div class="k">免费数据源</div></div>
  <div class="m"><div class="v">{g['nf']}</div><div class="k">个因子 / 5 大类</div></div>
  <div class="m"><div class="v">{g['samples']}</div><div class="k">天走前式回测</div></div>
  <div class="m"><div class="v g">{g['acc']}</div><div class="k">方向准确率</div></div>
</div>

<div class="shot"><img src="{img}" style="width:46%" alt="黄金走势预测工作台界面"></div>
<div class="cap">工作台界面：金价走势与次日预测、模型信号、驱动因子贡献分解、置信度分层命中率</div>

<section><h2>做了什么</h2><ol>
  <li><b>数据工程</b><span class="dim">——打通 16+ 个免费、无需 API Key 的数据源：新浪财经国际期货接口提供 COMEX 黄金日线，FRED 提供实际利率、美元指数、VIX、通胀预期等宏观因子。</span></li>
  <li><b>因子体系</b><span class="dim">——构建 {g['nf']} 个因子，分利率、汇率、风险、通胀商品、动量五类；只用因子的「变化量」而非绝对水平做趋势外推，避免非平稳序列的伪回归。</span></li>
  <li><b>严谨验证</b><span class="dim">——走前式回测 {g['samples']} 个交易日（每月滚动重训，{g['start']} 至今），严格按真实发布滞后对齐因子，杜绝未来数据泄露。</span></li>
  <li><b>交付工程</b><span class="dim">——单文件 HTML 工作台，图表库与数据全部内联，断网可打开；定时任务每日自动更新。</span></li>
</ol></section>

<section><h2>关键选择，以及背后的取舍</h2><ul>
  <li><b>不用 LSTM / 深度学习。</b><span class="dim">开源社区同类项目实测：有限样本上堆外部因子 + LSTM 会严重过拟合，反而跑不过朴素基准。选择可解释性更好的强正则线性模型。</span></li>
  <li><b>用实验决定，不靠直觉。</b><span class="dim">测试过滚动标准化（更差）与 GBDT（仅高 0.9pp，在噪声范围内）。最终选择线性模型，换取「因子贡献可直接相加归因」的可解释性。</span></li>
</ul></section>

<section><h2>模型能力边界（如实呈现）</h2>
<table>
  <tr><th>指标</th><th>模型</th><th>基准</th><th>说明</th></tr>
  <tr><td>方向准确率</td><td class="n">{g['acc']}</td><td>50.0%（随机）</td><td>略优于随机</td></tr>
  <tr><td>AUC</td><td class="n">{g['auc']}</td><td>0.500</td><td>区分度弱</td></tr>
  <tr><td>IC（预测-实际相关）</td><td class="n">{g['ic']}</td><td>0.000</td><td>近乎无关</td></tr>
</table>
<div class="dim" style="margin-top:2mm"><b>唯一有实用价值的发现</b>：按预测概率分 5 档后，方向命中率单调上升——模型只在高置信度时相对可靠。工作台把这一分层结果单独可视化。</div>
</section>

<section><h2>技术栈</h2><div class="tags">
  <span class="tag">Python</span><span class="tag">pandas</span><span class="tag">NumPy</span>
  <span class="tag">scikit-learn</span><span class="tag">RidgeCV</span><span class="tag">走前式回测</span>
  <span class="tag">特征工程</span><span class="tag">ECharts</span><span class="tag">FRED API</span>
  <span class="tag">离线单文件</span><span class="tag">定时自动化</span>
</div></section>

<div class="ft">
  <div class="row"><span><b>在线体验</b>　jw319.github.io/my-tools/gold/</span><span><b>源码</b>　github.com/jw319/my-tools</span></div>
  <div class="foot-note">本作品为量化研究与数据可视化用途，不构成任何投资建议。数据来源：新浪财经、FRED（圣路易斯联储）。</div>
</div>
</div>"""


def milktea_page(mt: dict, img: str) -> str:
    return f"""
<div class="page2" style="--ac:#B87B4B">
<div class="hd">
  <div class="kicker">Project 2 · Interactive Web App</div>
  <h1>杯里挑一<span class="en">智能奶茶推荐</span></h1>
  <div class="sub">百里挑一，不如杯里挑一 · 心情 × 口味 × 品牌三路打分推荐引擎 · 手机竖屏单页应用 · 菜单每周自动更新</div>
  <div class="links"><b>在线体验</b> <a href="https://jw319.github.io/my-tools/milktea/">jw319.github.io/my-tools/milktea/</a>
  　|　<b>源码</b> github.com/jw319/my-tools　|　移动端全屏 / 桌面端手机壳居中</div>
</div>

<div class="metrics">
  <div class="m"><div class="v">{mt['brands']}</div><div class="k">家品牌</div></div>
  <div class="m"><div class="v">{mt['skus']}</div><div class="k">款在售饮品</div></div>
  <div class="m"><div class="v">10</div><div class="k">种心情维度</div></div>
  <div class="m"><div class="v g">{mt['news']}</div><div class="k">款当季新品（{mt['version']}）</div></div>
</div>

<div class="shot"><img src="{img}" style="width:50%" alt="杯里挑一界面"></div>
<div class="cap">推荐页：左侧品牌边栏（可多选圈定范围）+ 心情/条件输入 → 出推荐结果与匹配度归因</div>

<section><h2>做了什么</h2><ol>
  <li><b>心情推荐引擎</b><span class="dim">——10 种心情多选（开心/疲惫/低落/约会/熬夜/解腻/省钱/轻负担…），每种心情映射「品类 × 口味标签 × 品牌画像」三路打分，推荐语自动归因。</span></li>
  <li><b>双模式输入</b><span class="dim">——还支持口味偏好（6 大类 × 8 种茶底 × 补充条件）与品牌范围圈定，左侧边栏与主页品牌多选双向同步。</span></li>
  <li><b>菜单数据工程</b><span class="dim">——数据与逻辑分离（menu-data.js + update.json 合并）；品名逐家对照品牌官网/官方社媒与公开报道核对，每周一自动联网复核，NEW 标 3 个月自动摘除。</span></li>
  <li><b>交付形态</b><span class="dim">——零依赖单文件应用，手机全屏、桌面手机壳居中；GitHub Pages 公开托管，访客免登录直接打开。</span></li>
</ol></section>

<section><h2>关键选择，以及背后的取舍</h2><ul>
  <li><b>不接品牌方 API。</b><span class="dim">点餐小程序无公开接口，选择「公开来源核对 + 每周联网复核」，页面明确标注来源与时效。</span></li>
  <li><b>规则打分，不上模型。</b><span class="dim">{mt['skus']} 个 SKU 的推荐排序用可解释的规则加权即可，每条推荐都能给出归因文案；引入排序模型对这个规模是负收益。</span></li>
  <li><b>真交互验证，不只看截图。</b><span class="dim">装不上 puppeteer 就用 Node 22 全局 WebSocket 直连 CDP 零依赖驱动系统 Chrome：点心情 → 圈品牌 → 断言推荐结果。</span></li>
</ul></section>

<section><h2>技术栈</h2><div class="tags">
  <span class="tag">原生 HTML/CSS/JS</span><span class="tag">单文件应用</span><span class="tag">Canvas 转盘</span>
  <span class="tag">CDP 自动化测试</span><span class="tag">数据/逻辑分离</span><span class="tag">update.json 增量合并</span>
  <span class="tag">GitHub Pages</span><span class="tag">每周定时自动化</span>
</div></section>

<div class="ft">
  <div class="row"><span><b>在线体验</b>　jw319.github.io/my-tools/milktea/</span><span><b>源码</b>　github.com/jw319/my-tools</span></div>
  <div class="foot-note">菜单品名来自公开来源（品牌官网/官方社媒/公开报道），每周自动复核；个别门店实际在售与价格可能滞后，不构成任何消费建议。</div>
</div>
</div>"""


def main() -> int:
    for p in (SHOT_GOLD, SHOT_MILKTEA):
        if not p.exists():
            print(f"缺少截图 {p}，请先运行截图脚本")
            return 1
    g = load_gold_facts()
    mt = load_milktea_facts()
    print(f"黄金：准确率 {g['acc']} | 回测 {g['samples']} 天 | {g['nf']} 因子")
    print(f"奶茶：{mt['brands']} 品牌 | {mt['skus']} 款 | {mt['news']} 新品 | v{mt['version']}")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>作品集 · 黄金预测与杯里挑一</title><style>{CSS}</style></head>
<body>{gold_page(g, b64img(SHOT_GOLD))}{milktea_page(mt, b64img(SHOT_MILKTEA))}
</body></html>"""

    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"中间文件 {OUT_HTML}  ({len(html) / 1024:.0f} KB)")

    chrome = next((p for p in CHROME_CANDIDATES if Path(p).exists()), None)
    if not chrome:
        print("未找到 Chrome，可手动用浏览器打开 HTML 打印为 PDF")
        return 1

    r = subprocess.run([
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer", f"--print-to-pdf={OUT_PDF}",
        "--virtual-time-budget=8000", OUT_HTML.as_uri(),
    ], capture_output=True, text=True, timeout=180)
    if not OUT_PDF.exists():
        print("打印失败：")
        print((r.stderr or r.stdout)[-1500:])
        return 1
    print(f"✅ 已生成 {OUT_PDF}  ({OUT_PDF.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
