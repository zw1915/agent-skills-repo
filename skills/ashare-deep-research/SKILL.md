---
name: ashare-deep-research
display_name: A股个股深度投研流水线
display_name_en: A-Share Deep Research Pipeline
description: "把个股研究固化为六段式流水线：基本面 → 技术面 → 新闻/事件面 → 情绪筹码面 → 多空辩论 → 风控交易计划，产出带 SVG 图表、可直接交付的 HTML 深度研报。当用户说「深度研究」「做个深度分析」「写一份个股研报」「这只票值不值得买」「能不能拿」「怎么看XX」「帮我拆一下基本面和筹码」「多空对辩一下」「给个买入区间和止损」「这只票有什么雷」时使用。也适用于批量产出付费研报栏目、把个人投研工作流产品化。触发词：深度研报、投研流水线、个股深度分析、基本面技术面情绪面、多空辩论、买入区间、止损位、仓位管理、主力资金、大宗交易折价、筹码派发。不适用：只查一个实时报价、只看大盘情绪周期、ETF轮动配置、纯短线打板选股。"
description_zh: "把个股研究固化为六段式流水线：基本面 → 技术面 → 新闻/事件面 → 情绪筹码面 → 多空辩论 → 风控交易计划，产出带 SVG 图表、可直接交付的 HTML 深度研报。当用户说「深度研究」「做个深度分析」「写一份个股研报」「这只票值不值得买」「能不能拿」「怎么看XX」「帮我拆一下基本面和筹码」「多空对辩一下」「给个买入区间和止损」「这只票有什么雷」时使用。也适用于批量产出付费研报栏目、把个人投研工作流产品化。触发词：深度研报、投研流水线、个股深度分析、基本面技术面情绪面、多空辩论、买入区间、止损位、仓位管理、主力资金、大宗交易折价、筹码派发。不适用：只查一个实时报价、只看大盘情绪周期、ETF轮动配置、纯短线打板选股。"
description_en: "Turns single-stock research into a six-stage pipeline: fundamentals, technicals, news/events, sentiment and chip structure, bull-bear debate, then risk control and trade plan, producing a deliverable HTML report with embedded SVG charts. Use when the user asks for a deep dive, says \"write me a research report\", \"is this stock worth buying\", \"should I hold\", \"give me entry and stop\", \"debate both sides\", \"any red flags\", or wants to productize a personal research workflow into a paid recurring column. Trigger phrases: deep research, stock report, fundamental analysis, technical levels, chip distribution, block-trade discount, position sizing, stop loss. Not for single price quotes, broad market sentiment cycles, ETF rotation, or intraday limit-up screening."
category: data-analysis
version: 1.0.0
agent_created: true
author: 梁樱萍
---

# A股个股深度投研流水线

## 它解决什么问题

散户做深度研究的失败模式高度一致：**数据查了几十项，落不到一个决策上**。
本技能把研究强制收口成六个阶段，每个阶段必须产出"能写进结论的一句话"，最后由多空辩论与风控表把数据压缩成可执行的仓位与止损。

**核心产出**：一份自包含 HTML 深度研报（内嵌 SVG K线/量能/MACD 图，零外部依赖，可直接打开或转 PDF）。

## 铁律：不许编数据

金融场景下虚假数字会造成严重误导。

- 行情/K线接口返回空数据 → **如实写"该条件下无数据"**，禁止用常识或同类公司补位；
- 找不到某个财务字段（如扣非净利、减值分摊季度）→ 在报告的**「信息缺口」小节显式列出**，不要静默略过；
- 所有推算值（如剔除一次性损益后的利润）必须标注口径与假设税率区间；
- 报告中所有数字都应可被上游接口回查核验。

## 标准工作流

### 步骤 0：锁定标的

用户给中文名或模糊代码 → 先 `tdx_lookup_stock(query=名称, range="AG")` 拿精确代码与 setcode，**再**调用行情工具。行情接口的 `code` 只接受纯数字。

### 步骤 1：一次性取全数据（避免多轮往返）

并行调用：

