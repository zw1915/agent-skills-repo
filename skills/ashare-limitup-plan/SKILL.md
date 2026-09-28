---
name: ashare-limitup-plan
display_name: A股打板选股与回测
display_name_en: A-Share Limit-Up Board Screener & Backtester
description: "面向 A 股首板打板的盘后量化选股与回测技能：收盘后增量更新全 A 股日线（约 5~8 分钟），重建涨停与首板事件，按封板形态、量能倍数、成交额、股价、前期涨幅、60 日位置等因子打分，再结合市场情绪闸门给出次日 Top10 交易计划（含买入区间、止损位、仓位与失效条件），并支持一键回测复盘以验证因子是否真的有效。当用户提到「打板」「首板」「涨停板选股」「连板」「情绪周期」「次日交易计划」「盘后选股」「涨停复盘」「回测打板策略」「给我今天的打板名单」等需求时使用本技能。技能自带可从零复现的数据层（同花顺为主源，新浪/东财为备源，零第三方依赖）以及 12 年全 A 股因子回测结论。不适用于日内高频、T+0、需要分时或盘口数据（封单量、封板时间）的场景；输出为量化研究结果，不构成投资建议。"
description_zh: "面向 A 股首板打板的盘后量化选股与回测技能：收盘后增量更新全 A 股日线（约 5~8 分钟），重建涨停与首板事件，按封板形态、量能倍数、成交额、股价、前期涨幅、60 日位置等因子打分，再结合市场情绪闸门给出次日 Top10 交易计划（含买入区间、止损位、仓位与失效条件），并支持一键回测复盘以验证因子是否真的有效。当用户提到「打板」「首板」「涨停板选股」「连板」「情绪周期」「次日交易计划」「盘后选股」「涨停复盘」「回测打板策略」「给我今天的打板名单」等需求时使用本技能。技能自带可从零复现的数据层（同花顺为主源，新浪/东财为备源，零第三方依赖）以及 12 年全 A 股因子回测结论。不适用于日内高频、T+0、需要分时或盘口数据（封单量、封板时间）的场景；输出为量化研究结果，不构成投资建议。"
description_en: "Post-close quant screener and backtester for A-share first-board (limit-up) trading. Incrementally updates full-market daily bars after the close (~5-8 min for ~5,500 stocks), reconstructs limit-up and first-board events, scores candidates on seal quality, volume ratio, turnover value, price, prior 20-day gain and 60-day position, then applies a sentiment gate to output a next-day Top-10 plan with entry band, stop, position size and invalidation rules. Also runs one-click backtests and factor analysis over 12 years of data. Use for limit-up board trading, first boards, consecutive boards, sentiment cycles, next-day trade plans, post-close selection, board-chasing review, or backtesting such strategies. Ships a zero-dependency data layer (Tonghuashun primary; Sina/Eastmoney fallback). Not for intraday/T+0 or strategies needing tick/order-book fields like seal order size or seal time. Research output only, not investment advice."
category: finance
version: 1.0.0
agent_created: true
author: 梁樱萍
---

# A股打板选股与回测

## 解决什么问题

打板策略的日常工作有两半：**盘后选股**（从当天几十到几百个涨停里挑出次日概率最高的几个）
和**事后复盘**（判断某类票到底赚不赚钱）。这两半必须用同一套口径，
否则回测好看、实盘走样。本技能把两半做成同一条代码路径。

## 三条核心命令

所有脚本都在 `scripts/` 下，**用绝对路径调用**。
重建信号那条会 import 本地模块，务必带 `PYTHONDONTWRITEBYTECODE=1`，
否则会在 `scripts/` 里生成 `__pycache__`，把技能包搞成三级目录、导入被拒。

```bash
S=~/.workbuddy/skills/ashare-limitup-plan
export PYTHONDONTWRITEBYTECODE=1        # 防止生成 __pycache__

# ① 收盘后增量更新（每只股票 1 个请求，约 5~8 分钟）
python "$S/scripts/update_data.py" --incremental

# ② 重建信号 + 生成次日 Top10 交易计划
python -c "import sys;sys.path.insert(0,'$S/scripts');import ashare_lib as A,strategy as S;S.rebuild_signals(A.connect())"
python "$S/scripts/screen_today.py" --top 10 --out plan.md

# ③ 一键回测复盘（因子是否真的有效）
python "$S/scripts/backtest.py" --top 10 --exit t1_oc --oos 2020-06-01
```

首次使用要先把历史补上（全市场约 8 万请求，耗时 **~90 分钟**，之后都走增量）：

