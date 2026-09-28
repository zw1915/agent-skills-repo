#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_skill_package.py — WorkBuddy Skill 包导入前置校验

校验三项导入端约束：
  1. 目录层级不超过两级（根目录 / 二级目录 / 文件）
  2. frontmatter 含 8 个必需字段 + agent_created
  3. 无 __pycache__ 等运行时缓存目录

用法:
  python check_skill_package.py <技能目录>
  python check_skill_package.py <已打包的.zip>
  python check_skill_package.py --all <技能根目录>

退出码: 0 = 全部通过, 1 = 存在问题
"""

import argparse
import os
import re
import sys
import zipfile

REQUIRED_FIELDS = [
    ("name", "Skill 名称（小写连字符）"),
    ("display_name", "Skill 中文展示名"),
    ("display_name_en", "Skill 英文展示名"),
    ("description", "Skill 描述"),
    ("description_zh", "Skill 中文描述"),
    ("description_en", "Skill 英文描述"),
    ("category", "Skill 分类"),
    ("version", "Skill 版本号"),
]

CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
              ".ipynb_checkpoints", "node_modules", ".git", ".venv", "venv"}

MIN_DESC_LEN = 80  # 描述过短会导致技能不被唤起

# 导入端对展示字段的长度硬上限（超出直接报「解析失败」）
# 实测报错信息：「Skill 英文描述：当前 1125 字符，上限 1000 字符」
MAX_DESC_LEN = {
    "description_en": 1000,
    "description_zh": 1000,
    "description": 1000,
}
# 留出余量：余量低于该值即告警，避免改一个词就超限
DESC_LEN_WARN_MARGIN = 40


# ------------------------------------------------------------ frontmatter 解析
def parse_frontmatter(text):
    """优先用 yaml，无则降级为行解析（支持引号包裹的多行值）。"""
    m = re.match(r"^\ufeff?---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None, "未找到 frontmatter（文件开头应为 --- 包裹的 YAML 块）"
    block = m.group(1)
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(block)
        return (data if isinstance(data, dict) else {}), None
    except ImportError:
        pass
    except Exception as exc:  # YAML 语法错误
        return None, f"frontmatter YAML 语法错误：{exc}"

    # 降级解析
    data, key, buf = {}, None, []
    for line in block.split("\n"):
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*:", line):
            if key:
                data[key] = " ".join(buf).strip().strip('"').strip("'")
            key, _, val = line.partition(":")
            key, buf = key.strip(), [val.strip()]
        elif key:
            buf.append(line.strip())
    if key:
        data[key] = " ".join(buf).strip().strip('"').strip("'")
    return data, None


# ------------------------------------------------------------ 校验逻辑
def check_entries(entries, label, verbose=True):
    """entries: list of (深度, 相对路径, 是否目录)"""
    problems, notes = [], []

    for depth, path, is_dir in entries:
        base = os.path.basename(path.rstrip("/"))
        if is_dir and base in CACHE_DIRS:
            problems.append(f"{label} 存在运行时缓存目录（会被打进包并造成层级超限）："
                            f"{path}\n      → 删除命令：rm -rf \"{path}\"")

    max_depth = max((d for d, _, _ in entries), default=0)
    for depth, path, is_dir in entries:
        if depth > 2:
            problems.append(f"{label} 目录层级超限（{depth} 级，上限 2 级）：{path}")

    return problems, notes, max_depth


def check_frontmatter(fm, err, label):
    problems, warns = [], []
    if err:
        problems.append(f"{label} {err}")
        return problems, warns

    for key, desc in REQUIRED_FIELDS:
        val = fm.get(key)
        if val is None or not str(val).strip():
            problems.append(f"{label} 缺少 {desc}（{key}），导入会报「解析失败」")

    if not fm.get("agent_created"):
        warns.append(f"{label} 未设置 agent_created: true（自建技能建议加上，"
                     f"否则后续无法通过 SkillManage 修改）")

    name = str(fm.get("name") or "")
    if name and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        problems.append(f"{label} name「{name}」不合规，应为小写字母/数字与连字符")

    ver = str(fm.get("version") or "")
    if ver and not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        problems.append(f"{label} version「{ver}」格式应为 x.y.z")

    d_zh = str(fm.get("description_zh") or "")
    d = str(fm.get("description") or "")
    if d and d_zh and d != d_zh:
        warns.append(f"{label} description 与 description_zh 不一致（建议保持一致）")

    if d and len(d) < MIN_DESC_LEN:
        warns.append(f"{label} description 仅 {len(d)} 字，偏短易导致技能不被唤起，"
                     f"建议补齐触发场景与不适用场景")

    # 长度上限：超限会被导入端直接拒绝
    for key, limit in MAX_DESC_LEN.items():
        val = str(fm.get(key) or "")
        if not val:
            continue
        n = len(val)
        if n > limit:
            problems.append(
                f"{label} {key} 当前 {n} 字符，超出上限 {limit} 字符 -> 导入会报"
                f"「解析失败：{key} 当前 {n} 字符，上限 {limit} 字符」，需压缩 {n - limit} 字符")
        elif n > limit - DESC_LEN_WARN_MARGIN:
            warns.append(
                f"{label} {key} 已达 {n}/{limit} 字符，余量不足 "
                f"{limit - n}，再改一句就可能超限，建议预留 {DESC_LEN_WARN_MARGIN} 字符以上余量")

    return problems, warns


def check_dir(path, verbose=True):
    entries = []
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path)
        rel_root = "" if rel_root == "." else rel_root.replace("\\", "/")
        for d in dirs:
            p = f"{rel_root}/{d}" if rel_root else d
            entries.append((len([x for x in p.split("/") if x]), p, True))
        for f in files:
            p = f"{rel_root}/{f}" if rel_root else f
            entries.append((len([x for x in p.split("/") if x]), p, False))
    entries.sort(key=lambda t: (t[0], t[1]))

    label = os.path.basename(os.path.abspath(path))
    problems, notes, max_depth = check_entries(entries, label, verbose)

    skill_md = os.path.join(path, "SKILL.md")
    if not os.path.exists(skill_md):
        problems.append(f"{label} 根目录缺少 SKILL.md")
    else:
        with open(skill_md, "r", encoding="utf-8") as fh:
            fm, err = parse_frontmatter(fh.read())
        p2, w2 = check_frontmatter(fm, err, label)
        problems += p2
        notes += w2

    return problems, notes, entries, max_depth


def check_zip(path):
    z = zipfile.ZipFile(path)
    entries = []
    for n in z.namelist():
        if n.endswith("/"):
            continue
        parts = [p for p in n.replace("\\", "/").split("/") if p]
        if len(parts) <= 1:
            continue
        rel = "/".join(parts[1:])  # 去掉根目录名
        entries.append((len(parts) - 1, rel, False))
    entries.sort(key=lambda t: (t[0], t[1]))

    label = os.path.basename(path)
    problems, notes, max_depth = check_entries(entries, label)

    # 包内 SKILL.md 校验
    inner = [n for n in z.namelist() if n.replace("\\", "/").endswith("SKILL.md")]
    if inner:
        fm, err = parse_frontmatter(z.read(inner[0]).decode("utf-8"))
        p2, w2 = check_frontmatter(fm, err, label)
        problems += p2
        notes += w2
    else:
        problems.append(f"{label} 包内未找到 SKILL.md")

    return problems, notes, entries, max_depth


# ------------------------------------------------------------ 输出
def report(name, problems, notes, entries, max_depth, echo):
    if problems:
        echo(f"❌ {name} —— 发现 {len(problems)} 个问题")
        for p in problems:
            echo(f"   • {p}")
    else:
        echo(f"✅ {name} —— 通过导入前置校验")
    for n in notes:
        echo(f"   ⚠️  {n}")
    echo(f"   层级：最大 {max_depth}（上限 2）　条目：{len(entries)}")
    return len(problems)


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy Skill 包导入前置校验")
    ap.add_argument("path", nargs="?", help="技能目录或 .zip 路径")
    ap.add_argument("--all", metavar="ROOT", help="批量校验根目录下的所有技能")
    ap.add_argument("--quiet", action="store_true", help="只输出结论")
    args = ap.parse_args()

    if not args.path and not args.all:
        ap.error("需要提供技能目录 / zip 路径，或使用 --all <根目录>")

    echo = (lambda *a: None) if args.quiet else print
    targets = []

    if args.all:
        for name in sorted(os.listdir(args.all)):
            p = os.path.join(args.all, name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "SKILL.md")):
                targets.append(p)
        if not targets:
            echo(f"在 {args.all} 下未找到含 SKILL.md 的技能目录")
            return 1
    else:
        targets.append(args.path)

    total = 0
    echo("=" * 68)
    echo("WorkBuddy Skill 包导入前置校验")
    echo("=" * 68)
    for t in targets:
        if not os.path.exists(t):
            echo(f"❌ 路径不存在：{t}")
            total += 1
            continue
        try:
            if os.path.isdir(t):
                problems, notes, entries, md = check_dir(t)
            else:
                problems, notes, entries, md = check_zip(t)
        except Exception as exc:
            echo(f"❌ {t} 校验异常：{exc}")
            total += 1
            continue
        total += report(os.path.basename(os.path.abspath(t)),
                        problems, notes, entries, md, echo)
        echo("-" * 68)

    echo("")
    if total == 0:
        echo("结论：全部通过，可以打包 / 导入。")
        echo("提示：打包后请对 zip 再跑一次——磁盘结构与包内结构可能不一致。")
    else:
        echo(f"结论：共 {total} 个问题，修复后再打包。")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