| 目的 | 工具与参数 |
|---|---|
| 实时快照 + 估值 + 资金 | `tdx_quotes(code, setcode, hasCwInfo="1", hasExtInfo="1", hasProInfo="1")` |
| 日K序列 | `tdx_kline(code, setcode, period="4", wantNum="180", tqFlag="1")` |
| 近期资讯 | `wenda_news_query(name=公司简称, bdate=近60天, edate=今日)` |
| 公告 | `wenda_notice_query(name=公司简称, bdate=近120天, edate=今日)` |
| 研报/评级 | `wenda_report_query(name=公司简称, bdate=近120天, edate=今日)` |

**时间参数必须显式传 YYYYMMDD**，禁止依赖后端解析"最近""本月"等相对词。

setcode 速查：`1`=沪市(6/68开头) · `0`=深市(00/30) · `2`=北交所 · `31`=港股。

### 步骤 2：组装输入文件

按 `assets/input-schema.json` 的结构落一个 `<code>_input.json`：

- `bars`：`[日期, 开, 高, 低, 收, 成交量(手)]` 数组，建议 ≥120 根（MA60/ATR 需要足够样本）
- `fundamentals`：最新报告期财务口径（注明报告期名称）
- `snapshot`：估值、市值、资金流向、阶段涨幅
- `events`：从资讯/公告提取的事件清单 `{date, type, text}`

### 步骤 3：写六段式正文

严格按 `references/research-playbook.md` 的六段结构写 `<code>_body.md`。
**每一段必须回答该阶段规定的那个问题**，写不出来就写"本阶段无有效信息"，不要用水话填充。

### 步骤 4：写元信息

`<code>_meta.json`：`badge` / `market` / `chart_bars`（图表显示K线数，默认 90）/ `verdicts`（4 个结论卡）/ `score` / `disclaimer`。

### 步骤 5：渲染

```bash
python scripts/build_research_report.py \
  --input data/<code>_input.json \
  --body  data/<code>_body.md \
  --meta  data/<code>_meta.json \
  --out   reports/<名称><code>_深度投研报告_<日期>.html
```

脚本会在 stdout 打印全部指标读数：**先用它核对数字，再据此定稿正文里的价位表与仓位建议。**
实践做法是：先跑一遍占位正文拿到读数 → 写正文 → 再跑一遍生成最终稿。

### 步骤 6：交付

调用 `present_files` 打开 HTML。若用户要文档，可再经 HTML→DOCX 通道转换。

## 输出必须包含的硬构件

缺任一项都不算合格：

1. **结论先行卡**：一句话定性 + 三条互相关联的核心事实
2. **信息缺口清单**：明确写出哪些数据没拿到
3. **斐波那契/均线关键价位表**：给出阻力、支撑的具体数字
4. **多空各三条最强论据**：必须是对等强度，不能把空头写成稻草人
5. **分场景交易计划**：突破/回踩/破位/持有四种情形各自动作
6. **基于 ATR 的仓位与止损**：给出具体金额与占比示例
7. **失效信号**：列出推翻本结论的可观测触发条件
8. **后续跟踪清单**：含下一次财报窗口

## 常见坑

| 现象 | 原因与处理 |
|---|---|
| 行情返回空 | code/setcode 不匹配；务必先 lookup 确认市场代码 |
| MA60/ATR 为 `—` | K线样本不足 60/14 根，加大 `wantNum` |
| 均线在图上看不见 | 该均线在窗口内无值（样本不足），非渲染错误 |
| 首次渲染数字与正文不符 | 正常：先跑占位拿读数，再回填正文，见步骤 5 |
| 打包时报错"目录层级超限" | 所有文件只能落在根目录或 `references/`、`scripts/`、`assets/` 下；删除 `scripts/__pycache__` |
| frontmatter 报错缺字段 | 需齐备 name / display_name / display_name_en / description / description_zh / description_en / category / version，且各 description ≤1000 字符 |

## 产品化建议

本技能的产出物天然可批量复制：

- **固定栏目**：每周对同一批自选股跑一遍，形成日/周更研报；
- **信号订阅**：只输出 verdicts 卡 + 买入区间 + 止损位，做成短版推送；
- **定制交付**：替换 meta 的 badge/disclaimer 与维权重，即为不同客户产出不同侧重版本（如"只看筹码"或"只看基本面"）。

更改默认权重与评分规则，见 `references/research-playbook.md` 末尾的评分表。
