#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy签到助手（每日自动签到脚本，接口直签，无需 GUI 点击 / OCR）

原理：
  1. 读取本机 WorkBuddy 登录态文件中的 accessToken（只读，绝不修改登录态）
  2. 查询今日签到状态  POST {base}/billing/meter/checkin-activity-status
  3. 若今日未签到，调用 POST {base}/billing/meter/daily-checkin 领取
  4. 已签到 / 接口返回 code=10001 则安全跳过，不做重复领取
  5. 派猫猫旅行（默认随签到一起跑全自动闭环「先领后派」）：
     查询 https://www.workbuddy.cn/activity/growth/buddy/travel/status
     已到达(arrived) → POST .../travel/claim 领取旅行积分
     空闲(idle)且未达每日上限 → POST .../travel/depart 派出 Buddy
     旅行中(traveling) → 不派遣，仅展示到达倒计时
     注意：旅行接口域名是 www.workbuddy.cn（与签到的 www.codebuddy.cn 不同），
           且路径不带 /v2 前缀。

失败推送（可选）：
  若签到结果为 status!=ok，会读取本地配置文件
  ~/.workbuddy/scripts/notify_config.json（若存在），向已配置的渠道推送失败提醒。
  支持 12 类渠道：企业微信/钉钉/飞书/微信(PushPlus)/邮件/短信/QQ/Slack/Telegram/Bark/通用 Webhook/系统通知。
  配置缺失的渠道自动跳过，单渠道失败不影响其他渠道，不影响签到。

成功推送（可选，默认关闭）：
  在 notify_config.json 中设置 "success_notify": true 后，
  签到成功（本次新签到 / 今日已签跳过）也会向已配置渠道推送一条播报。
  默认不开启，保持「静默无打扰」；仅失败时提醒。
  推送逻辑由 scripts/push_message.py 提供（接口/配置项对齐 totorosir-push-message 技能）。

安全约定：
  - 不打印 token / accessToken / refreshToken（任何输出都不含敏感凭据）
  - 不修改本机登录态文件
  - 推送密钥只存在于本地 notify_config.json，永不进入脚本或技能目录
  - 异常只记录失败原因，最多重试 1 次，不无限重试

用法：
  python workbuddy_checkin.py                  # 签到 + 派猫猫旅行全自动闭环（默认）
  python workbuddy_checkin.py --no-travel      # 只签到，跳过旅行（最快）
  python workbuddy_checkin.py --check-only     # 仅查询状态（只读，不领取、不写旅行）
  python workbuddy_checkin.py travel           # 只查派猫猫旅行状态（只读）
  python workbuddy_checkin.py travel --travel-auto      # 只跑旅行闭环（不签到）
  python workbuddy_checkin.py --travel-auto    # 显式开启旅行闭环（默认已开）
  python workbuddy_checkin.py --location N     # 指定派遣地点（1-4，缺省随机）
  python workbuddy_checkin.py --no-notify      # 跳过全部推送与桌面通知（调试用）
  python workbuddy_checkin.py --diagnose       # 环境自检（Python/登录态/网络/桌面会话/推送配置）
  python workbuddy_checkin.py --init-config    # 生成 notify_config.json.example 模板
  python workbuddy_checkin.py --help           # 显示帮助
  python workbuddy_checkin.py --version        # 显示版本
  成功推送开关见 ~/.workbuddy/scripts/notify_config.json 的 "success_notify"
