---
name: fapai-bargain-radar
display_name: 法拍房捡漏雷达
display_name_en: Judicial Auction Bargain Radar
description: "法拍房（司法拍卖房产）捡漏辅助与排名技能：帮用户检索、评估并排名司法拍卖房源，筛出「折价高且风险可控」的标的。v2 重写：诚实标注各数据源可抓取性（淘宝/法院网/京东需真实浏览器，公拍网可用脚本直连），内置已实测的自动抓取脚本(fetch_gpai.py)、支持批量打分+排名+Top-N（直接满足「各推荐十套」），价格单位(元/万)自动识别、评估价缺失时以市场价兜底，并在自动抓取失败时给出明确降级动作与自取步骤卡。覆盖折价率测算、风险尽调清单（占用腾退/税费/土地性质/租赁/户口/抵押/法拍贷）与出价策略。触发词：法拍房捡漏、司法拍卖怎么买、看法拍房值不值、法拍房折价率、法拍房风险、哪里看法拍房源、法拍房尽调、帮我列/推荐N套法拍房、按折价排名。不适用于普通二手房、新房、商业地产分析。"
description_zh: "法拍房（司法拍卖房产）捡漏辅助与排名技能：帮用户检索、评估并排名司法拍卖房源，筛出「折价高且风险可控」的标的。v2 重写：诚实标注各数据源可抓取性（淘宝/法院网/京东需真实浏览器，公拍网可用脚本直连），内置已实测的自动抓取脚本(fetch_gpai.py)、支持批量打分+排名+Top-N（直接满足「各推荐十套」），价格单位(元/万)自动识别、评估价缺失时以市场价兜底，并在自动抓取失败时给出明确降级动作与自取步骤卡。覆盖折价率测算、风险尽调清单（占用腾退/税费/土地性质/租赁/户口/抵押/法拍贷）与出价策略。触发词：法拍房捡漏、司法拍卖怎么买、看法拍房值不值、法拍房折价率、法拍房风险、哪里看法拍房源、法拍房尽调、帮我列/推荐N套法拍房、按折价排名。不适用于普通二手房、新房、商业地产分析。"
description_en: "Judicial-auction (法拍房) bargain radar: screen, score and RANK court-auctioned homes to surface high-discount, low-risk bargains. v2 rewrite: honestly flags which sources are auto-fetchable (Taobao/rmfysszc/JD need a real browser; gpai.net is scriptable), ships a tested fetch script (fetch_gpai.py), supports BATCH scoring + ranking + Top-N (directly fulfills 'recommend 10 per city'), auto-detects price units (元/万) and falls back to market price when appraisal is missing, and provides a clear degradation path (self-service step card + pasted-list scoring) when auto-fetch fails. Covers discount-rate math, a due-diligence checklist and bidding strategy. Triggers: 法拍房捡漏, 司法拍卖怎么买, 看法拍房值不值, 法拍房风险, 哪里看法拍房源, 帮我列/推荐N套法拍房, 按折价排名. Not for resale second-hand homes, new builds or general commercial RE."
category: research
version: 2.0.0
agent_created: true
author: 梁樱萍
---

# 法拍房捡漏雷达（v2）

帮你**发现、评估并排名**司法拍卖房产（法拍房）里的「捡漏」机会——以明显低于市场价取得产权、且风险可控的标的。

> v2 相对 v1 的关键改动：① 不再假设"能自动抓全量"，**诚实标注每个数据源的可抓取性**；② 内置一个**实测可用**的自动抓取脚本（公拍网）；③ 评分脚本支持**批量打分 + 排名 + Top-N**，直接满足"各推荐十套"；④ 价格单位(元/万)自动识别、评估价缺失时以市场价兜底；⑤ 自动抓取失败时给出**明确降级动作**与自取步骤卡。

## 何时使用

- 用户想「看法拍房能不能捡漏」「哪里能看法拍房源」「某套法拍房值不值」
- 用户要「帮我列出/推荐 N 套法拍房」「按折价率排名」「长沙/衡阳各来 10 套」
- 用户提到 法拍房 / 司法拍卖 / 法拍，并关心折价、风险、尽调、参拍

## 核心工作流（按序执行）

### 1. 明确需求边界（模型判断，不得省略）
先确认：目标城市与板块、预算上限、是否自住（影响户型/学区权重）、全款 vs 法拍贷、风险承受度。这些决定后面筛选口径。

### 2. 检索房源 —— 分层策略（本技能重点）
按"能自动跑的优先、需浏览器的引导、失败则降级"三层执行：

**2.1 数据源现实（实测结论，务必照此预期）**

