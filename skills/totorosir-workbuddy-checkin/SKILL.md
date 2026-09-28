---
name: totorosir-workbuddy-checkin
display_name: WorkBuddy签到助手
display_name_en: WorkBuddy Check-in Assistant
description: WorkBuddy签到助手（WorkBuddy「Buddy 加油站」每日签到自动化 Skill，接口直签，无需点击 GUI，跨平台支持 Windows / macOS / Linux）。当用户说"每天自动签到 WorkBuddy / 每日签到 / 自动领 Buddy 加油站积分 / 自动领 100 积分 / 设置 WorkBuddy 每日签到 / WorkBuddy 打卡 / 自动打卡 WorkBuddy / 帮我签到一次 / 现在签个到 / 检查签到环境 / 派猫猫旅行 / 猫猫旅行 / 旅行积分 / 领旅行奖励 / Buddy 在旅行吗 / 还有多久回来 / 自动派猫猫 / 推送签到结果 / 签到通知发钉钉"时使用。原理是读取本机已登录 WorkBuddy 的登录态 accessToken，直接调用官方签到接口完成领取，并支持派猫猫旅行全自动闭环（先领后派）；支持桌面通知与 12 类渠道的多渠道消息推送（钉钉/飞书/企业微信/微信/邮件/短信/QQ/Slack/Telegram/Bark/通用 Webhook/系统通知），推送接口设计与配置项对齐 totorosir-push-message 技能。
description_zh: 读取本机 WorkBuddy 登录态，直接调用官方接口完成「Buddy 加油站」每日签到（无需点击 GUI），并支持派猫猫旅行（查状态 / 领旅行积分 / 派 Buddy 出门，默认随签到跑全自动闭环）。支持桌面通知与 12 类多渠道消息推送（配置项/接口对齐 totorosir-push-message 技能），可设置每日 09:00 自动签到。
description_en: Auto check-in to WorkBuddy Buddy Station using the local auth token via the official API (no GUI clicks), plus Buddy Travel support (query status, claim travel credits, dispatch Buddy; runs a claim-then-dispatch loop by default). Cross-platform, with desktop notification and 12-channel push (DingTalk/Feishu/WeCom/WeChat/Email/SMS/QQ/Slack/Telegram/Bark/Webhook/system) whose interface and config mirror the totorosir-push-message skill; supports a daily 09:00 automation.
category: 自动化
version: 3.0.0
author: totorosir
agent_created: true
---

# WorkBuddy签到助手（每日自动签到 · 派猫猫旅行 · 多渠道消息推送 · 接口直签）

WorkBuddy「Buddy 加油站」每日签到本质是一次带本地登录 Token 的 HTTP 接口请求，**不需要**模拟点击左下角「个人信息 → Buddy 加油站 → 签到」这一套 GUI 流程（自动化代理也没有点击桌面 UI 的能力）。

本 Skill 自带脚本 `scripts/workbuddy_checkin.py`，仅用 Python 标准库（urllib/json/os/socket/subprocess），零第三方依赖。

> 面向用户的完整说明（快速开始 / 桌面通知 / 消息推送配置 / 环境自检 / FAQ / 反模式 / 排错）见 `README.md`。
> 接口规范、登录态格式、字段与错误码、推送模块接口见 `@references/api-spec.md`。
> 自动化提示词、命令示例与推送配置示例见 `@references/examples.md`。
> 本文件只保留 Skill 元数据与代理执行所需关键信息，避免内容重复维护。

## 关键事实（已实测验证，Windows / macOS / Linux，WorkBuddy v5.3.x）

- **登录态文件（明文 JSON）**：
  `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`
  （旧版可能在 `%APPDATA%` 同路径下；v5.3.8+ 为明文）
- 文件内 `auth.accessToken`（JWT，`auth.tokenType=Bearer`）、`auth.domain`（实测值 `www.codebuddy.cn`）。
- **接口域名**：以登录态里的 `auth.domain` 为准（实测为 `www.codebuddy.cn`）。注意：网上部分文章写 `copilot.tencent.com` 会 404，应以本机 `domain` 字段为准。
- **状态查询（只读）**：`POST https://<domain>/v2/billing/meter/checkin-activity-status`
  返回 `{"code":0,"data":{"today_checked_in":true/false,"streak_days":N,"daily_credit":100,...}}`（data 中可能含 **`total_credits`**（复数）/ `balance` 等余额字段，脚本会自动提取并展示）
