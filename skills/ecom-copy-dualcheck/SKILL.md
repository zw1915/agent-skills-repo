---
name: ecom-copy-dualcheck
display_name: 电商详情页双检器
display_name_en: E-commerce Listing Copy Dual-Check
description: "电商详情页文案的合规与卖点双检器：先按《广告法》逐句扫描违禁词并给出可落地替换建议，再按品类高转化套路重构卖点表达，输出「合规版」与「优化版」两稿正文及逐条改动说明。当用户提供电商详情页/商品标题/主图文案/直播话术/种草文案草稿，并表达「查违禁词」「广告法合规」「会不会违规」「卖点不突出」「转化率低」「帮我优化详情页」「敏感词检测」「改写成合规版」等意图，或提到天猫/淘宝/京东/拼多多/抖音小店的商品文案审核、被平台驳回、被投诉极限词时，使用本技能。技能把 13 类电商监管类别作为合规参数（普通食品、保健食品、普通/特殊化妆品、医疗器械、母婴、服饰、3C、家居、宠物等），不同类别的红线与必备提示语不同。不适用于纯文学创作、非商业性文案，也不提供规避平台检测的写法（拼音、拆字、谐音、符号替代一律不做）。"
description_zh: "电商详情页文案的合规与卖点双检器：先按《广告法》逐句扫描违禁词并给出可落地替换建议，再按品类高转化套路重构卖点表达，输出「合规版」与「优化版」两稿正文及逐条改动说明。当用户提供电商详情页/商品标题/主图文案/直播话术/种草文案草稿，并表达「查违禁词」「广告法合规」「会不会违规」「卖点不突出」「转化率低」「帮我优化详情页」「敏感词检测」「改写成合规版」等意图，或提到天猫/淘宝/京东/拼多多/抖音小店的商品文案审核、被平台驳回、被投诉极限词时，使用本技能。技能把 13 类电商监管类别作为合规参数（普通食品、保健食品、普通/特殊化妆品、医疗器械、母婴、服饰、3C、家居、宠物等），不同类别的红线与必备提示语不同。不适用于纯文学创作、非商业性文案，也不提供规避平台检测的写法（拼音、拆字、谐音、符号替代一律不做）。"
description_en: "Dual-check for e-commerce listing copy. Step 1 scans each sentence for China Advertising Law violations (superlatives, efficacy claims, absolute promises) with lawful fixes; step 2 rebuilds selling points using category-specific conversion patterns. Returns two drafts — a compliance version (minimal edits) and an optimized version (rewritten) — plus a change log. Use when the user supplies listing copy, titles, main-image text, livestream scripts, or social posts and asks to scan prohibited words, check Advertising Law compliance, fix weak selling points, or rewrite copy as compliant; also when a listing was rejected by Tmall/JD/PDD/Douyin or flagged for extreme claims. Applies 13 category parameters (food, health food, ordinary/special cosmetics, medical devices, mother-and-baby, apparel, 3C, home, pet); red lines and mandatory disclaimers differ by category. Not for literary or non-commercial writing; never helps evade platform detection."
category: writing
version: 1.0.1
agent_created: true
author: 梁樱萍
---

# 电商详情页双检器

详情页文案要过两道关：**别违法**，**别白写**。这个技能把两件事压进一次流程——先逐句扫合规风险并给出可落地的替换方案，再按品类的用户决策路径重构卖点表达。

## 核心判断：类别不是背景信息，是合规规则的参数

同样是「增强免疫力」四个字，放在保健食品详情页是合规的（需蓝帽子与注册功能），放在普通食品详情页就是虚假广告；同样是「美白」，普通化妆品不能宣称，特殊化妆品可以（需注册证号）。**所以品类必须先确认，它决定加载哪套红线**，而不是给报告加个标签。这也是本技能与通用敏感词工具最大的区别。

## 交付物

| 版本 | 定义 | 适用场景 |
|---|---|---|
| **合规版** | 最小改动去违规，保留原文结构与语气 | 已定稿，只想快速上架 |
| **优化版** | 按品类套路重构，痛点/场景/证据/背书重排 | 转化不理想，愿意重写 |

两稿都必须附**逐条改动说明**：改了什么、为什么改、依据哪条法条或哪份材料。不做无声修改——用户看不到改动理由，就没法自己判断对错。

## 执行流程

### 第 1 步：确认两个参数

必问，缺一不可：

1. **产品类别**——从 `references/category-playbooks.md` 的 13 类中选，或由产品描述判定。若用户只说「化妆品」，必须追问**普通化妆品还是特殊化妆品**（只有后者可宣称美白祛斑防晒防脱）。
2. **原稿**——用户贴文本或给文件。

**不接受只给链接。** 详情页多为图片或 JS 渲染，抓到的往往只有结构化字段而非文案本体。若用户给链接，请其复制文本或截图，**不得凭链接猜测内容**。

