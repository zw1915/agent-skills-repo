---
name: viral-structure-decoder
display_name: 爆款结构逆向拆解器
display_name_en: Viral Structure Decoder
description: "跨平台爆款内容结构逆向拆解器。当用户丢入内容链接（或文本、截图），希望分析「这条为什么火」「帮我拆解这条爆款」「它的结构是什么」「我想照着这个结构写我的选题」，或要求把某条高互动内容转成可复用写作模板时，使用本技能。技能自动识别平台类型并套用对应拆解框架：小红书拆「封面标题组合＋正文钩子＋互动引导」，公众号拆「开篇引入法＋小标题逻辑链＋金句收尾」，知乎拆「问题定义＋论证结构＋情绪落点」，另含视频号、抖音、B站、微博、播客与通用兜底框架。输出一份可填空的「可复用结构模板」，并询问是否基于该模板进行二创。不适用于纯文案润色、不提供链接或原文就会凭空的「爆款预测」、以及要求直接搬运或洗稿他人内容的请求。"
description_zh: "跨平台爆款内容结构逆向拆解器。当用户丢入内容链接（或文本、截图），希望分析「这条为什么火」「帮我拆解这条爆款」「它的结构是什么」「我想照着这个结构写我的选题」，或要求把某条高互动内容转成可复用写作模板时，使用本技能。技能自动识别平台类型并套用对应拆解框架：小红书拆「封面标题组合＋正文钩子＋互动引导」，公众号拆「开篇引入法＋小标题逻辑链＋金句收尾」，知乎拆「问题定义＋论证结构＋情绪落点」，另含视频号、抖音、B站、微博、播客与通用兜底框架。输出一份可填空的「可复用结构模板」，并询问是否基于该模板进行二创。不适用于纯文案润色、不提供链接或原文就会凭空的「爆款预测」、以及要求直接搬运或洗稿他人内容的请求。"
description_en: "Cross-platform reverse-engineering of viral content structure. Use when the user drops in a content link (or pasted text or a screenshot) and asks why it performed well, asks to deconstruct a hit post, wants its structure explained, or wants it turned into a reusable writing template. Auto-detects the platform and applies the matching framework: Xiaohongshu (cover-title pairing + body hook + engagement prompt), WeChat Official Accounts (opening device + subhead logic chain + closing punchline), Zhihu (problem framing + argument structure + emotional landing), plus WeChat Channels, Douyin, Bilibili, Weibo, podcasts, and a generic fallback. Outputs a fill-in-the-blank reusable structure template and asks whether to write an original piece from it. Not for copy polishing, baseless hit prediction without source material, or requests to copy or rewrite others' content wholesale."
category: writing
version: 1.0.0
agent_created: true
author: 梁樱萍
---

# 爆款结构逆向拆解器（Viral Structure Decoder）

## 这个技能解决什么

爆款不是灵感，是结构。同一个结构换一个选题仍然能打，这是创作者最想拿到的东西——
但大多数人拆解只停在「这条写得好」的印象层，说不出好在第几句、好在什么位置、
好在哪个可替换的变量上。

本技能把「拆解」从单一平台扩展为跨平台，并把拆解结果落成一份**可填空、可复用、
可迁移到新选题的结构模板**。

## 何时使用

触发信号：

- 用户丢来一条链接 / 一段文本 / 一张截图，问「这条为什么火」「帮我拆解一下」
- 「这个结构是怎么搭的」「它的钩子在哪」「我想照着这个写我的选题」
- 「帮我做个小红的爆款结构模板」「把这条爆款转成模板」
- 用户想对比多条同类内容，找出共同结构

不适用：

- **纯文案润色**：那是改写任务，应改用 `humanize-calibrator` 技能
- **没有素材的爆款预测**：「帮我预测什么会火」——没有源文本可拆，只能给通用建议，
  要如实说明这一点，不要伪装成拆解
- **要求搬运或洗稿**：只做结构复用，不做内容搬运。见下方合规边界

## 合规边界（先讲清，再动手）

| 可以做 | 不可以做 |
|---|---|
| 拆出**结构、套路、节奏、框架**并复用 | 逐句改写原文、替换同义词后发布（洗稿） |
| 引用少量原文作为**证据**（标明出处） | 大段复制原文当作用户自己的输出 |
| 借鉴「选题角度」与「表达类型」 | 复刻他人**个人经历、独家数据、原创观点** |
| 说明「这个结构适合什么选题」 | 承诺「照这个写就一定会火」 |

拆解时**引用原文仅用于举证**，并在引用处标注来源。二创时必须换掉：原始事实、
个人经历、独家数据、具体案例；可以保留：结构、节奏、钩子类型、段落功能。

## 工作流（五步，不可跳步）

### 第 1 步 · 取内容

1. 若输入是链接，先跑平台识别：

   ```bash
   python scripts/decode_scan.py --url "<链接>"
   ```

   输出平台类型、内容形态、抓取难度与建议路径。

