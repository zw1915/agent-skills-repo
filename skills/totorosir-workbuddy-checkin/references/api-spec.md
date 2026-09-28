# 接口与登录态规范（WorkBuddy签到助手）

本文件供 Skill 执行时参考，包含登录态文件格式、签到接口、旅行接口、字段含义、错误码、余额字段候选名，以及推送模块的接口契约。
所有接口均通过本机已登录 WorkBuddy 客户端的 `accessToken` 鉴权，**只读**登录态，绝不修改。

---

## 1. 登录态文件

由 WorkBuddy PC 客户端登录后生成，明文 JSON。

### 路径（按操作系统自动探测）

| 系统 | 路径 |
|------|------|
| Windows | `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`<br>（旧版可能在 `%APPDATA%` 同路径下） |
| macOS | `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` |
| Linux | `~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` |
| 兜底 | `~/.workbuddy/auth/workbuddy-desktop.info` |

脚本探测顺序：Windows 取 `LOCALAPPDATA` / `APPDATA` → macOS 取 `~/Library/Application Support` → Linux 取 `~/.config` → 最后兜底 `~/.workbuddy/auth`。

### 关键字段

```json
{
  "auth": {
    "accessToken": "<JWT>",
    "tokenType": "Bearer",
    "domain": "www.codebuddy.cn",
    "expiresAt": 1735689600000
  }
}
```

- `auth.accessToken`：鉴权令牌（JWT）。**任何输出都不得打印真实值**，脚本仅脱敏为 `eyJhbG...xxxx`。
- `auth.domain`：**接口域名以此为准**。实测值为 `www.codebuddy.cn`。网上文章写 `copilot.tencent.com` 会 404，切勿硬编码。
- `auth.expiresAt`：过期时间（epoch 毫秒/秒）。脚本兼容 13 位毫秒与 10 位秒；为空则跳过过期检查。

---

## 2. 签到接口

基础地址：`https://<auth.domain>/v2`

### 2.1 状态查询（只读）

```
POST /v2/billing/meter/checkin-activity-status
Authorization: Bearer <accessToken>
Content-Type: application/json
```

响应（示例）：

```json
{
  "code": 0,
  "data": {
    "today_checked_in": false,
    "streak_days": 12,
    "daily_credit": 100,
    "total_credits": 1340
  }
}
```

> 实测余额字段是 **`total_credits`（复数）**；早期脚本只认单数 `total_credit`，导致 `balance` 恒为 `null`。详见第 5 节候选名清单。

已签到的判定（脚本兼容多种形态）：
- `today_checked_in == true`
- `data.today_checked_in == true`
- `code == "10001"`

### 2.2 领取签到

```
POST /v2/billing/meter/daily-checkin
Authorization: Bearer <accessToken>
Content-Type: application/json
```

成功响应：

```json
{
  "code": 0,
  "credit": 100,
  "streak_days": 13,
  "data": { "credit": 100, "daily_credit": 100 }
}
```

已签到响应（幂等，非错误）：

```json
{
  "code": 10001,
  "msg": "今天已签到，请明天再来"
}
```

---

## 3. 派猫猫旅行接口

基础地址：`https://www.workbuddy.cn`

> **与签到不是同一个域名，且路径不带 `/v2` 前缀**——这是最容易踩的坑。
> 用登录态里的 `auth.domain`（`www.codebuddy.cn`）或误加 `/v2` 都会 404。
> 旅行接口仅需 Bearer Token，**无需** Turing Shield 设备指纹。

### 3.1 旅行状态（只读）

```
GET /activity/growth/buddy/travel/status
Authorization: Bearer <accessToken>
```

响应示例：

```json
{
  "code": 0,
  "data": {
    "state": "idle",
    "location": { "id": 1, "name": "咖啡馆" },
    "reward_credit": 0,
    "arrive_at": 1757500000,
    "server_now": 1757490000,
    "daily_limit_reached": false,
    "record_id": 123
  }
}
```

状态三态：

| `state` | 含义 | 可执行动作 |
|---|---|---|
| `idle` | 空闲 | 未达每日上限时可 `depart` |
| `traveling` | 旅行中 | 无；用 `arrive_at - server_now` 算到达倒计时 |
| `arrived` | 已到达，待领取 | 可 `claim` 领取积分 |

### 3.2 领取旅行积分（写）

```
POST /activity/growth/buddy/travel/claim
Authorization: Bearer <accessToken>
Content-Type: application/json

{}
```

成功：`{"code":0,"data":{"reward_credit":8}}`。
无可领取时服务端返回非 0 码，脚本如实上报、绝不编造结果。

### 3.3 派出 Buddy（写）

```
POST /activity/growth/buddy/travel/depart
Authorization: Bearer <accessToken>
Content-Type: application/json

{"location_id": 1}
```

成功：`{"code":0,"data":{"location":{"id":1,"name":"咖啡馆"},"arrive_at":1757500000}}`。

### 3.4 可选地点（只读）

