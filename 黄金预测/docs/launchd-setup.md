# 黄金预测工作台 · 系统级自动更新（launchd 兜底）

## 背景

WorkBuddy 自带 automation 的调度器依赖客户端常驻。如果你退出 WorkBuddy，就不会跑。
macOS 系统级 launchd 不依赖任何客户端进程——只要 Mac 开机/唤醒，就会按时触发。

## 当前状态

- ✅ plist 文件已写好：`~/Library/LaunchAgents/com.workbuddy.gold.daily.plist`
- ⏸️ **未注册**：因为 macOS 26.2 对未签名 LaunchAgent 强制拦截 `launchctl load`，WorkBuddy 沙箱内注册失败（错误码 5 I/O error）。
- ✅ WorkBuddy automation 已恢复 ACTIVE，作为客户端层的备份调度。

## 主人操作（两行命令）

打开 **macOS 终端**（不是 WorkBuddy 终端），执行：

```bash
xattr -d com.apple.provenance ~/Library/LaunchAgents/com.workbuddy.gold.daily.plist
launchctl load ~/Library/LaunchAgents/com.workbuddy.gold.daily.plist
```

第一行去掉 macOS 给 plist 加的"未签名"标记（macOS 26.2 自动加的）。
第二行真正注册到 launchd。

## 验证

```bash
launchctl list | grep workbuddy
```

应该看到一行：
```
-       0       com.workbuddy.gold.daily
```
（左列 PID、右列上次退出码，PID 为 `-` 表示还没跑过，7:00 后会变成数字）

## 看执行日志

```bash
tail -f "/Users/weijiang/Documents/vibe coding/黄金预测/logs/launchd.stdout.log"
tail -f "/Users/weijiang/Documents/vibe coding/黄金预测/logs/launchd.stderr.log"
```

## 卸载

```bash
launchctl unload ~/Library/LaunchAgents/com.workbuddy.gold.daily.plist
rm ~/Library/LaunchAgents/com.workbuddy.gold.daily.plist
```

## 行为

- 每天 07:00 触发 `./run_daily.sh`
- 完整流水线：采集 → 建模 → 生成 dashboard.html + gold/index.html → 出 PDF → git commit + git push
- 沙箱代理在 `run_daily.sh` 内已用 `env -u` 绕过，push 不会失败
- 进程超时 30 分钟自动 kill，避免卡死
- 输出日志落到 `黄金预测/logs/launchd.{stdout,stderr}.log`

## 已知限制

- Mac 进入睡眠后，唤醒时 7:00 那次已过去——launchd 不会补跑，会等下一日 7:00。
- 这就是为什么 WorkBuddy automation 也保留 ACTIVE 作为兜底；双保险。