"""

import sys

# Python 版本守卫：太旧时给出友好提示，而不是抛出一堆堆栈
if sys.version_info < (3, 6):
    sys.stderr.write(
        "WorkBuddy签到助手：需要 Python 3.6+，当前为 %s。\n"
        "请安装 Python 3.8+（https://www.python.org/downloads/，勾选 Add to PATH），\n"
        "或直接使用 WorkBuddy 自带的托管 Python（~/.workbuddy/binaries/python）。\n"
        % sys.version.split()[0])
    sys.exit(2)

import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# 多渠道消息推送模块（接口/配置项对齐 totorosir-push-message 技能，自包含、零依赖）
try:
    import push_message  # 与本脚本同目录
except Exception:  # noqa: BLE001 - 模块缺失时回落到静默，不影响签到
    push_message = None  # type: ignore

# ---- 配置 ----
def _auth_candidates():
    """按操作系统返回 WorkBuddy 登录态文件候选路径，依次探测。"""
    home = os.path.expanduser("~")
    cands = []
    if sys.platform.startswith("win"):
        for env in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env, "")
            if base:
                cands.append(os.path.join(
                    base, "CodeBuddyExtension", "Data", "Public",
                    "auth", "workbuddy-desktop.info"))
    elif sys.platform == "darwin":
        cands.append(os.path.join(
            home, "Library", "Application Support", "CodeBuddyExtension",
            "Data", "Public", "auth", "workbuddy-desktop.info"))
    else:  # linux / 其他类 Unix
        cands.append(os.path.join(
            home, ".config", "CodeBuddyExtension", "Data", "Public",
            "auth", "workbuddy-desktop.info"))
    # 兜底：便携版 / 未知布局（与 ~/.workbuddy 同根）
    cands.append(os.path.join(
        home, ".workbuddy", "auth", "workbuddy-desktop.info"))
    return [p for p in cands if p]
STATUS_PATH = "/billing/meter/checkin-activity-status"
CHECKIN_PATH = "/billing/meter/daily-checkin"
HTTP_TIMEOUT = 10
MAX_RETRY = 1
VERSION = "3.0.0"

# 推送渠道覆盖（由命令行 --push-channels 设定，None=用配置里全部已就绪渠道）
_PUSH_CHANNELS = None
_PUSH_CONFIRM_PAID = False

# ---- 派猫猫旅行配置 ----
# 关键：旅行接口与签到接口不是同一个域名，且路径不带 /v2 前缀，写错一律 404。
TRAVEL_BASE = "https://www.workbuddy.cn"
TRAVEL_STATUS_PATH = "/activity/growth/buddy/travel/status"   # GET  旅行状态
TRAVEL_CONFIG_PATH = "/activity/growth/buddy/travel/config"   # GET  可选地点
TRAVEL_CLAIM_PATH = "/activity/growth/buddy/travel/claim"     # POST 领取旅行积分
TRAVEL_DEPART_PATH = "/activity/growth/buddy/travel/depart"   # POST 派出 Buddy
TRAVEL_STATE_TEXT = {
    "idle": "空闲（可派遣）",
    "traveling": "旅行中",
    "arrived": "已到达，待领取",
}
# 失败推送配置（含密钥，仅本地，不入库）
NOTIFY_CONFIG = os.path.join(os.path.expanduser("~"),
                             ".workbuddy", "scripts", "notify_config.json")


def find_auth_file():
    for p in _auth_candidates():
        if os.path.isfile(p):
            return p
    return None


def _check_expiry(auth):
    """登录态已过期时给出友好提示（只读取 expiresAt，绝不打印 token）。"""
    raw = auth.get("expiresAt")
    if not raw:
        return  # 无过期字段则跳过检查
    try:
        exp = int(raw)
    except (TypeError, ValueError):
        return
    # 兼容 epoch 毫秒（13 位）/ 秒（10 位）
    if exp > 10 ** 11:
        exp = exp / 1000.0
    if exp <= time.time():
        expire_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
        raise RuntimeError(
            "登录态已过期（过期时间 %s），请重新登录 WorkBuddy 客户端后再试" % expire_str)


def load_token(auth_path):
    with open(auth_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    auth = data.get("auth", {})
    token = auth.get("accessToken")
    domain = auth.get("domain") or "www.codebuddy.cn"
    if not token:
        raise RuntimeError("登录态文件中未找到 accessToken（可能未登录或登录态已失效）")
    _check_expiry(auth)
    return token, domain


def api_call(base, path, token, payload=None, method="POST"):
    url = base + path
    # GET 且未显式传 payload 时不发请求体；其余情况按 JSON 编码发送
    if method == "GET" and payload is None:
        data = None
    else:
        data = json.dumps(payload if payload is not None else {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "WorkBuddy-Checkin-Script/1.1")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as e:
        # 非 2xx 也读取响应体（如已签到返回的 HTTP 400 / code=10001）
        try:
            body = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(body)
            except json.JSONDecodeError:
                return e.code, {"raw": body}
        except Exception:
            return e.code, {"raw": ""}


def mask_token(t):
    if not t:
        return "<empty>"
    return t[:6] + "..." + t[-4:]


def _extract_balance(*bodies):
    """从接口响应中尽力提取「积分余额」（total / balance 类字段）。

    不同版本接口返回的余额字段名不统一，这里按候选名 + 嵌套层级兜底提取，
    找不到则返回 None（不影响签到主流程）。
    """
    candidates = (
        "total_credits", "total_credit", "total_credit_balance", "total_points",
        "points_balance", "credit_balance", "balance", "remain_credit",
        "remain_credits", "remain", "score", "credits",
        "integral", "totalCredit", "totalCredits", "pointsBalance",
        "balanceCredit",
    )
    sections = ("", "data", "result", "data.result")
    for body in bodies:
        if not isinstance(body, dict):
            continue
        for sec in sections:
            node = body
            for part in sec.split(".") if sec else []:
                if isinstance(node, dict):
                    node = node.get(part)
                else:
                    node = None
                    break
            if not isinstance(node, dict):
                # 顶层（sec 为空字符串）直接看 body 本身
                node = body if sec == "" else None
            if not isinstance(node, dict):
                continue
            for k in candidates:
                v = node.get(k)
                if isinstance(v, (int, float)):
                    return v
    return None


# ---------------- 消息推送（多渠道，见 push_message.py） ----------------

def load_notify_config():
    """读取本地推送配置（原始结构，可能含新 channels 或旧扁平字段）。

    仅用于判定 enabled / success_notify 等顶层开关；实际渠道解析交给 push_message。
    """
    if not os.path.isfile(NOTIFY_CONFIG):
        return None
    try:
        with open(NOTIFY_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return None
        return cfg
    except Exception:
        return None


def _push_failure(res):
    """签到失败时，按本地配置推送提醒；配置缺失或推送模块不可用时静默跳过。

    通过 push_message.send_message 调度多渠道（钉钉/飞书/企业微信/PushPlus/Bark/邮件/…），
    单渠道失败不影响其他渠道，也不影响签到结果与退出码。
    """
    if push_message is None:
        return
    now = time.strftime("%Y-%m-%d %H:%M:%S")  # 本机时区（北京时间）
    msg = res.get("msg", "未知原因")
    auth_file = res.get("detail", {}).get("auth_file", "未知")
    title = "⚠️ WorkBuddy签到助手 · 签到失败"
    content = (
        "### ⚠️ WorkBuddy签到助手 · 签到失败\n\n"
        "> **时间**：%s\n\n"
        "> **原因**：%s\n\n"
        "> **登录态文件**：%s\n\n"
        "> **处理建议**：请检查 WorkBuddy 是否已登录、电脑是否联网、09:00 前后是否开机且客户端未退出；"
        "必要时重启客户端刷新登录态后，可手动再跑一次脚本。\n"
    ) % (now, msg, auth_file)
    try:
        result = push_message.send_message(
            title, content, channels=_PUSH_CHANNELS,
            content_type="markdown", confirm_paid=_PUSH_CONFIRM_PAID)
        res["detail"]["notify"] = result.get("results", [])
    except Exception:
        pass  # 推送失败绝不影响签到


def _push_success(res):
    """签到成功（新签到 / 今日已签跳过）时，按本地配置推送播报。

    仅当 notify_config.json 中 success_notify=true 时才推送；否则静默。
    通过 push_message.send_message 调度多渠道；失败时静默，不影响签到。
    """
    if push_message is None:
        return
    cfg = load_notify_config()
    if not cfg or cfg.get("enabled") is False:
        return
    if not cfg.get("success_notify"):
        return

    now = time.strftime("%Y-%m-%d %H:%M:%S")  # 本机时区（北京时间）
    action = res.get("action")
    # 仅对明确的成功态推送（新签到 / 今日已签跳过）；其他态（失败 / 纯查询）不推
    if action not in ("clicked", "skip_already_signed"):
        return
    msg = res.get("msg", "")
    points = res.get("points")
    streak = res.get("detail", {}).get("streak_days")
    balance = res.get("balance")

    if action == "skip_already_signed":
        title = "✅ WorkBuddy签到助手 · 今日已签"
        content = (
            "### ✅ WorkBuddy签到助手 · 今日已签\n\n"
            "> **时间**：%s\n\n"
            "> **状态**：今日已签到，无需重复领取（幂等保护）\n\n"
            "> **说明**：系统定时任务 / 技能已正常执行，无需处理。\n"
        ) % now
    else:
        title = "✅ WorkBuddy签到助手 · 签到成功"
        lines = (
            "### ✅ WorkBuddy签到助手 · 签到成功\n\n"
            "> **时间**：%s\n\n"
            "> **状态**：%s\n"
        ) % (now, msg)
        if points:
            lines += "> **积分**：+%s\n\n" % points
        if streak:
            lines += "> **连续天数**：第 %s 天\n\n" % streak
        if balance is not None:
            lines += "> **当前积分余额**：%s\n\n" % balance
        lines += "> **说明**：系统定时任务 / 技能已正常执行，无需处理。\n"
        content = lines

    try:
        result = push_message.send_message(
            title, content, channels=_PUSH_CHANNELS,
            content_type="markdown", confirm_paid=_PUSH_CONFIRM_PAID)
        res["detail"]["notify_success"] = result.get("results", [])
    except Exception:
        pass  # 推送失败绝不影响签到


def notify_system(res):
    """签到完成后弹出操作系统级桌面通知（toast / 气球提示），展示结果 + 积分余额。

    跨平台兼容 Windows / macOS / Linux；best-effort、非阻塞、失败静默，
    绝不影响签到结果与退出码。受 --no-notify 一并抑制（与消息推送调试开关一致）。
    """
    try:
        status = res.get("status")
        title = "WorkBuddy签到助手"
        if status == "error":
            body = "签到失败：" + str(res.get("msg", ""))
        else:
            body = str(res.get("msg", "签到完成"))
            bal = res.get("balance")
            if bal is not None:
                body += " ｜ 当前积分余额：" + str(bal)
        _system_toast(title, body)
    except Exception:
        pass  # 通知失败绝不影响签到


def _system_toast(title, body):
    """按操作系统分发到原生命令；任何异常一律忽略。"""
    plat = sys.platform
    try:
        if plat == "darwin":
            msg = body.replace('"', "'")
            subprocess.run(
                ["osascript", "-e",
                 'display notification "%s" with title "%s"' % (msg, title)],
                timeout=5, check=False,
            )
        elif plat.startswith("linux"):
            subprocess.run(["notify-send", title, body], timeout=5, check=False)
        elif plat == "win32":
            _win_toast(title, body)
    except Exception:
        pass


def _win_toast(title, body):
    """Windows：用 .NET 气球提示（非阻塞、约 5s）。PowerShell 不可用或被策略拦截时静默跳过。"""
    safe_title = title.replace("'", "''")
    safe_body = body.replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "Add-Type -AssemblyName System.Drawing;"
          "$n=New-Object System.Windows.Forms.NotifyIcon;"
          "$n.Icon=[System.Drawing.SystemIcons]::Information;"
          "$n.Visible=$true;"
          "$n.ShowBalloonTip(5000,'%s','%s','Info');"
          "Start-Sleep -Milliseconds 150;"
          "$n.Dispose()") % (safe_title, safe_body)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        timeout=10, check=False,
    )


# ---------------- 主流程 ----------------

def _do_checkin(base, token, check_only):
    """执行签到主流程（查询状态 → 必要时领取）。返回结构化结果片段。"""
    result = {"status": "unknown", "action": None, "points": None,
              "balance": None, "msg": "", "detail": {}}
    attempt = 0
    last_err = None
    while attempt <= MAX_RETRY:
        attempt += 1
        try:
            # 1) 查询今日状态
            st_code, st_body = api_call(base, STATUS_PATH, token)
            result["detail"]["status_http"] = st_code
            result["detail"]["status_resp"] = st_body
            # 从状态响应中提前提取积分余额（领取分支会用领取响应再覆盖一次）
            result["balance"] = _extract_balance(st_body)
            result["detail"]["balance"] = result["balance"]

            # 判断是否已签到：兼容多种返回形态
            today_signed = False
            if isinstance(st_body, dict):
                if st_body.get("today_checked_in") is True:
                    today_signed = True
                elif st_body.get("data", {}).get("today_checked_in") is True:
                    today_signed = True
                elif str(st_body.get("code")) == "10001":
                    today_signed = True

            if check_only:
                bal_txt = ("，当前积分余额 %s" % result["balance"]) if result.get("balance") is not None else ""
                result.update(
                    status="ok",
                    action="skip_check_only",
                    msg="状态查询成功（未执行领取）" + bal_txt,
                )
                result["detail"]["today_signed"] = today_signed
                return result

            if today_signed:
                bal_txt = ("，当前积分余额 %s" % result["balance"]) if result.get("balance") is not None else ""
                result.update(status="ok", action="skip_already_signed",
                              msg="今日已签到，无需重复领取" + bal_txt)
                return result

            # 2) 领取签到
            ck_code, ck_body = api_call(base, CHECKIN_PATH, token)
            result["detail"]["checkin_http"] = ck_code
            result["detail"]["checkin_resp"] = ck_body

            if isinstance(ck_body, dict):
                code = str(ck_body.get("code", ""))
                msg = ck_body.get("msg") or ck_body.get("message") or ""
                data = ck_body.get("data") if isinstance(ck_body.get("data"), dict) else {}
                # 已签/重复提示（幂等保护）
                if code == "10001" or "已签到" in msg or "今天已签到" in msg:
                    result.update(status="ok", action="skip_already_signed",
                                  msg="今日已签到（接口返回 code=10001）")
                    return result
                # 领取成功判定：HTTP 2xx 且业务码为成功（兼容无 code / code=0 / code=200）
                success_code = code in ("", "0", "200")
                if 200 <= ck_code < 300 and success_code:
                    credit = (ck_body.get("credit") or data.get("credit")
                              or data.get("daily_credit") or data.get("today_credit"))
                    streak = ck_body.get("streak_days") or data.get("streak_days")
                    # 领取响应若带回余额则覆盖状态响应中的值
                    bbal = _extract_balance(ck_body)
                    if bbal is not None:
                        result["balance"] = bbal
                        result["detail"]["balance"] = bbal
                    bal_txt = ("，当前积分余额 %s" % result["balance"]) if result.get("balance") is not None else ""
                    result.update(status="ok", action="clicked",
                                  points=credit,
                                  msg="领取成功" + (("，+%s 积分" % credit) if credit else "") +
                                      (("，连续第 %s 天" % streak) if streak else "") + bal_txt)
                    result["detail"]["streak_days"] = streak
                    return result
                # 其余视为失败（含 2xx 但业务码异常、或非 2xx）
                result.update(status="error", action="failed",
                              msg=msg or ("HTTP %s（业务码 %s）" % (ck_code, code)))
                return result
            else:
                result.update(status="error", action="failed",
                              msg="领取接口返回非 JSON: %s" % ck_body.get("raw", "")[:200])
                return result

        except urllib.error.HTTPError as e:
            last_err = "HTTP %s: %s" % (e.code, e.reason)
        except urllib.error.URLError as e:
            last_err = "网络错误: %s" % e.reason
        except Exception as e:
            last_err = "异常: %s" % e

        # 重试前稍作等待
        if attempt <= MAX_RETRY:
            time.sleep(2)

    result.update(status="error", msg="重试 %d 次后仍失败: %s" % (MAX_RETRY, last_err))
    return result


# ---------------- 派猫猫旅行 ----------------

def _travel_get(token, path):
    """旅行只读 GET；失败 / 非 200 / 非 0 码均返回 None（静默降级，不影响签到主结果）。"""
    try:
        st, body = api_call(TRAVEL_BASE, path, token, method="GET")
        if st != 200 or not isinstance(body, dict) or body.get("code") != 0:
            return None
        return body.get("data")
    except Exception:
        return None


def _fmt_duration(seconds):
    """把秒数格式化为「X 小时 Y 分」。"""
    if seconds is None:
        return None
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours > 0:
        return "%d 小时 %d 分" % (hours, minutes)
    if minutes > 0:
        return "%d 分钟" % minutes
    return "%d 秒" % seconds


def parse_travel(status, config=None):
    """规整派猫猫旅行状态；字段缺失填 None，绝不编造。"""
    if not isinstance(status, dict):
        return {"available": False}
    locations = []
    if isinstance(config, dict) and isinstance(config.get("locations"), list):
        for loc in config["locations"]:
            if isinstance(loc, dict):
                locations.append({"id": loc.get("id"),
                                  "name": loc.get("name") or "未命名地点"})
    state = status.get("state")
    remaining = None
    if state == "traveling":
        arrive, now = status.get("arrive_at"), status.get("server_now")
        if isinstance(arrive, int) and isinstance(now, int):
            remaining = max(0, arrive - now)
    loc = status.get("location")
    return {
        "available": True,
        "state": state,
        "state_text": TRAVEL_STATE_TEXT.get(state, state),
        "location_name": loc.get("name") if isinstance(loc, dict) else None,
        "reward_credit": status.get("reward_credit"),
        "remaining_seconds": remaining,
        "remaining_text": _fmt_duration(remaining) if remaining is not None else None,
        "daily_limit_reached": status.get("daily_limit_reached"),
        "locations": locations,
    }


def travel_claim(token):
    """领取已到达旅行的积分（写接口）。无可领取时服务端返回非 0 码，如实上报。"""
    try:
        st, body = api_call(TRAVEL_BASE, TRAVEL_CLAIM_PATH, token, payload={})
    except Exception as e:
        return {"action": "failed", "success": False, "message": str(e)}
    if st == 200 and isinstance(body, dict) and body.get("code") == 0:
        data = body.get("data") or {}
        credit = data.get("reward_credit")
        return {"action": "claimed", "success": True, "reward_credit": credit,
                "message": "已领取旅行奖励 +%s 积分" % (credit if credit is not None else "?")}
    return {"action": "failed", "success": False,
            "message": (body.get("msg") if isinstance(body, dict) else None) or ("HTTP %s" % st),
            "code": body.get("code") if isinstance(body, dict) else None}


def travel_depart(token, location_id=None, locations=None):
    """派出 Buddy 旅行（写接口）。location_id 为空时从可选地点中随机。

    仅调用方确认「未达每日上限」后才应调用本函数；本函数不再重复查询状态。
    """
    chosen = location_id
    if chosen is None:
        ids = [loc.get("id") for loc in (locations or []) if loc.get("id") is not None]
        if not ids:
            return {"action": "failed", "success": False,
                    "message": "未能获取可选地点列表，已跳过派遣"}
        chosen = random.choice(ids)
    try:
        st, body = api_call(TRAVEL_BASE, TRAVEL_DEPART_PATH, token,
                            payload={"location_id": chosen})
    except Exception as e:
        return {"action": "failed", "success": False,
                "location_id": chosen, "message": str(e)}
    if st == 200 and isinstance(body, dict) and body.get("code") == 0:
        data = body.get("data") or {}
        loc = data.get("location") or {}
        return {"action": "departed", "success": True, "location_id": chosen,
                "location_name": loc.get("name"), "arrive_at": data.get("arrive_at"),
                "message": "已派出 Buddy 前往【%s】" % (loc.get("name") or ("地点 %s" % chosen))}
    return {"action": "failed", "success": False, "location_id": chosen,
            "message": (body.get("msg") if isinstance(body, dict) else None) or ("HTTP %s" % st),
            "code": body.get("code") if isinstance(body, dict) else None}


def travel_auto(token, location_id=None):
    """派猫猫旅行全自动闭环（写操作）：先领取、后派遣。

    安全约束：派遣前必须先确认 daily_limit_reached 为假，达上限绝不发写请求。
    已到达(arrived) 状态会一直保留、不会丢积分，下次运行自动补领。
    """
    log = []
    status = _travel_get(token, TRAVEL_STATUS_PATH)
    if status is None:
        return {"available": False, "success": False,
                "log": ["查询旅行状态失败，已跳过全部写操作"], "status": None}

    if status.get("state") == "arrived":
        result = travel_claim(token)
        log.append(result.get("message") or result.get("action"))
        if result.get("action") == "claimed":
            fresh = _travel_get(token, TRAVEL_STATUS_PATH)
            if fresh is not None:
                status = fresh

    if status.get("daily_limit_reached"):
        log.append("今日派遣次数已用完，跳过派遣")
    elif status.get("state") in (None, "", "idle"):
        config = _travel_get(token, TRAVEL_CONFIG_PATH) or {}
        result = travel_depart(token, location_id, config.get("locations") or [])
        log.append(result.get("message") or result.get("action"))
    else:
        log.append("Buddy 正在旅行中，无需派遣")

    final = _travel_get(token, TRAVEL_STATUS_PATH) or status
    return {"available": True, "success": True, "log": log, "status": final}


def _run_travel(token, auto=True, location_id=None):
    """收集派猫猫旅行数据；auto 为真时执行全自动闭环（先领后派）。"""
    status = _travel_get(token, TRAVEL_STATUS_PATH)
    config = _travel_get(token, TRAVEL_CONFIG_PATH)
    auto_log = None
    if auto:
        res = travel_auto(token, location_id)
        auto_log = res.get("log") or []
        if res.get("status"):
            status = res["status"]
    parsed = parse_travel(status, config)
    if auto_log is not None:
        parsed["auto_log"] = auto_log
    return parsed


def _append_travel_msg(msg, travel):
    """把旅行状态拼进主消息，便于桌面通知与日志一眼看全。"""
    parts = []
    if travel.get("state_text"):
        parts.append(travel["state_text"])
    if travel.get("location_name"):
        parts.append(travel["location_name"])
    if travel.get("state") == "traveling" and travel.get("remaining_text"):
        parts.append("还需 %s" % travel["remaining_text"])
    if travel.get("state") == "arrived" and travel.get("reward_credit") is not None:
        parts.append("可领 %s 积分" % travel["reward_credit"])
    auto_log = travel.get("auto_log") or []
    if auto_log:
        parts.append("；".join(str(x) for x in auto_log))
    if not parts:
        return msg
    tail = "派猫猫旅行：" + "，".join(parts)
    return (msg + " ｜ " + tail) if msg else tail


def run(check_only=False, do_checkin=True, travel_mode="auto", location_id=None):
    """主流程：登录态 →（可选）签到 →（可选）派猫猫旅行。

    travel_mode：
      "auto"     全自动闭环（先领后派），默认
      "readonly" 仅查询状态，不写
      "off"      跳过旅行
    """
    result = {"status": "unknown", "action": None, "points": None,
              "balance": None, "msg": "", "detail": {}}

    auth_path = find_auth_file()
    if not auth_path:
        result.update(status="error", msg="未找到本机登录态文件，请确认 WorkBuddy 已登录")
        return result

    try:
        token, domain = load_token(auth_path)
    except Exception as e:
        result.update(status="error", msg="读取登录态失败: %s" % e)
        return result

    base = "https://%s/v2" % domain
    result["detail"]["domain"] = domain
    result["detail"]["auth_file"] = auth_path
    # 仅记录 token 形态，绝不记录真实值
    result["detail"]["token_masked"] = mask_token(token)

    # ---- 签到 ----
    if do_checkin:
        ck = _do_checkin(base, token, check_only)
        result["status"] = ck.get("status", result["status"])
        result["action"] = ck.get("action")
        result["points"] = ck.get("points")
        result["balance"] = ck.get("balance")
        result["msg"] = ck.get("msg", "")
        result["detail"].update(ck.get("detail", {}))

    # ---- 派猫猫旅行 ----
    if travel_mode != "off":
        travel = _run_travel(token, auto=(travel_mode == "auto"),
                             location_id=location_id)
        result["travel"] = travel
        # 旅行接口不可用时静默降级，绝不改变签到结论
        if travel.get("available"):
            result["msg"] = _append_travel_msg(result.get("msg", ""), travel)
        if not do_checkin:
            # 纯旅行模式：整体状态由旅行结果决定
            result["status"] = "ok" if travel.get("available") else "error"
            result["action"] = "travel"
            if not travel.get("available"):
                result["msg"] = "查询派猫猫旅行状态失败（请确认已登录且网络正常）"

    return result


def write_log(res):
    """把每次运行结果追加写入脚本同目录的 checkin.log（本地核查用，不含 token）。"""
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkin.log")
        line = "%s | status=%s | action=%s | msg=%s\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"),
            res.get("status"), res.get("action"), res.get("msg"))
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # 写日志失败绝不影响签到


# ---------------- 环境自检与配置模板 ----------------

def _has_desktop_session():
    """best-effort 探测当前是否存在桌面图形会话（影响系统通知能否弹出）。

    探测失败或无法确定时返回 "unknown"，绝不影响签到主流程。
    """
    try:
        if sys.platform.startswith("win"):
            # SM_REMOTESESSION：1=远端会话（通常为无桌面/服务态），0=本地控制台
            try:
                import ctypes
                return "yes" if ctypes.windll.user32.GetSystemMetrics(0x1000) == 0 else "remote/no"
            except Exception:
                return "unknown"
        elif sys.platform == "darwin":
            # macOS 桌面环境一般存在；无法可靠区分锁屏，保守返回 yes
            return "yes"
        else:
            # Linux/类 Unix：有 $DISPLAY 或 $WAYLAND_DISPLAY 通常代表有桌面
            if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                return "yes"
            return "no"
    except Exception:
        return "unknown"


def diagnose():
    """环境自检：检查 Python / 登录态 / 网络 / 桌面会话 / 推送配置。

    只读、不触发任何签到请求，便于用户首次安装后快速确认「能不能用」。
    返回结构化 dict，由 main() 以 JSON 打印。
    """
    report = {"version": VERSION, "python": {}, "auth": {}, "network": {}, "desktop": {}, "notify_config": {}}

    # 1) Python 版本
    report["python"] = {
        "version": sys.version.split()[0],
        "ok": sys.version_info >= (3, 6),
        "note": "" if sys.version_info >= (3, 6) else "低于 3.6，请升级 Python 或改用 WorkBuddy 托管 Python",
    }

    # 2) 登录态文件
    auth_path = find_auth_file()
    if auth_path:
        report["auth"]["found"] = True
        report["auth"]["path"] = auth_path
        try:
            token, domain = load_token(auth_path)
            report["auth"]["token_present"] = True
            report["auth"]["domain"] = domain
            report["auth"]["expired"] = False
        except Exception as e:
            report["auth"]["token_present"] = False
            report["auth"]["error"] = str(e)
            report["auth"]["expired"] = ("过期" in str(e))
    else:
        report["auth"]["found"] = False
        report["auth"]["hint"] = "未找到登录态文件，请先登录 WorkBuddy 客户端"

    # 3) 网络连通性（DNS 解析 best-effort）
    domain = report["auth"].get("domain") or "www.codebuddy.cn"
    try:
        ip = socket.gethostbyname(domain)
        report["network"]["dns_ok"] = True
        report["network"]["host"] = domain
        report["network"]["resolved_ip"] = ip
    except Exception as e:
        report["network"]["dns_ok"] = False
        report["network"]["host"] = domain
        report["network"]["error"] = str(e)

    # 4) 桌面会话（影响系统通知弹窗）
    report["desktop"]["session"] = _has_desktop_session()
    report["desktop"]["note"] = (
        "存在桌面会话，系统通知可正常弹出" if report["desktop"]["session"] == "yes"
        else "未检测到桌面会话（如锁屏/无 GUI 服务态），系统通知可能不弹出；stdout 与 checkin.log 仍可记录结果"
    )

    # 5) 消息推送配置
    if push_message is not None:
        report["notify_config"] = push_message.ready_channels()
        report["notify_config"]["hint"] = "运行 --init-config 生成模板；--push-channels 可指定本次渠道"
    else:
        cfg = load_notify_config()
        if cfg is None:
            report["notify_config"]["present"] = False
            report["notify_config"]["hint"] = "未配置（可选）；运行 --init-config 生成模板"
        else:
            report["notify_config"]["present"] = True
            report["notify_config"]["enabled"] = cfg.get("enabled", True)
            report["notify_config"]["success_notify"] = bool(cfg.get("success_notify"))
            channels = [k for k in ("wecom_webhook", "pushplus_token", "bark_url") if cfg.get(k)]
            report["notify_config"]["channels"] = channels
            if cfg.get("enabled", True) and not channels:
                report["notify_config"]["warn"] = "enabled=true 但未填写任何通道，推送不会生效"

    return report


USAGE = (
    "WorkBuddy签到助手（接口直签 + 派猫猫旅行）\n\n"
    "用法：\n"
    "  python workbuddy_checkin.py                       # 签到 + 派猫猫旅行全自动闭环（默认）\n"
    "  python workbuddy_checkin.py --no-travel           # 只签到，跳过旅行（最快）\n"
    "  python workbuddy_checkin.py --check-only          # 仅查询（只读，不签到也不写旅行）\n"
    "  python workbuddy_checkin.py travel                # 只查派猫猫旅行状态（只读，不签到）\n"
    "  python workbuddy_checkin.py travel --travel-auto  # 只跑旅行闭环（不签到）\n"
    "  python workbuddy_checkin.py --travel-auto         # 显式开启旅行闭环（默认已开）\n"
    "  python workbuddy_checkin.py --location N          # 指定派遣地点（1-4，缺省随机）\n"
    "  python workbuddy_checkin.py --no-notify           # 跳过全部推送与桌面通知（调试用）\n"
    "  python workbuddy_checkin.py --push-channels dingtalk,email   # 仅向指定渠道推送（覆盖配置）\n"
    "  python workbuddy_checkin.py --confirm-paid        # 允许发送付费渠道（如短信 sms）\n"
    "  python workbuddy_checkin.py --diagnose            # 环境自检（Python/登录态/网络/桌面会话/推送配置）\n"
    "  python workbuddy_checkin.py --init-config         # 生成 notify_config.json.example 模板\n"
    "  python workbuddy_checkin.py --help                # 显示本帮助\n"
    "  python workbuddy_checkin.py --version             # 显示版本号\n\n"
    "派猫猫旅行说明：\n"
    "  状态三态：idle 空闲 / traveling 旅行中 / arrived 已到达待领取。\n"
    "  闭环顺序为先领取、后派遣；派遣前必查每日上限，达上限绝不发写请求。\n"
    "  已到达不会丢积分，下次运行自动补领。旅行接口不可用时静默降级，不影响签到结论。\n\n"
    "退出码：成功 0 / 失败 1（便于自动化判断是否推送告警）\n"
    "签到成功后会在结果中展示当前积分余额（若接口返回 balance / total_credit 等字段）。\n"
    "消息推送说明：\n"
    "  支持 12 类渠道：dingtalk/feishu/wecom/wechat(pushplus)/email/sms/qq/slack/telegram/bark/webhook/system。\n"
    "  失败自动推送（配置缺失则静默跳过）；成功播报需 success_notify=true。\n"
    "  渠道/凭据见 ~/.workbuddy/scripts/notify_config.json（旧结构微信三字段仍兼容）。\n"
)


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        sys.exit(0)
    if "--version" in sys.argv:
        print("workbuddy_checkin %s" % VERSION)
        sys.exit(0)
    # 环境自检：只读、不签到，便于首次安装后确认可用性
    if "--diagnose" in sys.argv:
        rep = diagnose()
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        sys.exit(0)
    # 生成推送配置模板（可选）
    if "--init-config" in sys.argv:
        if push_message is None:
            print("推送模块缺失，无法生成模板。")
            sys.exit(1)
        p = push_message.write_sample()
        print("已生成配置模板：%s" % p)
        print("复制为 notify_config.json 并填入你的通道密钥（或使用默认值保持关闭）。")
        print("支持渠道见 README『消息推送』章节；旧结构微信三字段仍兼容。")
        sys.exit(0)
    check_only = "--check-only" in sys.argv
    no_notify = "--no-notify" in sys.argv
    travel_only = "travel" in sys.argv[1:]
    travel_auto_flag = "--travel-auto" in sys.argv
    no_travel = "--no-travel" in sys.argv

    # 推送渠道覆盖（可选）：--push-channels dingtalk,email ；缺省用配置里全部已就绪渠道
    global _PUSH_CHANNELS, _PUSH_CONFIRM_PAID
    _PUSH_CHANNELS = None
    _PUSH_CONFIRM_PAID = False
    if "--push-channels" in sys.argv:
        try:
            idx = sys.argv.index("--push-channels")
            _PUSH_CHANNELS = [c.strip() for c in sys.argv[idx + 1].split(",") if c.strip()]
        except (IndexError, ValueError):
            sys.stderr.write("[push] --push-channels 后需跟逗号分隔的渠道名，如 dingtalk,email\n")
    if "--confirm-paid" in sys.argv:
        _PUSH_CONFIRM_PAID = True

    location_id = None
    if "--location" in sys.argv:
        try:
            idx = sys.argv.index("--location")
            location_id = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            sys.stderr.write("[travel] --location 需为整数（1-4），已忽略\n")

    if travel_only:
        # 纯旅行模式：不签到；默认只读，加 --travel-auto 才跑闭环
        do_checkin = False
        travel_mode = "auto" if travel_auto_flag else "readonly"
    else:
        do_checkin = True
        if no_travel:
            travel_mode = "off"
        elif check_only:
            travel_mode = "readonly"
        else:
            travel_mode = "auto"  # 默认随签到跑全自动闭环

    try:
        res = run(check_only=check_only, do_checkin=do_checkin,
                  travel_mode=travel_mode, location_id=location_id)
    except Exception as e:
        res = {"status": "error", "action": None, "points": None,
               "msg": "脚本未捕获异常: %s" % e, "detail": {}}
    # 输出结果（不含任何真实 token）
    # 失败推送（配置缺失则跳过；--no-notify 用于调试）
    if not no_notify and res.get("status") != "ok":
        try:
            _push_failure(res)
        except Exception:
            pass  # 推送失败不影响签到结果与退出码
    # 成功推送（仅当 notify_config.json 中 success_notify=true；--no-notify 用于调试）
    if not no_notify and res.get("status") == "ok":
        try:
            _push_success(res)
        except Exception:
            pass  # 推送失败不影响签到结果与退出码
    # 系统桌面通知（跨平台 toast / 气球；--no-notify 一并抑制；失败静默）
    if not no_notify:
        try:
            notify_system(res)
        except Exception:
            pass
    # 输出结果（不含任何真实 token）—— 移后以便包含推送状态
    print(json.dumps(res, ensure_ascii=False, indent=2))
    # 本地运行日志（系统定时任务无对话汇报，靠它核查）
    write_log(res)
    # 退出码：成功 0，失败 1，便于自动化判断是否推送告警
    sys.exit(0 if res.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
