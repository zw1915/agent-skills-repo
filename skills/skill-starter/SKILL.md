---
name: skill-starter
display_name: 技能起步模板
display_name_en: Skill Starter Template
description: "最小但完整的 WorkBuddy 技能包模板，两个用途：验证上传通道是否可用，以及作为编写新技能的起点。附一键生成导入就绪骨架的脚本——目录严格两级、frontmatter 一次写好 8 个必需字段（name/display_name/display_name_en/description/description_zh/description_en/category/version），生成即可上传、无需事后补字段。当用户表达「生成一个技能」「新建技能」「做一个能上传的技能」「技能模板」「技能骨架」「skill 起手」「怎么开始写技能」「我的技能导不进去」等意图时，使用本技能。也用于修复上游报错「目录层级超限」「缺少 Skill 版本号」「缺少 Skill 中文展示名/英文展示名/中文描述/英文描述」后的重建起点。不适用于技能内容创作方法论（用 skill-creator），也不适用于单纯校验已有技能包（用 skill-package-guard）。"
description_zh: "最小但完整的 WorkBuddy 技能包模板，两个用途：验证上传通道是否可用，以及作为编写新技能的起点。附一键生成导入就绪骨架的脚本——目录严格两级、frontmatter 一次写好 8 个必需字段（name/display_name/display_name_en/description/description_zh/description_en/category/version），生成即可上传、无需事后补字段。当用户表达「生成一个技能」「新建技能」「做一个能上传的技能」「技能模板」「技能骨架」「skill 起手」「怎么开始写技能」「我的技能导不进去」等意图时，使用本技能。也用于修复上游报错「目录层级超限」「缺少 Skill 版本号」「缺少 Skill 中文展示名/英文展示名/中文描述/英文描述」后的重建起点。不适用于技能内容创作方法论（用 skill-creator），也不适用于单纯校验已有技能包（用 skill-package-guard）。"
description_en: "A minimal but complete WorkBuddy skill package, serving two purposes: verifying that the upload/import channel works, and acting as the starting point for authoring a new skill. Ships a scaffolding script that generates an import-ready skeleton — strictly two-level directories and all 8 frontmatter fields written up front (name, display_name, display_name_en, description, description_zh, description_en, category, version) — so it can be uploaded as-is with no follow-up fixes. Use when the user asks to generate a skill, create a new skill, make an uploadable skill, or asks for a skill template, skill skeleton, skill starter, or how to begin writing a skill; also when a skill failed to import with errors about excessive directory nesting or missing version / display_name / display_name_en / description_zh / description_en. Not for skill authoring methodology (use skill-creator) or for validating an existing package (use skill-package-guard)."
category: developer-tools
version: 1.0.0
agent_created: true
---

# 技能起步模板

一个**最小但完整**的 WorkBuddy 技能包。两个用途：先确认上传通道可用，再作为写新技能的起点。

## 为什么需要「最小」

创建技能最容易失败的地方不是内容，而是**包的形状**。目录多一层、frontmatter 少一个字段，导入就会被拒，而且报错是分阶段给出的——修完层级才报字段。所以把「能上传」和「写得好」拆开：先用这个包确认通道正常，再往里填内容。

这个包只保留必需的东西：**两个文件、两级目录、8 个字段**。

```
skill-starter/
├── SKILL.md               技能本体（frontmatter + 说明）
└── scripts/
    └── make_skill.py      生成导入就绪的新技能骨架
```

## 用法一：一键生成新技能

```bash
python scripts/make_skill.py my-skill \
  --display-name "我的技能" \
  --display-name-en "My Skill" \
  --desc "做什么 + 何时用 + 不适用" \
  --category writing
```

生成到 `~/.workbuddy/skills/my-skill/`（用 `--out` 改位置），结构与本技能一致，**8 个字段一次写好**，不需要再补。目录已存在时不会覆盖，加 `--force` 才覆盖。

## 用法二：直接复制本目录

