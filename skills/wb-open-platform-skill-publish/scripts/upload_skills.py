#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量上传技能 zip 到 WorkBuddy 开放平台（技能发布三步流程）。

配置方式（环境变量）：
  BSK_SESSION  bsk 会话 id（必需）
  ZIP_DIR      zip 目录（必需）
  ZIP_PREFIX   只处理该前缀的 zip，例如 b1-（可选）
  MARKET_CAT   市场展示分类，默认 开发工具（可选；个人账号可选：办公协同/开发工具/效率工具/内容创作）
  SERVICE_PARENT / SERVICE_CHILD  服务类目两级，默认 工具 / 办公
  UPLOAD_LOG   进度日志路径（可选）

用法: python upload_skills.py [start] [count]
"""
import subprocess, re, os, sys, time

BSK = "bsk"
SESSION = os.environ.get("BSK_SESSION", "")
ZIP_DIR = os.environ.get("ZIP_DIR", "")
ZIP_PREFIX = os.environ.get("ZIP_PREFIX", "")
MARKET_CAT = os.environ.get("MARKET_CAT", "开发工具")
SERVICE_PARENT = os.environ.get("SERVICE_PARENT", "工具")
SERVICE_CHILD = os.environ.get("SERVICE_CHILD", "办公")
LOG = os.environ.get("UPLOAD_LOG", os.path.join(os.getcwd(), "upload_progress.txt"))

ENV = {**os.environ, "BSK_AUTO_START": "0"}
LIST_URL = "https://open.workbuddy.cn/skill/all"
CREATE_URL = "https://open.workbuddy.cn/skill/publish?action=create&step=1"
CLEAR_JS = "sessionStorage.removeItem('wb.open.publication.draft'); 'ok'"

_REF_RE = re.compile(r'(@e\d+)\s+(\w+)\s+"([^"]*)"')
_OK_RE = re.compile(r'已提交审核')
_FAIL_RE = re.compile(r'解析失败')
_OS_RE = re.compile(r'os_[0-9a-zA-Z]{8,}')


def run(args, timeout=120):
    try:
        p = subprocess.run([BSK] + args, capture_output=True, text=True, env=ENV, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


def observe():
    return run(["observe", "--session", SESSION, "--max-tokens", "100000"])


def find_ref(text, role=None, exact=False, obs_text=None):
    o = obs_text if obs_text is not None else observe()
    for m in _REF_RE.finditer(o):
        ref, r, t = m.group(1), m.group(2), m.group(3)
        if role and r != role:
            continue
        if (t == text) if exact else (text in t):
            return ref, o
    return None, o


def click(ref):
    return run(["click", ref, "--session", SESSION, "--json"])


def press_escape():
    return run(["press", "Escape", "--session", SESSION, "--json"])


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def do_one(zip_name):
    """提交一个 zip，成功返回 None，失败返回原因字符串"""
    path = os.path.join(ZIP_DIR, zip_name).replace("\\", "/")
    log(f"[{zip_name}] --- 开始 ---")

    # A. 落创建页 -> 清 draft -> 重载
    #    批量必做：向导把当前资产存在 sessionStorage，提交后不清空，
    #    下一轮会仍绑定上个资产，上传新包被当改名而失败。
    run(["navigate", CREATE_URL, "--session", SESSION, "--json"]); time.sleep(2.5)
    run(["evaluate", "--session", SESSION, CLEAR_JS]); time.sleep(0.3)
    run(["reload", "--session", SESSION, "--json"]); time.sleep(2.5)

    # B. 上传 zip
    ref = None
    for _ in range(6):
        ref, o = find_ref("上传代码包", role="button")
        if ref:
            break
        time.sleep(1.5)
    if not ref:
        log(f"[{zip_name}] !! 未找到上传按钮"); return "no_upload_btn"
    # 该上传器是拖拽式（非 input[type=file]），必须用 --mode drop
    out = run(["upload", ref, "--file", path, "--mode", "drop", "--session", SESSION, "--json"])
    time.sleep(4.5)
    if '"file_names"' not in out and "upload ok" not in out:
        log(f"[{zip_name}] !! upload 返回异常: {out.strip()[:160]}"); return "upload_err"

    # C. 等解析：认 os_ 正则，不认静态提示语；同时抓解析失败
    o = observe()
    if _FAIL_RE.search(o):
        log(f"[{zip_name}] !! 解析失败"); return "parse_fail"
    if not _OS_RE.search(o):
        time.sleep(5)
        o = observe()
        if _FAIL_RE.search(o):
            log(f"[{zip_name}] !! 解析失败"); return "parse_fail"
        if not _OS_RE.search(o):
            log(f"[{zip_name}] !! 未见技能ID"); return "no_id"

    # D. 继续 -> 第2步
    ref, o = find_ref("继续", role="button", exact=True)
    if not ref:
        log(f"[{zip_name}] !! 未找到『继续』(1)"); return "no_next1"
    click(ref); time.sleep(2)

    # E. 市场展示分类（combobox，多选，选完要 Escape 收起）
    ref, o = find_ref("请选择", role="combobox")
    if not ref:
        log(f"[{zip_name}] !! 未找到『市场展示分类』下拉"); return "no_market_combo"
    click(ref); time.sleep(1.2)
    ref, o = find_ref(MARKET_CAT, role="button", exact=True)
    if not ref:
        log(f"[{zip_name}] !! 未找到选项『{MARKET_CAT}』"); return "no_market_opt"
    click(ref); time.sleep(1.0)
    press_escape(); time.sleep(0.6)

    # F. 服务类目（button，两级：父 -> 子）
    ref, o = find_ref("请选择", role="button")
    if not ref:
        log(f"[{zip_name}] !! 未找到『服务类目』下拉"); return "no_service_combo"
    click(ref); time.sleep(1.2)
    ref, o = find_ref(SERVICE_PARENT, role="button", exact=True)
    if not ref:
        log(f"[{zip_name}] !! 未找到父类目『{SERVICE_PARENT}』"); return "no_service_parent"
    click(ref); time.sleep(1.0)
    ref, o = find_ref(SERVICE_CHILD, role="button", exact=True)
    if not ref:
        log(f"[{zip_name}] !! 未找到子类目『{SERVICE_CHILD}』"); return "no_service_child"
    click(ref); time.sleep(1.2)

    # G. 继续 -> 第3步
    ref, o = find_ref("继续", role="button", exact=True)
    if not ref:
        log(f"[{zip_name}] !! 未找到『继续』(2)"); return "no_next2"
    click(ref); time.sleep(2)

    # H. 提交
    ref, o = find_ref("提交", role="button", exact=True)
    if not ref:
        log(f"[{zip_name}] !! 未找到『提交』按钮"); return "no_submit"
    click(ref); time.sleep(3)

    o = observe()
    if not _OK_RE.search(o):
        log(f"[{zip_name}] !! 提交后未见成功提示"); return "submit_unverified"
    log(f"[{zip_name}] OK 已提交审核")
    return None


def main():
    if not SESSION or not ZIP_DIR:
        print("需要环境变量 BSK_SESSION 与 ZIP_DIR"); sys.exit(1)
    zips = sorted(f for f in os.listdir(ZIP_DIR)
                  if f.endswith(".zip") and f.startswith(ZIP_PREFIX))
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else len(zips)
    targets = zips[start:start + count]
    log(f"=== 计划提交 {len(targets)} 个: {targets[0]} ... {targets[-1]} ===")
    ok, fail = 0, []
    for i, z in enumerate(targets, 1):
        try:
            r = do_one(z)
            if r is None:
                ok += 1
            else:
                fail.append((z, r))
        except Exception as e:
            log(f"[{z}] EXC {e}")
            fail.append((z, f"exc:{e}"))
        log(f"--- 进度 {i}/{len(targets)} 成功{ok} 失败{len(fail)} ---")
    log(f"=== 完成: 成功 {ok}, 失败 {len(fail)} {fail} ===")


if __name__ == "__main__":
    main()
