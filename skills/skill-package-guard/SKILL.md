---
name: skill-package-guard
display_name: 技能包导入自检
display_name_en: Skill Package Import Guard
description: "在 WorkBuddy 中打包或导入自建 Skill 前的前置校验器，专治四类「解析失败」：目录层级超过两级（根目录/二级目录/文件）、SKILL.md frontmatter 缺少导入端要求的展示与版本字段（display_name、display_name_en、description_zh、description_en、version、category 等）、__pycache__ 等运行时缓存目录被打进包导致层级超限、以及描述字段超过 1000 字符上限（英文描述按中文直译最容易超，中文 356 字符常膨胀到 1000+）。当用户要创建、编辑、打包、导出、分发自建 Skill，或遇到导入报错「目录层级超限」「缺少 Skill 版本号」「缺少 Skill 中文展示名」「Skill 英文描述：当前 N 字符，上限 1000 字符」「解析失败」时使用本技能。它是 skill-creator 的补充：skill-creator 负责怎么写出好技能，本技能负责让写出来的技能能被导入端接受。不适用于判断技能内容质量或提示词优劣。"
description_zh: "在 WorkBuddy 中打包或导入自建 Skill 前的前置校验器，专治四类「解析失败」：目录层级超过两级（根目录/二级目录/文件）、SKILL.md frontmatter 缺少导入端要求的展示与版本字段（display_name、display_name_en、description_zh、description_en、version、category 等）、__pycache__ 等运行时缓存目录被打进包导致层级超限、以及描述字段超过 1000 字符上限（英文描述按中文直译最容易超，中文 356 字符常膨胀到 1000+）。当用户要创建、编辑、打包、导出、分发自建 Skill，或遇到导入报错「目录层级超限」「缺少 Skill 版本号」「缺少 Skill 中文展示名」「Skill 英文描述：当前 N 字符，上限 1000 字符」「解析失败」时使用本技能。它是 skill-creator 的补充：skill-creator 负责怎么写出好技能，本技能负责让写出来的技能能被导入端接受。不适用于判断技能内容质量或提示词优劣。"
description_en: "Pre-flight validator for WorkBuddy Skill packages that prevents the four most common import failures: (1) directory nesting deeper than two levels (root/second-level/files), (2) missing frontmatter fields required by the importer beyond the standard name/description — display_name, display_name_en, description_zh, description_en, version, category, (3) runtime cache folders such as __pycache__ being packaged and blowing the nesting limit, (4) description fields exceeding the 1000-character cap (English descriptions translated from Chinese are the usual offender). Use when creating, editing, packaging, exporting or distributing a custom Skill, or when an import failed with 「目录层级超限」/「缺少 Skill 版本号」/「缺少 Skill 中文展示名」/「Skill 英文描述：当前 N 字符，上限 1000 字符」/ parse errors. Complements skill-creator: skill-creator covers how to author a good skill; this covers making it acceptable to the importer. Not intended to judge content or prompt quality."
category: developer-tools
version: 1.0.1
agent_created: true
---

# 技能包导入自检

## 为什么需要它

`skill-creator` 的 `package_skill.py` **只校验标准 SKILL.md 规范**，它会对一个根本导不进去的包报「✅ Skill is valid!」。导入端的要求更严，且报错是分阶段的——修完层级才报字段，修完字段可能又冒出新的。结果是打包一次、导入失败一次、修一次，来回几轮。

本技能把导入端的全部已知约束一次校验完，在打包**之前**跑。

## 四条已知约束（都来自真实报错）

### 1. 目录最多两级

只允许 `根目录 / 二级目录 / 文件`。三级目录（含根目录本身算第一级）会被拒：

```
✅ skill/SKILL.md
✅ skill/references/a.md
❌ skill/assets/samples/readme.md      ← 三层
❌ skill/scripts/__pycache__/x.pyc     ← 三层，且是**最容易漏掉的**
```

**`__pycache__` 陷阱**：只要用 `python -m py_compile`、或在技能目录里 import 过脚本，就会生成 `scripts/__pycache__/`。它不是手写的，很容易在打包时忘掉。打包前必须删。

**遇到目录超限时的正确改法**：不要只把文件挪个位置——把「需要目录承载的东西」改成单文件。例如用户的语料样本不要放 `assets/samples/*.md`，而是合并为 `assets/samples-guide.md`，运行时数据改为写入单个 `xxx-profile.md`。目录方案在这个约束下注定反复踩坑。