| 平台 | 能否自动抓取 | 说明 / 方法 |
|---|---|---|
| 公拍网 gpai.net | ✅ 可脚本直连（但**不按城市过滤**） | 服务端渲染，Python 可直连；搜索走 `POST s.gpai.net/Sf/Search.do`（先访问首页种 cookie，再 POST 并跟随 307 重定向）。**实测 `q=城市` 关键词不会按城市过滤**，返回全国混合流（以上海/华东为主）。脚本 `fetch_gpai.py` 只能拉回「≤价格 的全站标的」，需用户按法院/地区人工筛。**不能作为长沙/衡阳的可靠主源**，仅作补充。 |
| 淘宝司法拍卖 sf.taobao.com | ⚠️ 需真实浏览器 | 房源全国最多，但**城市/价格筛选纯前端 JS**，直连搜索页/分类页为空或跳登录。必须 `agent-browser` 才能按城市过滤；HTTP/WebFetch 拿不到城市级数据。 |
| 人民法院诉讼资产网 rmfysszc.gov.cn | ⚠️ 需真实浏览器 | 官方最权威，但筛选表单 AJAX，裸 HTTP 被 WAF 挡成 521。需浏览器。 |
| 京东司法拍卖 auction.jd.com/sifa.html | ⚠️ 需真实浏览器 | JS 动态加载，需浏览器。 |

**2.2 能自动跑的（仅作补充，非城市主源）：** `python <技能目录>/scripts/fetch_gpai.py --keyword 住宅 --max-price 30`（拉回公拍网全站 ≤30万 标的，结果需按法院/地区人工筛；详见脚本头注释与数据源现实表）。长沙/衡阳主源仍靠淘宝/法院网。

**2.3 需浏览器的（淘宝/法院网/京东）：** 加载 `agent-browser` 技能做定向抓取；或先给用户**自取步骤卡**（`references/platforms-and-risks.md` 第五节），让其自行筛选后把清单贴回。

**2.4 降级动作（自动抓取失败时，必须执行，不得假装成功）：**
1. 明确告诉用户"为何自动抓取受限"（引用 2.1 表格）；
2. 给出**自取步骤卡**（哪个平台、怎么筛、筛完贴回）；
3. 接受用户粘贴的清单（标题/起拍价/评估价/城市），用第 3 步批量打分排名。
> ❗ 绝不为凑数编造房源。只输出已验证存在的标的或用户提供的标的。

### 3. 量化评分与排名（确定性，交给脚本）
- **单套：** `python scripts/score_listing.py --starting 280 --appraisal 400 --tax 各付 --occupancy 空置`
- **批量（推荐用法，直接出 Top-N）：**
```bash
python scripts/score_listing.py --batch listings.json --top 10 --out report.md
```
  `listings.json` 为房源对象数组，字段：`title,city,starting,appraisal,market,tax,occupancy,lease,land,loan,usage`（价格单位元/万自动识别；`appraisal` 缺失时以 `market` 兜底折价率）。脚本输出**按评分降序的排名表** + 逐项风险标记，仅把 ≥60 分纳入候选。

### 4. 风险尽调清单（模型判断，逐条核对，不得省略）
对进入候选的房源，逐条核验 `references/platforms-and-risks.md` 的《尽调清单》。**折价高但"不清场/划拨地/买家全付税费/长租约"的标的，评分会显著下调——务必人工复核公告原文的"已知瑕疵"。**

### 5. 决策与出价策略
- 捡漏成功的关键不是"拍到最便宜"，而是"拍到后无额外大额成本 + 能顺利收房"。
- 出价锚点：`心理最高价 = 评估价×(1−合理折价) − 预估额外成本(税费/出让金/装修/腾退)`。
- 警惕「悔拍」：保证金不退、且可能被责令补差价，参拍前必须算清上限。

### 6. 风险提示（每次都要讲）
法拍房不是无风险套利：占用腾退难、隐性税费、划拨地补出让金、长期租约、户籍户口、物业欠费等都可能导致"表面捡漏、实际踩坑"。本技能只做信息梳理与初步筛查，**不构成投资建议，最终以法院公告与专业尽调为准**。

## 与相邻技能的分工

| 技能 | 职责 |
|---|---|
| `fapai-bargain-radar`（本技能） | 法拍房捡漏检索、批量评分与排名、尽调框架 |
| `agent-browser` | 真实去淘宝/法院网/京东抓取（按需加载，本技能无浏览器时必需） |
| `portfolio-diagnosis` | 已购房产组合诊断再平衡（非本技能范围） |