- **领取签到**：`POST https://<domain>/v2/billing/meter/daily-checkin`
  - 成功：HTTP 200，`code:0`，返回 `credit` / `streak_days`（领取 100 积分）。
  - 已签到：HTTP 400，`code:10001`，`msg:"今天已签到，请明天再来"` —— **幂等，不会重复发**。

### 派猫猫旅行（关键：域名不同、且无 `/v2` 前缀）

- **旅行接口域名**：`https://www.workbuddy.cn`。**与签到域名不是同一个**，路径也**不带 `/v2` 前缀**；用签到域名或误加 `/v2` 一律 404。
- **旅行状态（只读）**：`GET /activity/growth/buddy/travel/status`
  - `data.state`：`idle` 空闲 / `traveling` 旅行中 / `arrived` 已到达待领取。
  - 另有 `daily_limit_reached`（今日派遣是否达上限）、`reward_credit`、`location`、`arrive_at`、`server_now`。
- **领取旅行积分**：`POST /activity/growth/buddy/travel/claim`（body `{}`）—— 仅 `arrived` 时可领。
- **派出 Buddy**：`POST /activity/growth/buddy/travel/depart`（body `{"location_id": N}`）
  - 仅 `idle` 且**未达每日上限**时派遣；地点 1-4（咖啡馆 / 商场店铺 / 健身房 / 古镇客栈），四个地点收益完全相同（随机 1-4 小时、5-10 积分），缺省随机。
- **不会丢积分**：`arrived` 状态会一直保留，下次运行自动补领。
- 接口仅需 Bearer Token，**无需** Turing Shield 设备指纹。

完整字段、路径与错误码对照见 `@references/api-spec.md`。

## 自带脚本

两个脚本，均只用 Python 标准库，零第三方依赖：

- `scripts/workbuddy_checkin.py` —— 签到 + 派猫猫旅行主流程（下文「核心逻辑」即指它）
- `scripts/push_message.py` —— 多渠道消息推送模块（被主脚本按同目录导入，也可独立运行）

### 主脚本核心逻辑
1. 在 `LOCALAPPDATA` / `APPDATA` / `~/Library/Application Support` / `~/.config`（及 `~/.workbuddy/auth` 兜底）定位 `workbuddy-desktop.info`，只读取出 `accessToken` 与 `domain`。
2. 调 `checkin-activity-status`：若 `data.today_checked_in==true` → 直接 `skip_already_signed` 退出（不发领取请求）。
3. 否则调 `daily-checkin` 领取；响应 `code==10001` 或含"已签到" → 视为已签安全跳过；HTTP 200 且 `code==0` → 领取成功。
4. 非 2xx 也解析响应体（避免把"已签到 400"误判为异常）。
5. **输出 JSON 结果，全程不打印任何真实 token**（仅脱敏 `eyJhbG...xxxx`）。退出码：成功 0 / 失败 1。

支持参数：
- （无参数）签到 + 派猫猫旅行全自动闭环（**默认**）
- `--no-travel` 只签到，跳过旅行（最快档）
- `--check-only` 仅查询状态（只读，不领取、不写旅行）
- `travel` 只查派猫猫旅行状态（只读，不签到）
- `travel --travel-auto` 只跑旅行闭环（不签到）
- `--travel-auto` 显式开启旅行闭环（默认已开，写出来只为明确表达）
- `--location N` 指定派遣地点（1-4，缺省随机）
- `--push-channels dingtalk,email` 仅向指定渠道推送（覆盖配置里的渠道集合）
- `--confirm-paid` 允许发送付费渠道（短信）；缺省时付费渠道一律跳过
- `--no-notify` 跳过全部推送与桌面通知（调试用）
- `--diagnose` 环境自检（Python/登录态/网络/桌面会话/推送配置，只读）
- `--init-config` 生成 `notify_config.json.example` 模板
- `--version` / `--help`

推送模块也可独立运行（便于单独调试渠道）：`python scripts/push_message.py --title "标题" --content "正文" --ready`

**派猫猫旅行闭环顺序（先领后派）**
1. 查状态：`arrived` → 领取积分 → 重新查状态。
2. 此时若为 `idle` 且 `daily_limit_reached` 为假 → 派出；已达上限 → 跳过并说明。
3. 若 `traveling` → 不派遣，仅展示到达倒计时。