### 2. frontmatter 需要 8 个字段 + agent_created

标准只要求 `name` + `description`，导入端还要求：

```yaml
---
name: my-skill                      # 小写连字符
display_name: 中文展示名
display_name_en: English Display Name
description: "中文长描述（与 description_zh 一致）"
description_zh: "中文长描述"
description_en: "English long description"
category: writing                   # 见下方取值参考
version: 1.0.0                      # x.y.z
agent_created: true
---
```

**description 的写法**：不是一句话摘要，而是**触发条件清单**——写清楚什么话术、什么场景该唤起它，以及**不适用的场景**。触发词要覆盖用户可能说的多种说法。太短的描述会导致技能不被唤起。

`category` 常用取值：`writing`、`developer-tools`、`data-analysis`、`productivity`、`design`、`research`。

**改完 frontmatter 要清缓存再导入**，否则可能仍读到旧值。后续每次改动递增 `version`。

### 3. 描述字段长度上限 1000 字符

`description`、`description_zh`、`description_en` 三个字段各自**不得超过 1000 字符**，超出会被直接拒绝：

```
❌ 解析失败：Skill 英文描述：当前 1125 字符，上限 1000 字符
```

中文描述按**字符数**计（1 个汉字算 1 字符），不是字节数。英文描述最容易超——中文 356 字符的描述，直译成英文往往膨胀到 1000+，因为英文表达同一信息需要更多词。

**压缩时不能砍触发词**——`description` 是导入端判断何时唤起技能的唯一依据，砍掉「查违禁词」「被平台驳回」这类说法，技能就不会被触发。正确的压缩顺序：

1. 删冗余修饰（`high-conversion patterns` → `conversion patterns`）
2. 长句拆并列（`and returns... ; then restructures...`）
3. 删括号内的举例说明（品类清单留 8–10 个代表性的即可，不必求全）
4. 删重复表述（同一限制不必在两个子句里各说一遍）

**建议留 40 字符以上余量**，否则改一个词就再次超限。

### 4. 打包脚本不查以上三项

```
✅ Skill is valid!        ← 只是说符合 skill-creator 规范
```

所以必须自己跑校验，这就是本技能的存在意义。

## 使用方法

```bash
# 校验技能目录（打包前）
python scripts/check_skill_package.py ~/.workbuddy/skills/my-skill

# 校验已打好的 zip（分发给别人之前）
python scripts/check_skill_package.py ./dist/my-skill.zip

# 批量校验所有自建技能
python scripts/check_skill_package.py --all ~/.workbuddy/skills
```

脚本不依赖第三方库（无 pyyaml 时会用内置解析降级），退出码非 0 表示存在问题。

## 标准工作流

1. **建技能时**：`init_skill.py` 生成骨架 → 立刻补齐 8 个 frontmatter 字段，不要留到最后
2. **写内容时**：新增文件只落在根目录或 `references/`、`assets/`、`scripts/` 下
3. **测试脚本时**：用绝对路径执行（`python <绝对路径>/scripts/x.py`），避免在技能目录里产生 `__pycache__`；若已产生，`rm -rf scripts/__pycache__`
4. **打包前**：跑本技能的校验脚本，退出码 0 才打包
5. **打包后**：再校验一次 zip（目录结构可能与磁盘不一致）
6. **导入失败时**：把报错原文对照约束表定位；导入端的校验是分阶段的，修完一项再跑一次

## 约束来源

以上约束来自实际导入报错，非猜测：

| 报错原文 | 对应约束 |
|---|---|
| 目录层级超限 — Skill 包仅支持两级目录结构（根目录/二级目录/文件），请移除子目录嵌套 | 约束 1 |
| 缺少 Skill 版本号（version），请在 SKILL.md frontmatter 中填写 | 约束 2 |
| 缺少 Skill 中文展示名（display_name），请在 SKILL.md frontmatter 中填写 | 约束 2 |
| 缺少 Skill 英文展示名（display_name_en），请在 SKILL.md frontmatter 中填写 | 约束 2 |
| 缺少 Skill 中文描述（description_zh），请在 SKILL.md frontmatter 中填写 | 约束 2 |
| 缺少 Skill 英文描述（description_en），请在 SKILL.md frontmatter 中填写 | 约束 2 |
| Skill 英文描述：当前 1125 字符，上限 1000 字符 | 约束 3 |

导入端可能还有尚未暴露的校验项。遇到新报错时，**把报错原文追加到上表**，并同步更新校验脚本——这是本技能持续变准的方式。