```bash
python "$S/scripts/update_data.py" --years 2014-2026 --workers 20
```

> **为什么这么慢、且加线程没用**：同花顺是**服务端限速**（实测 32 线程 11.5 req/s、
> 64 线程 12.9 req/s，线程越多失败越多），吞吐封顶约 12~13 req/s。
> 所以耗时由**请求数**决定：全市场 5561 只 × (1 个 last.js + 约 11 个年份文件)
> ≈ 8 万请求 ÷ 13 ≈ 100 分钟。想更快只能换数据源（新浪单股 1 请求拿 3000 根，
> 但缺成交额/换手率且并发超 8 就被封）。这是一次性成本，日常增量只需 5~8 分钟。

`rebuild_signals` 需要重跑的情况：新增了数据、改了因子口径。
日常流程是「增量更新 → 重建信号 → 出计划」，重建只需几秒到一两分钟。

## 数据放在技能包之外

```
~/.workbuddy/data/ashare-limitup/market.db     ← SQLite（可用 ASHARE_DATA_HOME 覆盖）
```

**刻意不放在技能目录里**：技能包只允许两级目录，运行时生成的子目录会把包搞成不合规；
而且数据可复用，重装技能不必重下。表结构：

| 表 | 内容 |
|---|---|
| `daily` | 全 A 股未复权日线（OHLC / 成交量 / 成交额 / 换手率） |
| `stock_meta` | 代码、名称、板块、ST 标记、市值快照 |
| `lu_event` | 涨停事件 + 因子 + 前瞻收益（选股与回测共用） |
| `market_daily` | 全市场情绪日表（涨停家数、连板高度、赚钱效应） |
| `plan` / `backtest_run` | 交易计划与回测留痕 |

## 五个必须知道的口径与局限

**1. 涨停判定用未复权价。** 涨跌停价是按未复权价四舍五入到分算出来的，
复权价会破坏这个等式。因此 `daily` 存的全是未复权数据，
四舍五入用整数分价运算实现 half-up（`round()` 是银行家舍入，会算错涨停价）。
数据层把同花顺接口的复权标志位**硬编码为 `00`（不复权）**：`01`（前复权）
不只是价格口径错，其历史还被上游截断（老股只覆盖近几年），
详见 `references/data-sources.md`。

**2. 封板强度是近似量。** 日线里没有封板时间和封单量（那些要分时/盘口数据）。
本技能用「开盘是否即涨停」与「日内最大回撤深度」近似，
**不要把它当成真实的封单强度**。想要精确封单数据，得接入 L2 行情。

**3. 首板是「20 个交易日内无涨停」。** 这个窗口是参数（`strategy.LOOKBACK_FIRST`），
放宽到 60 日会显著减少候选。

**4. 历史 ST 状态是推断的。** 用滚动窗口内最大单日涨跌幅反推当时是否处于 5% 制度，
只依赖当日之前的数据。比「拿当前名称里的 ST 回溯历史」更准，但不完全等价于官方标记。

**5. 市值是抓取当日快照，不是历史值。** 因此市值不参与打分，
只用成交额（当日可算）替代规模维度。

## 因子体系与情绪闸门

打分是 7 个因子的加权复合，权重是**先验设定**，不是样本内拟合出来的
（拟合出来的权重回测不可信）。市场情绪不参与选股——
它对当日所有股票相同，只决定**总仓位**，这是这类策略最有效的一道风控。

完整的因子定义、方向、分层回测结论与 IC，见 `references/factor-playbook.md`。
执行层面的细节（竞价规则、一字板买不到、跌停卖不出、情绪周期怎么用），
见 `references/trading-playbook.md`。数据源、限流与降级策略见 `references/data-sources.md`。

## 输出

- 交易计划书：`assets/template-plan.md` 定义结构，由 `screen_today.py` 填充
- 复盘报告：`assets/template-review.md` 定义结构，由 `backtest.py` 输出

## 硬约束

- **不做投资建议**。输出是量化规则的结果，实盘前必须自己在样本外验证。
- **不隐瞒局限**。封板强度、ST 状态、市值三项的近似性必须在输出里标明。
- **不虚构回测结论**。回测数字只能来自 `backtest.py` 的实际运行，
  引用时须同时给出区间、样本量、成本假设与卖出口径。

> **打包约束**：技能包只支持两级目录（根目录 / 二级目录 / 文件）。
> 新增文件只能落在 `references/`、`assets/`、`scripts/` 之下或根目录；
> 运行时数据一律写到 `~/.workbuddy/data/` 之外，不要建三级目录。