```
GET /activity/growth/buddy/travel/config
```

返回 `data.locations`（`id` / `name` / `duration_hours_min` / `duration_hours_max` / `reward_credit_min` / `reward_credit_max`）。
实测四个地点为**咖啡馆 / 商场店铺 / 健身房 / 古镇客栈**，时长与积分区间完全相同（随机 1-4 小时、5-10 积分），**收益无差异**，`location_id` 缺省时随机选一个。

### 3.5 派遣前置检查（硬规则）

调用 `depart` 前必须先读 `status` 并同时满足：

1. `state == "idle"`
2. `daily_limit_reached` 为假

任一不满足即跳过派遣，**不发任何写请求**。

---

## 4. 错误码 / 状态码对照

| HTTP | code | 含义 | 脚本处理 |
|------|------|------|----------|
| 200 | 0 | 领取成功 | `action=clicked`，展示积分/连续天数 |
| 400 | 10001 | 当天已签 | `action=skip_already_signed`（幂等跳过，非失败） |
| 非 2xx | — | 网络/服务端错误 | 读取响应体；若含"已签到"仍判为已签，否则 `status=error` |
| — | — | `accessToken` 缺失/过期 | `status=error`，提示重新登录客户端 |

> 脚本对非 2xx 也解析响应体，避免把"已签到 400"误判为异常。
>
> **旅行接口的降级约定**：只读接口（`status` / `config`）失败时置 `travel.available=false` 并静默跳过，
> 绝不改变签到结论；写接口（`claim` / `depart`）返回非 0 码时，把服务端 `msg` 如实记入
> `travel.auto_log`，同样不影响签到状态与退出码。

---

## 5. 积分余额字段候选名

不同版本接口返回的余额字段名不统一，脚本按以下候选名 + 嵌套层级兜底提取，写入结果 `balance` 字段（找不到则返回 None，不影响签到）：

- 候选键（**注意复数形态**，接口实测返回的是 `total_credits`（复数），早期版本脚本只认单数导致余额恒为空）：
  `total_credits` / `total_credit` / `total_credit_balance` / `credits` / `total_points` / `points_balance` /
  `credit_balance` / `balance` / `remain_credit` / `remain_credits` / `remain` / `score` / `integral` /
  `totalCredits` / `totalCredit` / `pointsBalance` / `balanceCredit`
- 候选层级：`（顶层）` / `data` / `result` / `data.result`

---

## 6. 消息推送模块接口（`scripts/push_message.py`，可选，密钥仅本地）

仅当用户主动配置 `notify_config.json` 时，才会向对应渠道发请求。凭据不进入脚本或技能目录。
模块**纯 Python 标准库**实现（urllib / json / hmac / hashlib / smtplib / subprocess），可独立运行。

### 6.1 渠道注册表与构造器

```python
CHANNELS = {"dingtalk": build_dingtalk, "feishu": build_feishu, "wecom": build_wecom,
            "wechat": build_wechat, "email": build_email, "sms": build_sms, "qq": build_qq,
            "slack": build_slack, "telegram": build_telegram, "bark": build_bark,
            "webhook": build_webhook}          # 11 个走网络/邮件的渠道
SUPPORTED   = [...11 项..., "system"]          # 对外宣称支持的 12 类
ZERO_CONFIG = {"system"}                       # 无需任何凭据
PAID_CHANNELS = {"sms"}                        # 付费渠道，需 confirm_paid=True 才放行
```

`system` 不进入 `CHANNELS`，由 `send_one` 开头短路处理（`if channel == "system": return send_system(...)`）。

每个 `build_<channel>(cfg, msg)` 统一返回下列两种形态之一，由 `send_one` 分发：

| 返回 | 含义 |
|---|---|
| `("http", url, payload, headers)` | POST JSON 到 `url`（`headers` 可为 `None`） |
| `("smtp", cfg, msg)` | 走 `smtplib`（仅 `email`） |

必填项缺失时抛 `ConfigError`，由上层转为 `unconfigured`，**不发起任何网络请求**。
未知渠道名由 `send_one` 直接返回 `failed`（`detail="未知渠道 X"`）。

### 6.2 配置归一化

`normalize_channels(cfg)` 把两种写法**按渠道合并**（同渠道以新结构为准，旧字段只补齐新结构里没有的渠道）：

- 新结构：`{"channels": {"dingtalk": {"webhook": ...}, "email": {...}}}`
- 旧扁平字段（向后兼容，仅微信三通道）：
  - `wecom_webhook` → `wecom.webhook`
  - `pushplus_token` → `wechat.pushplus_token`
  - `bark_url` → `bark.server` + `bark.device_key`（由 `_split_bark_url` 自动拆分）

**为什么是合并而不是二选一**：若写成「出现 `channels` 就整体忽略旧字段」，老用户只想新增一个渠道（如在 `channels` 里加 `email`）时，原有企业微信 / PushPlus / Bark 推送会静默失效。合并语义避免了这类回归。

