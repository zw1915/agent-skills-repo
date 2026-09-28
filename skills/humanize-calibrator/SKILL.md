---
name: humanize-calibrator
display_name: 人味校准器
display_name_en: Humanize Calibrator
description: "人味校准器：对 AI 生成或 AI 味偏重的文本做可量化的深度改写。当用户表达「去 AI 味」「太像 AI 写的」「套话太多」「读起来不像人话」「太模板化」「内容同质化」「帮我改得自然一点」「更像我自己写的」「有个人风格」，或要求 AI 对自己刚产出的内容做自我修正、降低套路感、提升可读性与个人语感时，使用本技能。它把「人味」拆成 7 个可检测维度（结构机械、词汇空泛、细节缺失、立场模糊、节奏单一、逻辑套壳、信息增量低），先体检打分、再定向改写、后复检对比，输出「修改前后对比」报告并沉淀可迭代的个人校准档案——它更像写作教练，而不是一次性改写工具。不适用于纯翻译、纯错别字或语法纠错、格式转换，以及用户明确要求保留 AI 风格或仅需公文/学术润色的场景。"
description_zh: "人味校准器：对 AI 生成或 AI 味偏重的文本做可量化的深度改写。当用户表达「去 AI 味」「太像 AI 写的」「套话太多」「读起来不像人话」「太模板化」「内容同质化」「帮我改得自然一点」「更像我自己写的」「有个人风格」，或要求 AI 对自己刚产出的内容做自我修正、降低套路感、提升可读性与个人语感时，使用本技能。它把「人味」拆成 7 个可检测维度（结构机械、词汇空泛、细节缺失、立场模糊、节奏单一、逻辑套壳、信息增量低），先体检打分、再定向改写、后复检对比，输出「修改前后对比」报告并沉淀可迭代的个人校准档案——它更像写作教练，而不是一次性改写工具。不适用于纯翻译、纯错别字或语法纠错、格式转换，以及用户明确要求保留 AI 风格或仅需公文/学术润色的场景。"
description_en: "Quantifiable deep rewriter for AI-sounding text. Use when the user asks to remove the AI flavor, says it sounds too AI-written, has too much boilerplate, reads like a template, feels homogenized, wants it to read more naturally or sound more like them, or asks the model to self-correct a draft it just produced. Scores text on 7 measurable dimensions (mechanical structure, empty vocabulary, missing specifics, no stance, flat rhythm, boilerplate logic, low information gain), then diagnoses, rewrites, re-verifies against the same rubric, and returns a before/after diff plus an iterable calibration profile. A writing coach rather than a one-shot rewriter. Not for pure translation, proofreading, format conversion, or keeping a formal/academic tone."
category: writing
version: 1.0.0
agent_created: true
author: 梁樱萍
---

# 人味校准器（Humanize Calibrator）

## 这个技能解决什么

AI 产出的文本最大的问题不是错，而是「对得没有信息量」：套话密度高、结构机械、
细节缺席、立场骑墙、句句正确但读完什么都没留下。笼统地下「去 AI 味」指令之所以
效果不稳定，是因为没有人知道到底哪里像 AI，改完之后也无从验证、无法收敛。

本技能把「人味」拆成 **7 个可检测维度**，先量化体检，再定向改写，最后用同一把尺子
复检，并输出逐条「修改前后对比」。每一次修改都可解释、可复现、可迭代。

## 何时使用

触发信号（出现任一即适用）：

- 「去 AI 味 / 太像 AI 写的 / 套话太多 / 不像人话 / 太模板化 / 同质化严重」
- 「帮我改得自然一点 / 更像我自己写的 / 更有个人风格 / 更像我说话的样子」
- AI 刚产出的长文需要二次打磨，或用户抱怨「改了一遍还是老样子」
- 需要建立并沿用一个稳定的个人写作风格（尤其当用户提供了自己的语料样本时）

不适用：

- 纯翻译、纯错别字或语法纠错、格式转换 —— 这些不是校准问题
- 用户只想润色公文/学术文本且明确要求保持正式腔 —— 除非用户同时要求降 AI 味
- 用户要求从零代写 —— 那是创作任务。可先创作，再用本技能复查，但不要以校准替代创作

## 核心工作流（四步闭环，不可跳步）

### 第 1 步 · 体检（Diagnose）：先量化，再动笔

1. 若环境可用 Python，先跑确定性扫描拿到客观指标：

   ```bash
   python scripts/tone_scan.py --file <输入文件> --format md
   # 无文件时： --text "待检测文本"   或   直接通过 stdin 传入
   ```

   脚本输出：黑话命中词与频次、机械序号词频、套路连接词频、句长均值/标准差/最长最短比、
   段落长度方差、短句占比、第一人称占比、具体信息（数字/日期/百分比）密度。

2. 结合扫描结果，按 `references/checklist.md` 对 7 个维度逐项打子分（0–10），
   按权重加权换算成 **人味指数 HI（0–100）**。

3. 产出「人味体检表」：每维度给出子分、证据（**引用原文片段**）、命中规则编号。

   **铁律：只给总分不给证据的体检表视为无效。** 任何判断都必须能指回原文的具体字句。

