---
name: browser-skill-network-diagnosis
description: Diagnose BrowserSkill agent-window network failures when automating dApps or websites. Use when bsk Chrome cannot load pages, returns ERR_CONNECTION_RESET, Region not Supported, or wallet-extension tunnels fail. Guides through shell reachability tests, system proxy checks, regional block verification, and decides whether to fix proxy, switch platforms, or fall back to manual execution.
agent_created: true
---

# BrowserSkill 网络阻塞诊断

## 触发条件

当 BrowserSkill 的 agent 窗口出现以下任一症状时使用本 skill：

- `net::ERR_CONNECTION_RESET` 或页面长期空白/超时。
- 页面能加载但显示 `Region not Supported` / `This service is not available in your region`。
- 钱包扩展弹窗连接失败，提示 `ERR_TUNNEL_CONNECTION_FAILED`。
- dApp 部分功能可用，但钱包连接、OAuth 授权或特定域名请求无法完成。

## 诊断流程

### 1. 确认 shell 层网络是否可达

用 Bash 执行 curl，确认当前环境是否存在可用出口：

```bash
curl -sS -m 15 -o /dev/null -w "status:%{http_code}\n" https://target-site/
env | grep -iE "HTTP_PROXY|HTTPS_PROXY"
```

- 返回 `200`/`302`/`403`/`404` 等 HTTP 码 → shell 层网络可达，存在可用出口。
- 返回 `timeout`/`connection refused` → shell 自身受限，先让用户解决本机网络或 VPN。

### 2. 检查系统代理与 bsk Chrome 的关系

Windows 上，bsk 启动的 Chrome 会读取 `HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings`。

- `bsk` CLI **不支持**通过参数给 Chrome 注入 `--proxy-server`，只能通过修改系统代理影响 agent 窗口。
- 修改系统代理前必须告知用户：这会同时影响用户主 Chrome/Edge 的网络出口。

用 PowerShell 读写该注册表键：

```powershell
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Get-ItemProperty -Path $key -Name ProxyEnable, ProxyServer
```

### 3. 区分三类典型失败

#### A. 直连被沙箱/防火墙阻挡

- 现象：agent 窗口 navigate 超时/RESET，shell curl 返回 200。
- 验证：设系统代理到可用本地代理，重启 bsk session 后再测。
- 处理：若代理后网络恢复，继续排查是否地区封锁或隧道失败。

#### B. 代理出口被地区封锁

- 现象：设代理后页面能加载，但显示 `Region not Supported`。
- 处理：撤销系统代理，避免影响主 Chrome；该平台改由用户主浏览器手动执行，或换其他不被封锁的平台。

#### C. 代理对特定域名隧道失败

- 现象：钱包扩展连接 `keys.coinbase.com`、MetaMask 后端或 OAuth 服务时返回 `ERR_TUNNEL_CONNECTION_FAILED`。
- 处理：说明该代理不是干净全局出口，不能支撑依赖钱包扩展/OAuth 的 dApp 自动化。停止在该 agent 窗口继续尝试此类登录，改为主浏览器手动或换代理节点。

#### D. 用户标签页无法被驱动（借入确认 UI 无法显示）

- 现象：`bsk navigate --tab-id <用户标签>` 报错 `operation denied by the Agent Window sandbox`，提示必须先 `bsk tab borrow`；但 `bsk tab borrow <tab-id>` 报错 `the browser could not display a confirmation request` / `Invalid borrow confirmation response`。
- 根因：当前 sandbox 环境无法向用户浏览器呈现 borrow 确认弹窗，用户无法点"允许"，借入流程永远完成不了。
- 推论：**agent 窗口是 bsk 唯一可操控的视图**，而它的网络出口（无论系统代理开关）对 Galxe/Layer3 等平台始终被限区/403。因此任何"地区封锁类 dApp"都既不能被 agent 窗口访问、也不能借用户主窗口驱动 → 对该 agent 完全不可自动化。
- 处理：这类平台直接判为"需用户主浏览器手动执行"，不再尝试借入/导航。

### 4. 决策与下一步

| 症状组合 | 根因 | 建议 |
| --- | --- | --- |
| 直连超时，代理后能加载 | 沙箱/防火墙需代理 | 用代理，但需继续测地区/隧道 |
| 代理后 `Region not Supported` | 代理出口 IP 被地区封锁 | 撤销代理，主浏览器手动或换平台 |
| 代理后 `ERR_TUNNEL_CONNECTION_FAILED` | 代理对特定域名隧道失败 | 撤销代理，该 dApp 改手动 |
| 钱包连接弹窗在主 Chrome 而非 agent 窗口 | 用户点错扩展实例 | 明确提示用户在 agent 窗口的扩展弹窗确认 |
| `tab borrow` 报 confirmation 无法显示 | 沙箱无法呈现借入确认 UI | 放弃驱动用户标签，判为不可自动化 |
| 目标 dApp 直连/代理/借入均不可用 | agent 窗口 + 用户标签双路皆死 | 放弃 agent 自动化，AI 负责清单/追踪，用户手动执行 |

## 执行原则

- 钱包连接、OAuth 授权、助记词/私钥相关操作必须由用户本人确认，不得代点。
- 每次修改系统代理前后都记录状态，任务结束后按用户要求恢复直连。
- 把每次尝试的平台、代理状态、错误码和结论写入工作区 memory，避免同一 session 内重复踩坑。
