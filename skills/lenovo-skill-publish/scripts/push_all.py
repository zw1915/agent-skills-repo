"""Batch-push Lenovo skill zips via the official CLI.

The CLI is interactive (prompts for "Update Notes", then a y/N confirm), so we
drive it over stdin with a delay between answers. Writes results to
push_results.json so reruns skip already-pushed skills.

Usage:  python push_all.py [--only name1,name2] [--skip a,b]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

NODE = r"C:\Users\zw\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
CLI = (r"C:\Users\zw\.workbuddy\binaries\node\workspace\node_modules"
       r"\@lenovo-open\skill-cli\dist\index.js")
NODE_PATH = r"C:\Users\zw\.workbuddy\binaries\node\workspace\node_modules"
WORK = Path(r"F:\workbuddy\2026-09-28-19-38-12")
# search order matters: C-drive leftovers first, then F-drive sets
DEFAULT_ZIP_DIRS = [WORK / "lenovo_zips_fixed",     # C-drive 28 (sanitized)
                    WORK / "lenovo_zips_f60",       # F-drive skills60 (doc-*/mat-*)
                    WORK / "lenovo_zips_f93"]       # F-drive skills93 (pro-*)
RESULTS = WORK / "push_results.json"
NOTES = "Initial release"

QUOTA_MARK = "已达上限"   # e.g. "今日部署次数已达上限(20次)"

CONFIRM_DELAY = 8      # seconds between notes answer and y/N confirm
PER_PUSH_TIMEOUT = 240


def load_results():
    if RESULTS.exists():
        try:
            return json.loads(RESULTS.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_results(res):
    RESULTS.write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


def push_one(zip_path: Path):
    env = os.environ.copy()
    env["NODE_PATH"] = NODE_PATH
    proc = subprocess.Popen(
        [NODE, CLI, "push", "-zap", str(zip_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(Path(NODE_PATH).parent),
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
    )

    chunks = []

    def drain():
        try:
            for line in proc.stdout:
                chunks.append(line)
        except Exception:
            pass

    t = threading.Thread(target=drain, daemon=True)
    t.start()

    try:
        # 1) answer Update Notes
        proc.stdin.write(NOTES + "\n")
        proc.stdin.flush()
        # 2) after the confirm prompt appears, answer y
        time.sleep(CONFIRM_DELAY)
        proc.stdin.write("y\n")
        proc.stdin.flush()
    except Exception:
        pass

    # The CLI does not exit while stdin is still open, so wait for a completion
    # marker in the output rather than waiting on process exit.
    deadline = time.time() + PER_PUSH_TIMEOUT
    while time.time() < deadline:
        cur = "".join(chunks)
        if "Push succeeded" in cur or "Push failed" in cur:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    t.join(timeout=10)

    raw = "".join(chunks)
    clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", raw)
    ok = "Push succeeded" in clean
    failed = "Push failed" in clean
    app_id, version = None, None
    for line in clean.splitlines():
        if "appId" in line:
            # e.g. "✓ Push succeeded, pending review, appId: 2026..., version: 1.0.0"
            try:
                part = line.split("appId:")[1]
                app_id = part.split(",")[0].strip()
                if "version:" in part:
                    version = part.split("version:")[1].strip()
            except Exception:
                pass
    reason = None
    if failed and "reason:" in clean:
        reason = clean.split("reason:")[-1].strip()[:400]

    return {
        "ok": ok and not failed,
        "appId": app_id,
        "version": version,
        "reason": reason,
        "raw": raw[-800:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--zips", default="",
                    help="comma-separated zip dirs (default: C-fixed, f60, f93)")
    ap.add_argument("--max", type=int, default=0,
                    help="stop after N successful pushes this run (0 = no cap)")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    dirs = ([Path(d.strip()) for d in args.zips.split(",") if d.strip()]
            if args.zips else DEFAULT_ZIP_DIRS)

    results = load_results()
    # dedupe by name, preserving dir order (first dir wins)
    seen, zips = set(), []
    for d in dirs:
        if not d.is_dir():
            print(f"[warn] zip dir missing: {d}")
            continue
        for zp in sorted(d.glob("*.zip")):
            if zp.stem not in seen:
                seen.add(zp.stem)
                zips.append(zp)

    quota_hit = False
    pushed_this_run = 0
    for zp in zips:
        name = zp.stem
        if only and name not in only:
            continue
        if name in skip:
            continue
        if results.get(name, {}).get("ok"):
            print(f"[skip] {name} already pushed (appId={results[name].get('appId')})")
            continue

        print(f"\n=== pushing {name} ===", flush=True)
        r = push_one(zp)
        results[name] = r
        save_results(results)
        status = "OK" if r["ok"] else "FAIL"
        print(f"[{status}] {name} appId={r.get('appId')} "
              f"version={r.get('version')} reason={r.get('reason')}", flush=True)

        if r["ok"]:
            pushed_this_run += 1
            if args.max and pushed_this_run >= args.max:
                print(f"\n[stop] reached --max {args.max} successes this run")
                break
        else:
            # daily deployment cap reached -> further pushes today are futile
            if r.get("reason") and QUOTA_MARK in r["reason"]:
                quota_hit = True
                print("\n[stop] daily deployment quota exhausted "
                      "(20/day). Re-run tomorrow after reset.")
                break

        # brief pause to avoid hammering the endpoint
        time.sleep(2)

    ok = sum(1 for v in results.values() if v.get("ok"))
    pending = sum(1 for zp in zips
                  if not results.get(zp.stem, {}).get("ok"))
    print(f"\n==== summary: {ok} succeeded / {len(results)} recorded; "
          f"this run +{pushed_this_run}; pending {pending} "
          f"(quota hit today: {quota_hit}) ====")
    for n, v in sorted(results.items()):
        if not v.get("ok"):
            print(f"  FAILED {n}: {v.get('reason') or v.get('raw','')[:120]}")


if __name__ == "__main__":
    sys.exit(main())
