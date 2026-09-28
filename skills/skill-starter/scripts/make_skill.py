#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_skill.py — 生成一个「导入就绪」的 WorkBuddy 技能骨架

与 skill-creator 的 init_skill.py 的区别：本脚本一次写入导入端要求的
8 个 frontmatter 字段（含 display_name / description_zh / description_en 等），
生成即可直接上传，不需要事后补字段——补字段正是导入失败最常见的原因。

用法:
  python make_skill.py my-skill --display-name "我的技能"
  python make_skill.py my-skill --display-name "我的技能" \
      --display-name-en "My Skill" --desc "做什么 + 何时用 + 不适用" \
      --category writing --out ~/.workbuddy/skills
"""

import argparse
import os
import re
import sys

CATEGORIES = ["writing", "developer-tools", "data-analysis",
              "productivity", "design", "research"]

SKILL_TEMPLATE = """---
name: {name}
display_name: {display_name}
display_name_en: {display_name_en}
description: "{desc}"
description_zh: "{desc}"
description_en: "{desc_en}"
category: {category}
version: 1.0.0
agent_created: true
---

# {display_name}

> 待填写：用一段话说明这个技能做什么、核心机制是什么。写清「怎么工作」，
> 而不只是「做什么」。

## 什么时候用

> 待填写：列出触发场景。写得越具体，技能越容易被正确唤起。

- 用户说：「…」「…」「…」
- 用户提到：… / …

## 不适用

> 待填写：划清边界，避免误触发。

- …

## 执行流程

> 待填写：步骤化。确定性的事（统计、匹配、转换、评分）写成 scripts/ 下的脚本
> 并在此给出调用命令，不要让模型每次现算；语义判断留给模型，但要写清
> 「哪些必须模型判断，不得省略」。

1. …
2. …

```bash
python scripts/xxx.py --input ... --format md
```

## 硬约束

> 待填写：这个技能在什么情况下必须停下、必须拒绝、或必须提示用户。
> 例如不得编造数据、不得替代专业意见、超范围请求要拒绝。

1. …

## 资源

| 文件 | 用途 |
|---|---|
| `references/…` | … |
| `assets/…` | … |
| `scripts/…` | … |

## 打包与导入约束

- 目录**最多两级**（根目录 / 二级目录 / 文件）；`assets/a/b.md` 这类三层路径会被拒绝
- frontmatter 需上述 8 个字段 + `agent_created: true`
- 打包前删除 `scripts/__pycache__`——它构成三级目录且会被打进包
- 自检：`python ~/.workbuddy/skills/skill-package-guard/scripts/check_skill_package.py <技能目录>`
- 改动后递增 `version`；导入前清缓存，否则可能读到旧值
"""


def main():
    ap = argparse.ArgumentParser(
        description="生成导入就绪的 WorkBuddy 技能骨架")
    ap.add_argument("name", help="技能名（小写字母/数字/连字符，如 my-skill）")
    ap.add_argument("--display-name", default=None, help="中文展示名")
    ap.add_argument("--display-name-en", default=None, help="英文展示名")
    ap.add_argument("--desc", default=None, help="中文描述（触发条件清单式）")
    ap.add_argument("--desc-en", default=None, help="英文描述")
    ap.add_argument("--category", default="productivity", choices=CATEGORIES)
    ap.add_argument("--out", default=None,
                    help="输出根目录，默认为 ~/.workbuddy/skills")
    ap.add_argument("--force", action="store_true",
                    help="SKILL.md 已存在时覆盖")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", args.name):
        ap.error(f"技能名「{args.name}」不合规："
                 "只允许小写字母、数字与连字符（如 my-skill）")

    out_root = args.out or os.path.join(
        os.path.expanduser("~"), ".workbuddy", "skills")
    out_root = os.path.normpath(out_root)
    skill_dir = os.path.join(out_root, args.name)
    skill_md = os.path.join(skill_dir, "SKILL.md")

    display_name = args.display_name or args.name
    display_name_en = args.display_name_en or " ".join(
        w.capitalize() for w in args.name.split("-"))
    desc = args.desc or f"{display_name}：待填写——写清做什么与何时使用。"
    desc_en = args.desc_en or (
        f"{display_name_en}: TODO — describe what it does and when to use it.")

    if os.path.exists(skill_md) and not args.force:
        print(f"已存在，未覆盖：{skill_md}")
        print("如需覆盖请加 --force")
        return 1

    for sub in ("references", "scripts"):
        os.makedirs(os.path.join(skill_dir, sub), exist_ok=True)

    with open(skill_md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SKILL_TEMPLATE.format(
            name=args.name,
            display_name=display_name,
            display_name_en=display_name_en,
            desc=desc,
            desc_en=desc_en,
            category=args.category,
        ))

    print(f"已生成导入就绪的技能骨架：{skill_dir}")
    print("")
    print("下一步：")
    print("  1. 打开 SKILL.md，替换所有标了「待填写」的部分")
    print("  2. 把 description 改写成触发条件清单：做什么 + 何时用 + 不适用")
    print("  3. 需要确定性计算时在 scripts/ 下写脚本，不要让模型现算")
    print("  4. 删掉用不到的 references/ 或 scripts/ 空目录")
    print("  5. 打包前自检（这一步不能省）：")
    print("     python \"<skill-package-guard>/scripts/check_skill_package.py\" "
          f"\"{skill_dir}\"")
    print("  6. 打包后对 zip 再自检一次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
