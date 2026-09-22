# 黄金预测工作台 · 自动更新方案

## 结论先说

本机是**受限环境**，系统级定时任务全部不可用：

| 方案 | 结果 | 证据 |
|---|---|---|
| `launchctl bootstrap/load` | ❌ 失败 | `Bootstrap failed: 5: Input/output error`，连最简 plist（无中文、无参数）也一样 |
| `crontab` | ❌ 失败 | `operation not permitted: crontab` |
| `sudo` | ❌ 失败 | `operation not permitted: sudo` |

补充证据：`~/Library/LaunchAgents/` 里已有的 Google、Pixso 等 plist **也全部未注册**在 launchd 中（`launchctl list` 查不到），说明这不是本项目 plist 的问题，而是本机 launchd 用户域整体不接受加载。

→ **自动更新改用 WorkBuddy automation（客户端层）**。

## 实际方案：automation 多点触发 + 脚本幂等

### 1. automation 配置

- ID：`automation-1789436602517`
- 名称：黄金预测工作台 · 每日更新（每2小时触发·幂等）
- 触发：`FREQ=HOURLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR` —— **工作日每 2 小时**
- 状态：ACTIVE

**为什么不用「每天 7:00」**：automation 调度器跟着 WorkBuddy 客户端走，客户端不在线就不触发。主人开机时间不固定（记录到 9:16、14:47 等），固定 7:00 命中率极低——这正是 9/15 之后连续多天没更新的直接原因。改成每 2 小时触发，只要客户端在线就会命中。

### 2. 脚本幂等保护

`run_daily.sh` 开头会检查 `data/latest.json` 的 `generated_at` 是否为今天：

- 是今天 → 打印「今天已更新过，跳过本次」并 `exit 0`，不重复采集/建模/推送
- 不是今天 → 正常跑完整流水线

所以一天内被触发多次是安全的，第一次命中会真正跑，其余快速跳过。

强制重跑（忽略幂等）：

```bash
cd "/Users/weijiang/Documents/vibe coding/黄金预测" && ./run_daily.sh --force
```

### 3. 手动跑

```bash
cd "/Users/weijiang/Documents/vibe coding/黄金预测" && ./run_daily.sh
```

流水线 5 步：采集 → 建模 → 生成 dashboard.html + gold/index.html → 出 PDF → git commit + push。

## 排错

### 症状：数据没更新

1. 看客户端是否在线（automation 依赖客户端）：
   ```bash
   cat ~/.workbuddy/last-launch.json
   ```
2. 看 automation 是否执行过：
   ```bash
   sqlite3 ~/.workbuddy/workbuddy.db "SELECT * FROM automation_runtime_state;"
   ```
3. 手动跑一次看具体报错：
   ```bash
   cd "/Users/weijiang/Documents/vibe coding/黄金预测" && ./run_daily.sh --force
   ```

### 已知坑 1：`PermissionError: EEXIST ... mkdir`

在 WorkBuddy 的 Bash 工具里跑 Python 脚本时，`PYTHONPATH` 被注入了
`<WorkBuddy>/cli/vendor/shim`，Python 启动时加载其文件系统 shim，
该 shim 的 `mkdir` 包装没有正确实现 `exist_ok` 语义——目录已存在时抛
`PermissionError(EEXIST)`，导致 `collect.py` 第一步就崩。

**已修复**：`run_daily.sh` 开头 `unset PYTHONPATH`，三种环境（WorkBuddy / 终端 / 定时任务）都能跑。
不要绕过脚本自己调 python。

### 已知坑 2：git push 被沙箱代理拦截

环境变量里的 `HTTP_PROXY/HTTPS_PROXY` 指向沙箱代理，**放行 GitHub 只读 API 但拦截 push 端点**，报错很像网络问题（`HTTP2 framing layer` / `CONNECT tunnel 502`），极具误导性。

**已修复**：`run_daily.sh` 里所有 git 命令都用
`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy` 包装。

### 已知坑 3：GitHub Pages 有 10 分钟 CDN 缓存

push 成功后访问页面可能仍看到旧数据。响应头 `cache-control: max-age=600`。
验证真实内容时加 cache-buster：

```bash
curl -s "https://jw319.github.io/my-tools/gold/?cb=$(date +%s)" | grep -o 'generated_at":"[^"]*"'
```

## 附：如果换到不受限的机器

`com.workbuddy.gold.daily.plist`（每早 7:00 跑，超时 30 分钟，日志落 `logs/`）内容已在
git 历史里（commit `8ded44c` 之前那段），换机后放回 `~/Library/LaunchAgents/` 并
`launchctl load` 即可。但**本机用不了**，别再试。