能力要点：
- **桌面通知（默认开启）**：每次执行后弹系统级 toast 展示结果与余额；受 `--no-notify` 抑制；无桌面会话时自动跳过，不影响签到。
- **失败消息推送（可选）**：`status!=ok` 时读取本地 `~/.workbuddy/scripts/notify_config.json`（若存在），向已就绪渠道推送失败提醒；支持 12 类渠道，配置缺失或通道异常则静默跳过，单渠道失败不影响其他渠道。
- **成功消息播报（可选，默认关闭）**：`notify_config.json` 中 `success_notify: true` 时，签到成功也会推送一条播报；默认 `false` 保持静默无打扰。推送逻辑由 `scripts/push_message.py` 提供（接口/配置项对齐 totorosir-push-message 技能）。
- **多渠道推送模块**：`CHANNELS` 注册表 + 每渠道 `build_<channel>` 构造器统一返回 `("http", url, payload, headers)` / `("smtp", …)` / `("system", …)`，由 `send_one` 分发；配置支持旧扁平字段与新 `channels` 映射双结构归一化；付费渠道（短信）需 `--confirm-paid` 显式放行。
- **积分余额展示**：从状态/领取响应中尽力提取「积分余额」（**`total_credits`**（复数）/ `balance` / `points_balance` 等），写入结果 `balance` 字段并展示；接口未返回则自动跳过。
- **派猫猫旅行（默认随签到执行）**：查状态 / 领旅行积分 / 派 Buddy 出门全自动闭环；**派出前必查 `daily_limit_reached`，达上限一个写请求都不发**；已到达不会丢积分。结果写入 `travel` 字段并拼进主消息与桌面通知；旅行接口不可用时静默降级，绝不改变签到结论。
- **环境自检（--diagnose）**：只读自检上述五项，输出 JSON 报告，便于首次安装后确认环境就绪。

## 调用本 Skill 时的搭建流程（照做即可）

当用户要求搭建/修复自动签到，或换机/重装后重建时：

1. **定位登录态并校验 token**
   - 找到 `workbuddy-desktop.info`，确认 `auth.accessToken` 存在且未过期（`expiresAt` 字段）。
   - 若文件不存在或 token 失效：如实告知用户"请先在 WorkBuddy 客户端登录"，**不要**伪造或猜测。

2. **落位脚本到稳定路径**
   - 把本 Skill 目录里的 `scripts/workbuddy_checkin.py` **与 `scripts/push_message.py` 一起**复制到 `~/.workbuddy/scripts/`（两文件必须同目录，主脚本按同目录导入推送模块；只复制主脚本时推送自动降级为不可用，签到本身不受影响）。
   - 用 Python 跑一次 `--check-only` 验证接口通、token 有效（应返回 `status_http:200`、`today_signed` 字段）。
   - 可顺带跑一次 `--diagnose`，把自检报告读给用户，确认环境就绪（含推送渠道就绪情况）。

3. **验证领取分支（可选但建议）**
   - 跑一次不带参数的完整脚本：若当天已签 → 返回 `skip_already_signed`；若未签 → 返回 `clicked` 并提示用户去 Buddy 加油站界面核对 +100。

4. **创建 WorkBuddy 自带自动化**（不要用 crontab / launchd / 第三方定时器）
   - 用 `automation_update`（mode=create）创建 recurring 自动化：
     - name：`WorkBuddy签到助手 · 每日自动签到`
     - rrule：`FREQ=DAILY;BYHOUR=9;BYMINUTE=0`
     - status：`ACTIVE`
   - 自动化提示词（让代理用 Bash 跑脚本并脱敏汇报）见 `@references/examples.md`。

5. **向用户汇报**：自动化名称、执行时间、脚本路径；并提醒"若当天已手动签到会自动跳过；首个真实自动领取通常在次日 09:00，请在 Buddy 加油站核对积分 +100"。

## 消息推送（可选，12 渠道）

签到失败 / 成功时（按配置），脚本通过 `scripts/push_message.py` 向已就绪渠道推送提醒。**推送凭据只存在于本地 `notify_config.json`，永不进入脚本或技能目录**。

