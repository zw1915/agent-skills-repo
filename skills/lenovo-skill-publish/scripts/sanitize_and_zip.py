"""Fix Lenovo YAML-parse failures and rebuild skill zips from any source dir.

Lenovo's parser rejects SKILL.md frontmatter where an UNQUOTED scalar contains
": " (colon+space) -- YAML reads it as a second key:
  {"status": -2, "message": "SKILL.md文件失败，请检查语法格式，或检查冒号空格、缩进及特殊字符"}

Copies each skill to a staging dir, quotes risky frontmatter values, and zips
the result with SKILL.md at the zip ROOT (another hard platform rule).
Originals are never modified.

Usage:
  python sanitize_and_zip.py                       # default C-drive skills
  python sanitize_and_zip.py --src <dir> --out <dir> [--stage <dir>]
"""
import argparse
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

DEFAULT_SRC = r"C:\Users\zw\.workbuddy\skills"
DEFAULT_STAGE = r"F:\workbuddy\2026-09-28-19-38-12\staged"
DEFAULT_OUT = r"F:\workbuddy\2026-09-28-19-38-12\lenovo_zips_fixed"

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".idea"}
EXCLUDE_EXT = {".pyc", ".pyo"}
LIMIT = 10 * 1024 * 1024

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s+(.*)$")


def needs_quoting(val: str) -> bool:
    v = val.strip()
    if not v:
        return False
    if v[0] in "\"'":
        return False          # already quoted
    if ": " in v:             # colon+space breaks plain scalars
        return True
    if v.endswith(":"):       # trailing colon
        return True
    if v[0] in "{}[]&*!|>%@`":  # YAML indicators
        return True
    return False


def quote(val: str) -> str:
    v = val.strip()
    esc = v.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def sanitize_frontmatter(text: str):
    """Return (new_text, n_fixed)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text, 0
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return text, 0

    fixed = 0
    for i in range(1, end):
        m = KEY_RE.match(lines[i])
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if needs_quoting(val):
            lines[i] = f"{key}: {quote(val)}"
            fixed += 1
    return "\n".join(lines), fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--stage", default=None,
                    help="staging dir (default: <workspace>/staged_<outname>)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    stage = Path(args.stage) if args.stage else out.parent / (
        "staged_" + out.name.replace("lenovo_zips_", ""))

    if stage.exists():
        shutil.rmtree(stage)
    out.mkdir(parents=True, exist_ok=True)

    names = sorted(d for d in os.listdir(src)
                   if (src / d).is_dir() and not d.startswith("."))
    report = {}
    for n in names:
        s = src / n
        dst = stage / n
        shutil.copytree(s, dst,
                        ignore=shutil.ignore_patterns(*EXCLUDE_DIRS))
        skill_md = dst / "SKILL.md"
        fixed = 0
        if skill_md.exists():
            txt = skill_md.read_text(encoding="utf-8", errors="ignore")
            new_txt, fixed = sanitize_frontmatter(txt)
            if fixed:
                skill_md.write_text(new_txt, encoding="utf-8")

        zpath = out / f"{n}.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(dst):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    if os.path.splitext(f)[1] in EXCLUDE_EXT:
                        continue
                    full = Path(root) / f
                    # SKILL.md must land at the ZIP ROOT (platform rule)
                    arc = os.path.relpath(full, dst).replace(os.sep, "/")
                    z.write(full, arc)

        sz = zpath.stat().st_size
        report[n] = {"yaml_fixed": fixed,
                     "mb": round(sz / 1024 / 1024, 2),
                     "over_limit": sz > LIMIT}

    (out / "_sanitize_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fixed_items = [(k, v["yaml_fixed"]) for k, v in report.items() if v["yaml_fixed"]]
    over = [k for k, v in report.items() if v["over_limit"]]
    print(f"src={src}")
    print(f"staged+zipped {len(report)} skills -> {out}")
    print(f"YAML fixes applied ({len(fixed_items)}):")
    for k, c in fixed_items:
        print(f"  {k}: {c} field(s) quoted")
    if over:
        print("OVER 10MB:", over)
    else:
        print("all zips within 10MB limit")


if __name__ == "__main__":
    main()