### 第 2 步：跑合规扫描

```bash
python scripts/compliance_scan.py --file draft.txt --category <类别> --format md
```

脚本负责确定性部分：词库分组匹配、上下文豁免判断、风险分级、逐句定位、输出替换建议与风险指数 CRI。词库与豁免规则见 `references/compliance-rules.md`。

常用参数：
- `--category food|health_food|cosmetic|cosmetic_special|medical_device|mother_baby|apparel|digital|home|pet|finance|general`
- `--format md|text|json`　`--list-categories`　`--list-words --level high`

### 第 3 步：模型复核（脚本之外的三件事，不得省略）

脚本只能匹配词，以下必须读文判断：

1. **句子级误导**——整句无违禁词，但变相宣称了不得宣称的内容。例：「用了一个月，脸上的斑淡了」没有「祛斑」二字，实为祛斑功效宣称，属违规（普通化妆品）。
2. **对比误导**——贬低同行（「比某大牌好用」「效果碾压进口货」）、无依据对比。
3. **证明材料核验**——文中的专利号、检测报告、销量排名、认证是否真实存在。无材料支撑即标 🟠 并要求补证，**不得默认其成立**。

脚本判 🟡 而语境确实违规的**上调**，脚本误报的（如「100% 棉」是成分标注）**下调**——以模型判定为准，但必须在报告的「复核调整」栏写明调整理由。脚本与模型结论不一致时不掩饰，直接展示分歧。

### 第 4 步：卖点重构

读 `references/category-playbooks.md` 取该品类的用户决策路径与套路，按 `references/rewrite-playbook.md` 的五步重排：

**痛点前置 → 场景代入 → 证据支撑 → 信任背书 → 行动指令**

三条铁律：
- **不得为卖点好看而新增未提供的功效、数据、资质。** 缺证据只能写 `【待补：检测报告编号】` 占位。
- **不得跨类升级。** 普通食品不写成保健品，化妆品不写成药品，非医疗器械不写「医用级」。
- **每个改写后的卖点都必须能被原稿或用户提供的信息支撑。** 复核方法是逐句回溯：这句的依据在原稿哪一行。

### 第 5 步：交付

按 `assets/template-report.md` 出体检报告 + 对比表 + 两稿；正文用 `assets/template-copy.md`。

## 硬约束

1. **合规优先于转化。** 优化版与合规冲突时以合规为准，并说明因此放弃了哪个卖点。
2. **不做无声改动。** 任何替换都要在对比表里出现。
3. **不虚构。** 数据、资质、证书、检测报告、用户评价一律不得编造。
4. **不提供规避监管的写法。** 用户要求「绕开广告法」「躲过平台检测」时明确拒绝，并说明：本技能做的是**换一种合法的说法**，不是**把违禁词藏起来**。拼音、拆字、谐音、生僻字、符号/emoji 替代违禁词，一概不做。
5. **强监管类目须提示。** 保健食品、医疗器械、药品、金融产品除本技能规则外，须提示用户以主管部门审查（广告审查批准文号、注册备案）为准，本技能结论不构成法律意见。
6. **不做绝对结论。** 报告用「风险等级」而非「一定违规/一定合法」表述——执法与平台审核存在裁量空间。

## 资源

| 文件 | 用途 |
|---|---|
| `references/compliance-rules.md` | 违禁词库（分级 / 法条依据 / 替换建议）+ 上下文豁免规则 |
| `references/category-playbooks.md` | 13 类品类的监管红线、必备提示语、用户决策路径、高转化套路 |
| `references/rewrite-playbook.md` | 卖点重构五步法、FAB 转译、句级改写手法、过改反例 |
| `assets/template-report.md` | 体检报告 + 改动对比表模板 |
| `assets/template-copy.md` | 合规版 / 优化版 正文模板 |
| `scripts/compliance_scan.py` | 确定性合规扫描（词库匹配 / 分级 / 豁免 / 替换建议） |

## 打包与导入约束

> **目录层级**：Skill 包仅支持两级（根目录 / 二级目录 / 文件）。新增文件必须落在
> `references/`、`assets/`、`scripts/` 之下或根目录，**不得创建三级目录**，否则导入被拒。
> 运行时产物（体检报告、双稿）写到工作区，不要写进技能目录。
>
> **frontmatter**：导入端要求 8 个字段——`name`、`display_name`、`display_name_en`、
> `description`、`description_zh`、`description_en`、`category`、`version`，
> 外加 `agent_created: true`。标准 SKILL.md 只规定 `name` + `description`，
> 其余字段缺失会导致「解析失败」。
>
> **以上两项 `package_skill.py` 都不校验**（它只报 "Skill is valid"），打包后必须自行复核：
> `find <skill目录> -mindepth 3`（有输出即层级违规）；
> 解包用 yaml 解析 frontmatter 确认字段非空。改动 frontmatter 后需清缓存再导入。
