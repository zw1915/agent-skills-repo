---
name: worldview-distiller
display_name: 长篇语料观点萃取专家团
display_name_en: Long-Form Corpus Worldview Distiller (Expert Team)
description: "将长篇个人叙事、论坛连载、随笔合集、访谈转录等庞杂语料，提炼为结构化「世界观图谱 + 分主题观点 + 可操作建议 + 合规边界」的专家团技能。当用户表达「总结这本书/这个文档的观点」「提炼文集里的世界观」「把聊天记录/帖子/随笔萃取成框架」「长篇语料太散了我看不过来帮我梳理」「做个观点地图/思想图谱」「把连载帖归纳成体系」等意图，或丢入超大 txt/md/doc 个人文集、多年博客、论坛存档、口述史转录时，使用本技能。核心机制：由 4 个专家角色协作——语料结构分析师（分段/时间线/体裁识别）、思想体系萃取师（跨主题世界观坐标）、生活智慧与案例整理师（可操作建议+反例）、合规与边界审查师（标记未可验证/政治敏感/个人内容，仅梳理框架不采信不放大）；输出严格遵循 references/output-template.md 的统一结构。不适用于纯学术论文综述（用学术检索类技能）、不适用于事实核查新闻（用事实核查类技能）、不适用于代写。"
description_zh: "将长篇个人叙事、论坛连载、随笔合集、访谈转录等庞杂语料，提炼为结构化「世界观图谱 + 分主题观点 + 可操作建议 + 合规边界」的专家团技能。当用户表达「总结这本书/这个文档的观点」「提炼文集里的世界观」「把聊天记录/帖子/随笔萃取成框架」「长篇语料太散了我看不过来帮我梳理」「做个观点地图/思想图谱」「把连载帖归纳成体系」等意图，或丢入超大 txt/md/doc 个人文集、多年博客、论坛存档、口述史转录时，使用本技能。核心机制：由 4 个专家角色协作——语料结构分析师（分段/时间线/体裁识别）、思想体系萃取师（跨主题世界观坐标）、生活智慧与案例整理师（可操作建议+反例）、合规与边界审查师（标记未可验证/政治敏感/个人内容，仅梳理框架不采信不放大）；输出严格遵循 references/output-template.md 的统一结构。不适用于纯学术论文综述（用学术检索类技能）、不适用于事实核查新闻（用事实核查类技能）、不适用于代写。"
description_en: "Expert-team skill that distills long-form narratives, forum serials, essays, and interview transcripts into a structured deliverable: worldview coordinates, per-theme viewpoints, actionable advice, and compliance boundaries. Trigger on requests like summarize this book/doc, extract the worldview, turn posts into a framework, too scattered help me structure it, make a viewpoint map, turn serial posts into a system; or given an oversized personal txt/md/doc corpus, multi-year blog, forum archive, or oral-history transcript. Four roles: Corpus Structure Analyst, Thought-System Extractor, Life-Wisdom and Case Curator, Compliance Reviewer (flags unverifiable or sensitive content, maps frame only). Output follows references/output-template.md. Not for academic surveys, news fact-checking, or ghostwriting."
category: research
version: 1.0.0
agent_created: true
author: 梁樱萍
---

# 长篇语料观点萃取专家团（worldview-distiller）

把"读不完、理不清"的长篇个人语料，变成一张可复用的世界观图谱与观点清单。

## 何时用

- 用户丢来超大个人文集 / 论坛连载 / 多年博客 / 口述史转录 / 聊天记录归档，要求"总结观点""提炼世界观""梳理成体系"。
- 用户明确要做"观点地图 / 思想图谱 / 世界观萃取"。
- **不适用**：纯学术论文的文献综述（交给学术检索类技能）、新闻事实核查、代写。

## 专家团角色（必须按此分工协作）

| 角色 | 职责 | 必须产出的东西 |
|---|---|---|
| **① 语料结构分析师** | 读本、切分时间线/主题块、识别体裁（随笔/答疑/小说/史料/玄学见闻） | 体量说明 + 体裁分布表 + 采样策略 |
| **② 思想体系萃取师** | 跨主题抽取一以贯之的底层逻辑，形成"世界观坐标系" | 3–6 条世界观坐标 + 分主题观点 |
| **③ 生活智慧与案例整理师** | 从可操作角度提炼建议、正例、反例（健康/财富/人际/心智） | 分主题"可操作建议 + 反例清单" |
| **④ 合规与边界审查师** | 标记未可验证主张、政治敏感叙事、个人私密内容；只梳理框架，不采信、不放大、不传播 | 边界声明段落 + 需设限的条目清单 |

> 四个角色的输出**合并**为一份文档，结构见 `references/output-template.md`。模型必须依次调用四角色视角，缺失任一角色即视为不合格。

## 执行流程（确定性步骤 + 判断性步骤）

**确定性（可脚本化，优先交给脚本）：**
1. 体量探测：`wc -l` / 行数、字节数；定位年份/章节锚点（如 `^－－－\d{4}年－－－`、空行分隔的帖标题）。
2. 分层采样：逐年开篇读 30–50 行 + 关键主题节点（用 Grep 抓高频词/《》标题/问答标记）。
3. 体裁打标：用正则/关键词识别"答疑体（答：）""连载小说""史料演义""健康方"。

**判断性（必须模型完成，不得省略）：**
4. 思想体系萃取师：归纳世界观坐标——**宁少勿滥**，每条须有原文支撑。
5. 生活智慧整理师：区分"可操作建议"与"个人神秘叙事"，前者吸收、后者标注为文体样本。
6. 合规审查师：**遇到政治敏感、未可验证史实、个人隐私，只写"存在此类体裁/框架"，不展开、不采信、不传播**；健康类一律加"就医优先"边界。
7. 语言体识别：标注"戏谑/认真"语气，避免把调侃当论断。

## 关键边界（硬约束）

- **不逐行通读也可交付**：庞杂语料必须分层采样，明确写出"基于代表性采样，非逐行通读"，不假称全读。
- **政治敏感内容**：仅作为"文档体裁之一"标注其存在与叙事框架，**不采信为史实、不展开具体政治论断、不传播**。
- **健康/医疗建议**：一律标注"个人经验，不能替代专业就医"。
- **不编造**：未在原文本出现的数据、文献、案例不得补入；缺失素材处写"原文未提供"。

## 输出

写一份 Markdown 文档，严格遵循 `references/output-template.md` 的章节顺序与表格化格式，并 `present_files` 呈现。

## 与相邻技能分工

| 技能 | 关系 |
|---|---|
| `skill-creator` | 本技能本身的写法方法论 |
| `skill-package-guard` | 本技能能否被导入的校验器 |
| 学术检索类 / 事实核查类 | 本技能不替代，遇纯学术或新闻核查应转交 |