| 渠道 | 标识 | 必填配置项 |
|---|---|---|
| 钉钉群机器人 | `dingtalk` | `webhook`（可选 `secret` 加签） |
| 飞书群机器人 | `feishu` | `webhook`（可选 `secret`） |
| 企业微信群机器人 | `wecom` | `webhook` |
| 微信（PushPlus 中转） | `wechat` | `pushplus_token` |
| 邮件 | `email` | `smtp_host` / `smtp_user` / `smtp_pass` / `from` / `to` |
| 短信（**付费**） | `sms` | `url` / `payload_template` |
| QQ | `qq` | `url` |
| Slack | `slack` | `webhook_url` |
| Telegram | `telegram` | `bot_token` / `chat_id` |
| Bark（iOS） | `bark` | `server` / `device_key`（也兼容整条 `bark_url`） |
| 通用 Webhook | `webhook` | `url`（可选 `payload_template` / `secret`） |
| 系统通知 | `system` | **零配置**，写本地 `notifications.jsonl` + 桌面 toast |

**配置两种写法可混用**（`normalize_channels` 会归一化后合并）：
- 新结构 `channels` 映射 —— 渠道最全，推荐：`{"channels": {"dingtalk": {"webhook": "..."}, "email": {...}}}`
- 旧结构扁平字段 —— 微信三通道向后兼容：`wecom_webhook` / `pushplus_token` / `bark_url`

**行为约定**：
- `enabled: false` 或配置文件不存在 → 不推送，仅输出 JSON 结果（失败时退出码仍为 1）。
- 失败推送：仅在 `status!=ok` 时推送。
- 成功播报：仅当 `success_notify: true` 时推送；`--check-only` 纯查询不会推送。
- **单渠道失败隔离**：某渠道报错只记录该渠道失败，不影响其他渠道与签到退出码。
- **付费闸门**：`sms` 属付费渠道，未显式带 `--confirm-paid` 时一律跳过并标记，不会意外产生短信费用。
- 推送结果仅记录到 `detail.notify` / `detail.notify_success`（含渠道名与状态，**不含任何密钥值**），**不影响签到退出码**。

配置模板与真实示例见 `@references/examples.md`，模块接口规范见 `@references/api-spec.md`。

## 安全约束（务必遵守）

- 只读登录态文件，绝不修改、绝不删除、绝不外传 `accessToken` / `refreshToken`。
- 任何输出（终端、日志、汇报）都不得包含真实 token 或推送凭据；脚本已脱敏，代理也不要回显凭据。
- 推送凭据只存本地 `notify_config.json`；**不要**把填了真实密钥的配置文件放进技能目录、打包进 zip 或提交到仓库。
- 写操作仅限已验证的 3 个端点：`daily-checkin`（签到）、`travel/claim`（领旅行积分）、`travel/depart`（派遣）。推送是独立的本地外发行为，不得借推送接口做任意地址请求。
- 不要为推送额外引入第三方 SDK / PyPI 依赖；模块只用 Python 标准库。
- 不安装 Electron；本 Skill 自身只用 WorkBuddy 自带自动化完成每日签到。
- 如需**系统级定时任务**（Windows 计划任务 / macOS launchd / Linux crontab，脱离 WorkBuddy 也能跑），请使用独立的「WorkBuddy 自动签到分享包」，与本 Skill 互不冲突、可并存。
- 不要在网页版尝试签到（网页版无签到入口，仅 PC 客户端专属）。

## 排错要点（详见 `README.md` 排错速查）

- `code=10001` 是今日已签，非错误。
- 404 一定是用了错误域名（脚本自动用本机 `auth.domain`）。
- **旅行接口 404 先查两件事**：域名必须是 `www.workbuddy.cn`（不是登录态里的 `auth.domain`），且路径**不能带 `/v2`**。
- 「今日派遣次数已用完」是正常的服务端每日限额，次日自动恢复，不是故障。
- 旅行中无法提前召回：官方没有召回接口，只能等到达后自动领取。
- **推送没发出**：先跑 `--diagnose` 看 `notify_config.ready` 是否列出你的渠道；`ready` 为空说明配置缺字段或文件路径不对（默认 `~/.workbuddy/scripts/notify_config.json`）。
- **推送结果里某渠道 `unconfigured`**：该渠道必填项缺失，不是网络问题。
- **`sms` 显示 `skipped`**：付费渠道未加 `--confirm-paid`，属预期保护。
- 自动化没跑先查开机 / 客户端退出 / 联网。
- 桌面通知不弹通常是无桌面会话（锁屏/无 GUI），属预期，stdout 与 checkin.log 仍有完整记录。