2. 按抓取难度决定策略（详见 `references/extraction.md`）：

   | 难度 | 平台 | 策略 |
   |---|---|---|
   | 低 | B站、播客、个人博客 | 可直接抓取正文或简介 |
   | 中 | 公众号、知乎、微博 | 先试抓取，失败则请用户粘贴 |
   | 高 | 小红书、视频号、抖音 | 反爬/需登录，**直接请用户粘贴文本或截图**，不要反复重试 |

3. **抓不到就问，不要编。** 拿不到正文时明确告知用户，并给出三种替代：
   粘贴文本、发截图（可用 Read 读取图片）、只给标题+首段做局部拆解。
   **绝不允许在没拿到原文的情况下假装做了拆解。**

### 第 2 步 · 结构扫描（拿到客观骨架）

```bash
python scripts/decode_scan.py --file content.md --platform xiaohongshu --format md
```

输出可核对的硬数据：标题组合构成、首句钩子命中的类型、段落数与字数分布、
小标题位置与间隔、独立成段的短句（金句候选）、互动引导句、话题标签、
第二人称密度、数字密度。

**这些数据是拆解的骨架。** 后续每一层分析都要能指回具体位置
（「第 3 段」「第 2 个小标题之后」），不要写「整体节奏把握得很好」这类空话。

### 第 3 步 · 套框架逐层拆解

按识别出的平台取对应框架（完整版见 `references/frameworks.md`）：

| 平台 | 拆解框架 |
|---|---|
| 小红书 | 封面标题组合 → 正文钩子 → 互动引导 |
| 公众号 | 开篇引入法 → 小标题逻辑链 → 金句收尾 |
| 知乎 | 问题定义 → 论证结构 → 情绪落点 |
| 视频号 | 前 3 秒钩子 → 结构节奏 → 结尾引导 |
| 抖音 / 快手 | 3 秒钩子 → 完播结构 → 互动引导 |
| B站 | 标题封面 → 开场承诺 → 章节推进 → 三连引导 |
| 微博 | 热点锚点 → 观点爆点 → 转发话术 |
| 播客 / 长音频 | 开场承诺 → 话题分段 → 结尾钩子 |
| 其他 / 不确定 | 通用五层：注意力 → 承诺 → 主体 → 情绪 → 引导 |

**每个拆解层必须回答三件事**：用了什么手法、在哪个位置、为什么它能起作用。
只说「用了悬念」不够，要说清「悬念挂在第 2 段的哪个问题上，读者为了知道答案才读到第 5 段」。

### 第 4 步 · 输出「可复用结构模板」

把拆解结果转成**填空式模板**，让用户换掉变量即可迁移到自己的选题。
这是本技能的主交付物，规格见 `references/output-spec.md`，模板见
`assets/template-structure.md`。

模板中必须包含：

- **结构骨架**：逐句/逐段的功能标注（第 1 句做什么、第 2 段做什么）
- **可替换变量**：哪些是主题相关的（换掉），哪些是结构性的（保留）
- **适用选题范围**：这个结构适合哪类内容，不适合哪类
- **风险提示**：这个结构的短板（例：需要真实案例支撑，否则会显得空）

### 第 5 步 · 询问是否二创

模板交付后**主动询问**，给三个明确选项：

1. **直接二创**：用户给新选题，我按该结构写一版
2. **调整结构**：用户想改哪一层（钩子类型 / 段数 / 语气强度）
3. **只留模板**：存下来自己用

询问时说明二创会遵守合规边界（换掉原始事实与个人经历，只留结构）。

## 输出格式

固定交付以下五项：

1. **来源与平台判定** —— 平台、内容形态、抓取方式、是否成功取得全文
2. **结构扫描数据** —— 脚本输出的硬指标（标题构成、钩子类型、节奏数据）
3. **逐层拆解** —— 按平台框架分层，每层都带位置与作用
4. **可复用结构模板** —— 填空式，可直接迁移到新选题
5. **二创询问** —— 三个选项

拆解报告模板见 `assets/template-decoding.md`。

## 资源索引

| 文件 | 用途 |
|---|---|
| `references/frameworks.md` | 各平台拆解框架详解、话术模式库、通用五层兜底模型、新增平台扩展模板 |
| `references/extraction.md` | 内容获取流程、各平台抓取难度、失败降级策略、字段清单 |
| `references/output-spec.md` | 交付物字段规格、合规边界细则、二创衔接 |
| `assets/template-decoding.md` | 拆解报告模板 |
| `assets/template-structure.md` | 可复用结构模板 |
| `scripts/decode_scan.py` | 平台识别 + 结构骨架量化扫描 |

> **打包与导入约束（维护本技能时务必遵守）**
>
> 1. **两级目录上限**：Skill 包仅支持「根目录 / 二级目录 / 文件」。新增文件只能落在
>    根目录，或 `references/`、`assets/`、`scripts/` 之下，**不要创建三级目录**。
> 2. **frontmatter 必需字段**：导入端除 `name` / `description` 外还要求
>    `version`、`display_name`、`display_name_en`、`description_zh`、`description_en`，
>    缺任一项会被拒绝导入。
> 3. **改完要自检**：`find <技能目录> -mindepth 3` 有输出即为目录违规；
>    frontmatter 用 YAML 解析器校验。注意 `package_skill.py` 这两项都不检查。