### 6.3 渠道接口清单（与实现一一对应）

| 渠道 | 地址 | 形态与要点 |
|------|------|------|
| `dingtalk` | 用户填的 `webhook` | POST markdown；填 `secret` 时追加 `&timestamp=<毫秒>&sign=<HMAC-SHA256>` |
| `feishu` | 用户填的 `webhook` | POST `msg_type=text`；填 `secret` 时追加 `timestamp=<秒>&sign=` |
| `wecom` | 用户填的 `webhook`（`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<KEY>`） | POST markdown，正文前缀 `# 标题`；填 `secret` 时追加毫秒级签名 |
| `wechat` | `https://www.pushplus.plus/send` | POST，`token` + `template`（markdown/html） |
| `email` | `smtp_host:smtp_port` | `smtplib`；默认 465 + SSL，`smtp_mode=starttls` 可切；`smtp_pass` 为授权码 |
| `sms` | 用户填的 `url` + `payload_template` | POST（**付费**，默认拦截）；支持 `headers` |
| `qq` | 用户填的 `url` | 直接复用 `build_webhook` |
| `slack` | 用户填的 `webhook_url` | POST，正文 `*标题*\n正文` |
| `telegram` | `https://api.telegram.org/bot<token>/sendMessage` | POST，`chat_id` + `text` |
| `bark` | `<server>/push` | POST `{"device_key","title","body"}`；也接受整条 `bark_url`（自动拆分） |
| `webhook` | 用户填的 `url` | POST；`payload_template` 支持 `{{title}}` / `{{content}}` 占位符；可选 `headers` |
| `system` | 本地 `~/.workbuddy/scripts/notifications.jsonl` + 桌面 toast | 零配置、离线可用，不联网 |

### 6.4 对外函数

| 函数 | 作用 |
|---|---|
| `load_raw_config(path=None)` | 读取配置，回退顺序：`path` → 环境变量 `WORKBUDDY_CHECKIN_PUSH_CONFIG` → 默认 `~/.workbuddy/scripts/notify_config.json`；均不存在返回 `None` |
| `normalize_channels(cfg)` | 归一化新旧两种结构 |
| `resolve_channels(cfg, requested=None)` | 决定本次实际目标渠道集合（`requested` 非空则覆盖） |
| `send_one(channel, cfg, msg, timeout)` | 发单渠道，返回 `{"channel","status",...}` |
| `send_message(title, content, channels=None, content_type="markdown", confirm_paid=False, timeout=10, config_path=None)` | 主入口，聚合并返回 `{"ok": bool, "results": [...]}` |
| `ready_channels(config_path=None)` | 只读列出 `ready` / `unconfigured`，供 `--diagnose` 使用（不联网） |
| `write_sample(config_path=None)` | 生成双结构配置模板 |
| `hmac_sign(secret, timestamp)` | 钉钉 / 飞书 / 企业微信加签 |
| `desktop_toast(title, content)` | 跨平台桌面通知（`system` 渠道使用） |

### 6.5 结果状态与错误边界（硬约定）

| `status` | 含义 |
|---|---|
| `success` | 发送成功（HTTP 2xx，或邮件已投递） |
| `failed` | 发送失败（网络异常 / 凭据失效 / URL 非法），`detail` 为该渠道异常摘要（截断 500 字符） |
| `unconfigured` | 必填项缺失（`ConfigError`），**未发起请求** |
| `skipped` | 主动跳过：付费渠道未确认、`enabled=false`、未配置任何渠道时的 `<none>` 占位 |

- **单渠道失败隔离**：任一渠道异常只记入该条 `results`，`try/except` 包裹，绝不中断其他渠道，也绝不改变签到 `status` 与退出码。
- **判定顺序**（`send_message` 内，务必照此理解结果）：
  1. 逐个渠道判「是否已配置」——`ch in configured or ch in ZERO_CONFIG` 才进入发送目标；显式请求但未配置的 → 直接记 `unconfigured`（**未发起请求**）。
  2. 再对付费渠道做闸门——目标里含 `PAID_CHANNELS` 且 `confirm_paid=False` → 记 `skipped`，并从目标中剔除。
  3. 最后逐个发送，异常统一转 `failed`。
  因此：**未配置的 `sms` 会显示 `unconfigured`，已配置但未加 `--confirm-paid` 才显示 `skipped`**。
- **凭据脱敏**：`detail` 只含渠道名与错误摘要，**永不回显 webhook / token / 密码**。
- 配置文件不存在 → 返回 `{"ok": True, "skipped": True, "results": [{"channel":"<none>","status":"skipped",...}]}`；`enabled=false` 且未显式指定渠道时同样静默跳过。主脚本对这类返回静默处理，用户无感知。
- `ok` 语义：所有 `results` 均为 `success` 才为 `True`；主脚本**不据此改变签到退出码**。

配置字段与获取方式见同目录下的 `examples.md`（不要在本文件里用加载式引用）。