把本技能目录复制一份改名，然后替换 SKILL.md 里的占位：`name`、`display_name`、`display_name_en`、三个 `description_*`。

## 8 个必需字段

| 字段 | 说明 | 常见错误 |
|---|---|---|
| `name` | 小写字母/数字/连字符 | 用了下划线或大写 |
| `display_name` | 中文展示名 | 缺失 |
| `display_name_en` | 英文展示名 | 缺失 |
| `description` | 中文长描述 | 写成一句话摘要，导致技能不被唤起 |
| `description_zh` | 与 `description` 一致 | 两者不一致 |
| `description_en` | 英文长描述，信息量与中文对齐 | 压成一句 |
| `category` | 见下 | 缺失 |
| `version` | `x.y.z` | 写成 `1.0` |
| `agent_created` | 自建技能置 `true` | 缺失则后续无法修改 |

`category` 常用值：`writing`、`developer-tools`、`data-analysis`、`productivity`、`design`、`research`。

## description 怎么写（最关键）

它**不是摘要，是触发条件清单**。三段式：

1. **做什么** + 核心机制
2. **什么时候用**——列出用户可能说的各种说法（同义词、口语、行业黑话都要覆盖）
3. **不适用于什么**——划边界，避免误触发

```
"<做什么，含核心机制>。当用户表达「<触发词1>」「<触发词2>」「<触发词3>」等意图，
或提到 <场景A>/<场景B> 时，使用本技能。不适用于 <边界场景>。"
```

英文描述的信息量要与中文对齐——它服务于英文环境下的唤起，不是装饰。描述太短的直接后果是技能永远不会被唤起。

## 执行流程该怎么写

**确定性的事交给脚本，判断性的事交给模型。** 统计、匹配、格式转换、评分这类每次都会重写同样的代码，就放进 `scripts/` 并在 SKILL.md 里给出调用命令；语义判断、取舍、改写留给模型，但要在 SKILL.md 里明确写出「哪些必须模型判断，不得省略」。

这条分界是技能质量的主要来源——否则要么让模型每次现算（不稳定），要么让脚本做它做不到的语义判断（不准）。

## 目录约束

**只能两级**：`根目录 / 二级目录 / 文件`。标准子目录是 `references/`、`assets/`、`scripts/`。

不要建 `assets/samples/x.md` 这种三层路径。需要多份同类内容时**合并成单文件**（如 `assets/samples-guide.md`）；运行时状态也一律用单文件而非目录——目录方案在这个约束下会反复踩坑。

## 打包前必须自检

```bash
python ~/.workbuddy/skills/skill-package-guard/scripts/check_skill_package.py <技能目录>
```

> `skill-creator` 的 `package_skill.py` **不校验目录层级和展示字段**——它对一个根本导不进去的包也会报「✅ Skill is valid!」。所以这一步不能省。

打包（需 `skill-creator`）：

```bash
python <skill-creator 目录>/scripts/package_skill.py <技能目录> ./dist
```

**打包后对 zip 再跑一次自检**：磁盘结构与包内结构可能不一致。

## 三条最容易踩的坑

1. **`__pycache__`**——在技能目录里跑过 `python -m py_compile`，或 import 过本地模块，就会生成 `scripts/__pycache__/*.pyc`。它构成三级目录，**并且会被打进包里**。打包前务必 `rm -rf scripts/__pycache__`。测试脚本时用绝对路径执行可避免产生它。
2. **改完 frontmatter 要清缓存再导入**，否则可能仍读到旧值；每次改动递增 `version`，便于区分导入的是哪一版。
3. **description 宁长勿短**。太短不会报错，只会静默地不被唤起——比报错更难排查。

## 与相邻技能的分工

| 技能 | 职责 |
|---|---|
| `skill-creator` | 怎么写出一个好技能（方法论） |
| `skill-package-guard` | 能不能被导入（校验器） |
| **本技能** | 起手模板与骨架生成 |
