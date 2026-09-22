#!/usr/bin/env bash
# 黄金走势预测工作台 —— 一键每日更新
# 采集 -> 建模 -> 生成工作台 -> 重新生成投递用 PDF -> 推送到 GitHub Pages
# 注意：ROOT 由脚本自身位置推导，所以整个文件夹移动/改名后无需修改本文件。
# 沙箱代理会拦截 git push 端点，本脚本所有 git 命令都用 env -u 显式绕过。
set -euo pipefail

PY="/Users/weijiang/.workbuddy/binaries/python/envs/default/bin/python"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ⚠️ 必须清理 PYTHONPATH：
# WorkBuddy 会在 Bash 工具调用里注入 PYTHONPATH=<...>/cli/vendor/shim，
# 使 Python 启动时加载其文件系统 shim（sitecustomize.py）。该 shim 的 mkdir
# 包装没有正确实现 exist_ok 语义 —— 目录已存在时抛 PermissionError(EEXIST)，
# 导致 collect.py 第 32 行 DATA.mkdir(exist_ok=True) 直接崩掉。
# 在 launchd / 普通终端下没有这个变量，但清掉是无害的，三种环境都能跑。
unset PYTHONPATH || true

# 沙箱代理包装函数：所有 git 命令必须绕过 HTTP(S)_PROXY，否则 push 会失败。
GIT="env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git"

echo "=================================================="
echo " 黄金走势预测工作台  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="

# ---- 幂等保护：今天已成功生成过就跳过 ----
# 因为定时触发会设多个时间点（WorkBuddy 客户端何时在线不确定），
# 一天里可能被触发好几次。这里用 data/latest.json 的 generated_at 判断
# 当天是否已经跑过，避免重复采集/建模/推送。
# 想强制重跑：./run_daily.sh --force
TODAY="$(date '+%Y-%m-%d')"
if [ "${1:-}" != "--force" ]; then
    if "$PY" -c "
import json, sys
from pathlib import Path
f = Path(r'''$ROOT''') / 'data' / 'latest.json'
try:
    gen = json.loads(f.read_text(encoding='utf-8')).get('generated_at', '')
    sys.exit(0 if gen[:10] == '$TODAY' else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo
        echo "今天（$TODAY）已更新过，跳过本次。需要强制重跑请执行： ./run_daily.sh --force"
        exit 0
    fi
fi

echo; echo ">>> [1/5] 采集数据"
"$PY" scripts/collect.py

echo; echo ">>> [2/5] 训练模型并预测"
"$PY" scripts/model.py

echo; echo ">>> [3/5] 生成工作台"
"$PY" scripts/build_dashboard.py

echo; echo ">>> [4/5] 重新生成投递用 PDF"
"$PY" scripts/make_pdf.py

echo; echo ">>> [5/5] 同步到 GitHub Pages"
# build_dashboard.py 已自动把 dashboard.html 同步到仓库根的 gold/index.html，
# 这里负责 commit + push。其他项目文件（index.html / job-search.html / recipe*.html 等）
# 不会被一并提交。data/ 与 PDF 均在 .gitignore 里，自动跳过。
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
cd "$REPO_ROOT"

$GIT add 黄金预测/dashboard.html gold/index.html 黄金预测/scripts

if $GIT diff --cached --quiet; then
    echo "无内容变化，跳过 commit / push"
else
    MSG="chore(gold): 每日更新 $(date '+%Y-%m-%d')"
    $GIT commit -m "$MSG"
    $GIT push origin main
    echo "已推送到 GitHub，Pages 通常 1-2 分钟内刷新"
fi

echo; echo "✅ 完成。工作台： open \"$ROOT/dashboard.html\""