打分口径与权重见 `references/checklist.md`；词表与句式套路见 `references/patterns.md`。

### 第 2 步 · 改写（Rewrite）：对症下药，逐维度开处方

按体检表中得分最低的维度优先处理，每个维度对应固定手法（见
`references/checklist.md` 的「改写处方」列）。通用铁律：

- **只改表达，不改观点。** 论点、结论、数据、事实一律保持原意。改写不是重写观点。
- **细节用真、不用编。** 原文缺少具体案例或数字时，绝不虚构，改写处以
  `【待补：请提供××的具体例子】` 占位，并在报告末尾汇总成待补清单。
- **文体契约优先。** 先判断原文文体（营销文案 / 公众号 / 报告 / 学术 / 公文 / 朋友圈），
  改写幅度与口语化程度必须服从该文体。合同、公文、论文严禁改成随笔腔。
- **保留专业术语。** 行业术语不等于 AI 味。判断标准是：该词是否携带可验证信息？
  带信息的术语保留，空转的黑话替换。混淆「黑话」与「术语」是本技能最常见的失败方式。
- **人味 ≠ 网感。** 禁止为了「像人」而堆 emoji、网络流行语、「家人们」「谁懂啊」式
  表演性口语。这属于过改，比不改更糟。护栏清单见 `references/calibration.md`。

### 第 3 步 · 复检（Re-verify）：用同一把尺子量

对改写稿重跑一遍相同的清单与脚本，给出 after 分数。通过标准：

- HI 提升 ≥ 15 分，**且**
- 7 个维度中无任一项低于 6 分，**且**
- 未引入新问题（新增黑话、新增套路连接词、专业性下降、语病）

未过线则定点再修。总轮次上限 3 轮，超过后如实告知用户剩余短板，不要无限循环。

### 第 4 步 · 校准（Calibrate）：把反馈变成资产

输出完整的「修改前后对比」报告（模板：`assets/report-template.md`），并在末尾给出
3 个可选的再校准方向（例：「再短一点 / 再锋利一点 / 更像口语 / 保留全部术语」）。
收到用户反馈后：

1. 按反馈做定向修正，并说明这次调整改的是哪一条规则；
2. 把稳定偏好写入用户级校准档案
   `~/.workbuddy/skills/humanize-calibrator/calibration-profile.md`
   （用户偏爱文体、必须保留的词、忌讳词、历史反馈与由此生效的规则调整；
   用户本人的写作样本也粘贴进同一文件的「语料样本」章节）；
3. 此后每次改写**先读该档案，再开始体检**。

**这一步是本技能与一次性改写工具的本质差别：它让「反馈」变成可累积的资产。**

机制细节、档案结构与轮次规则见 `references/calibration.md`。

## 输出格式

每次校准固定交付以下六项，顺序不变：

1. **人味体检表（Before）** —— 7 维度子分 + 原文证据摘录 + HI + 等级判定
2. **改写稿（After）** —— 完整、可直接使用的正文，不得省略或以「……」略过
3. **修改前后对比表** —— `# | 原文片段 | 命中的 AI 味特征 | 改后片段 | 改了什么、为什么`
   逐条对应体检表命中的规则。**这是用户最关心的部分，不得省略、不得合并同类项。**
4. **复检表（After 分数）与过线判定** —— 附未过线时的残余短板说明
5. **待补清单** —— 需要用户提供真实细节的占位处
6. **下一步校准选项** —— 3 个方向供用户选择

模板见 `assets/report-template.md`。

## 资源索引

| 文件 | 用途 |
|---|---|
| `references/checklist.md` | 7 维度可量化清单、权重、评分口径、逐维度改写处方 |
| `references/patterns.md` | AI 味模式库：黑话词表、句式模板、结构套路、正反示例对照 |
| `references/calibration.md` | 迭代校准机制、校准档案结构、过改护栏、文体契约 |
| `assets/report-template.md` | 交付报告模板 |
| `assets/voice-samples-guide.md` | 个人语料样本的采集与提取指南（样本本身粘贴进校准档案） |
| `scripts/tone_scan.py` | 确定性文本体检脚本（词频 / 句长 / 结构统计） |

> **打包与导入约束（维护本技能时务必遵守）**
>
> 1. **两级目录上限**：Skill 包仅支持「根目录 / 二级目录 / 文件」。新增文件只能落在
>    根目录，或 `references/`、`assets/`、`scripts/` 之下，**不要创建三级目录**。
>    运行时状态（校准档案、用户语料）一律以**单文件**读写，不建样本目录。
> 2. **frontmatter 必需字段**：导入端除 `name` / `description` 外还要求
>    `version`、`display_name`、`display_name_en`、`description_zh`、`description_en`，
>    缺任一项会被拒绝导入。修改 frontmatter 后清空缓存重新导入，
>    否则仍可能读到旧值。
> 3. **改完要自检**：`find <技能目录> -mindepth 3` 有输出即为目录违规；
>    frontmatter 用 YAML 解析器校验一遍。注意 `package_skill.py` 这两项都不检查，
>    它只会报「Skill is valid」。
