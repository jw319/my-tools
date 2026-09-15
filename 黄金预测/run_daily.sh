#!/usr/bin/env bash
# 黄金走势预测工作台 —— 一键每日更新
# 采集 -> 建模 -> 生成工作台
set -euo pipefail

PY="/Users/weijiang/.workbuddy/binaries/python/envs/default/bin/python"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=================================================="
echo " 黄金走势预测工作台  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="

echo; echo ">>> [1/3] 采集数据"
"$PY" scripts/collect.py

echo; echo ">>> [2/3] 训练模型并预测"
"$PY" scripts/model.py

echo; echo ">>> [3/3] 生成工作台"
"$PY" scripts/build_dashboard.py

echo; echo "✅ 完成。打开工作台： open \"$ROOT/dashboard.html\""
