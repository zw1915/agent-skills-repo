#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘后选股：生成次日的 Top10 打板交易计划。

用法
----
    # 用库内最新交易日（收盘后跑）
    python screen_today.py

    # 指定日期 / 数量 / 输出文件
    python screen_today.py --date 2026-09-11 --top 10 --out plan.md

    # 只看不落库；输出 JSON 供程序消费
    python screen_today.py --no-save --format json

工作流
------
1. 取目标交易日的涨停事件（lu_event）与市场情绪（market_daily）
2. 硬性过滤：非首板、一字板、次新、成交额不足、前 20 日涨幅过大
3. 复合打分取 Top N
4. 结合市场情绪给总仓位，逐票生成「有条件的」次日交易计划

为什么计划必须写条件
--------------------
打板的盈亏不取决于「选没选中」，而取决于**次日什么价格买**。
高开 8% 追进去和低开 2% 接回来，同一只股票是两个完全不同的交易。
所以计划里把「放弃条件」写得比「买入条件」更明确。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ashare_lib as A          # noqa: E402
import strategy as S            # noqa: E402

LU_COLS = ["code", "date", "preclose", "open", "high", "low", "close", "lu_price",
           "shape", "body_depth", "gap_open", "seal_minute", "vol_ratio", "amount_yi",
           "turnover", "price", "prev_ret20", "pos60", "prior_lu20", "streak",
           "is_first", "bars_listed", "t1_gap", "t1_oc", "t1_tradable", "t1_ld",
           "t2_oo", "t2_oc", "exdiv_risk"]


def load_events(conn, date: str) -> list:
    rows = conn.execute(
        f"SELECT {','.join(LU_COLS)} FROM lu_event WHERE date=?", (date,)).fetchall()
    return [dict(zip(LU_COLS, r)) for r in rows]


def load_market(conn, date: str) -> dict:
    r = conn.execute("SELECT * FROM market_daily WHERE date=?", (date,)).fetchone()
    if not r:
        return {}
    keys = [d[0] for d in conn.execute("SELECT * FROM market_daily LIMIT 0").description]
    return dict(zip(keys, r))


def reasons(e: dict) -> str:
    """从因子值生成 2~3 条口语化理由，避免只给一个分数。"""
    out = []
    sh = e.get("shape")
    if sh == "一字板":
        out.append("一字板（次日大概率买不到，已排除）")
    elif sh == "T字板":
        out.append("T字板：开盘即涨停")
    elif sh == "浅回撤":
        out.append("日内回撤浅，封板扎实")
    else:
        out.append("日内回撤较深，封板一般")
    vr = e.get("vol_ratio")
    if vr:
        out.append(f"量能 {vr:.1f} 倍" + ("（放量充分）" if 1.5 <= vr <= 4 else
                                        "（量能偏小）" if vr < 1.5 else "（放量过大）"))
    if e.get("pos60") and e["pos60"] >= 0.995:
        out.append("收盘创 60 日新高")
    pr = e.get("prev_ret20")
    if pr is not None:
        out.append(f"前 20 日 {pr:+.1%}" + ("（未拉升）" if pr < 0.10 else ""))
    amt = e.get("amount_yi")
    if amt:
        out.append(f"成交 {amt:.1f} 亿")
    return "；".join(out[:4])


def render_md(date: str, regime: dict, picks: list, universe: dict, market: dict,
              dropped: list) -> str:
    L = []
    L.append(f"# 打板交易计划 · {date}")
    L.append("")
    L.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　"
             f"数据源：同花顺日线（不复权）　口径：首板次日"
             f"（T 日收盘后出计划，T+1 开盘执行）")
    L.append("")
    L.append("## 一、市场情绪与建议仓位")
    L.append("")
    L.append(f"**{regime['level']} — 建议总仓位 {regime['position']:.0%}**")
    L.append("")
    L.append(f"{regime['note']}")
    L.append("")
    L.append("| 指标 | 数值 |")
    L.append("|---|---|")
    L.append(f"| 涨停家数 | {market.get('lu_count') or 0} |")
    L.append(f"| 跌停家数 | {market.get('ld_count') or 0} |")
    L.append(f"| 首板家数 | {market.get('first_count') or 0} |")
    L.append(f"| 最高连板 | {market.get('max_streak') or 0} 板 |")
    L.append(f"| 昨日涨停今日均涨 | "
             f"{(market.get('yest_lu_premium') or 0):+.2%} |")
    L.append(f"| 昨日涨停今日收红率 | "
             f"{(market.get('yest_lu_winrate') or 0):.0%} |")
    L.append("")
    L.append(f"当日首板候选 {len(universe)} 只，过滤后 {len(dropped) + len(picks)} 只进入打分，"
             f"取前 {len(picks)} 只。")
    L.append("")
    if not picks:
        L.append("**今日无符合条件的标的。**空仓也是一种决策 —— 情绪与结构不支持时，"
                 "不交易就是最好的交易。")
        return "\n".join(L)

    L.append("## 二、Top {} 候选一览".format(len(picks)))
    L.append("")
    L.append("| # | 代码 | 名称 | 得分 | 形态 | 量能 | 成交额(亿) | 换手% | 前20日 | 价格 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, e in enumerate(picks, 1):
        L.append(f"| {i} | {e['code']} | {e.get('name') or ''} | {e['score']:.1f} | "
                 f"{e.get('shape')} | {(e.get('vol_ratio') or 0):.1f}x | "
                 f"{(e.get('amount_yi') or 0):.2f} | "
                 f"{(e.get('turnover') or 0):.2f} | "
                 f"{(e.get('prev_ret20') or 0):+.1%} | {e.get('price'):.2f} |")
    L.append("")
    L.append("## 三、逐票交易计划")
    L.append("")
    for i, e in enumerate(picks, 1):
        pl = e["plan"]
        L.append(f"### {i}. {e['code']} {e.get('name') or ''}　"
                 f"（得分 {e['score']:.1f}）")
        L.append("")
        L.append(f"- **入选理由**：{reasons(e)}")
        L.append(f"- **买入条件**：{pl['buy_cond']}")
        L.append(f"- **加仓条件**：{pl['add_cond']}")
        L.append(f"- **止损**：{pl['stop']}")
        L.append(f"- **目标/持有**：{pl['target']}")
        L.append(f"- **仓位**：{pl['position']}")
        L.append(f"- **失效条件**：{pl['invalidate']}")
        L.append("")
    L.append("## 四、被过滤的候选（供复盘）")
    L.append("")
    if dropped:
        L.append("| 代码 | 名称 | 剔除原因 |")
        L.append("|---|---|---|")
        for e in dropped[:20]:
            L.append(f"| {e['code']} | {e.get('name') or ''} | {e.get('_why')} |")
    else:
        L.append("无")
    L.append("")
    L.append("## 五、口径与风险提示")
    L.append("")
    L.append("- **封板强度是近似量**：日线数据没有封板时间与封单量，"
             "本表用「日内回撤深度 + 是否开盘即涨停」近似，不等同于真实封单强度。")
    L.append("- **成交额与换手率**来自同花顺；若切到新浪数据源，成交额由 OHLC 均价推算、"
             "换手率缺失，此时相关因子按中性分处理。")
    L.append("- **打板是高风险交易**：首板次日存在一字跌停（无法卖出）的尾部风险，"
             "单票仓位与总仓位管理比选股更重要。")
    L.append("- 本计划由量化规则生成，不构成投资建议。实盘前请用回测模块在样本外验证。")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="盘后生成 Top10 打板交易计划")
    ap.add_argument("--date", default=None, help="目标交易日，默认库内最新日")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", default=None, help="输出 Markdown 文件路径")
    ap.add_argument("--format", default="md", choices=["md", "json"])
    ap.add_argument("--no-save", action="store_true", help="不写入 plan 表")
    args = ap.parse_args()

    conn = A.connect()
    A.init_schema(conn)

    date = args.date
    if not date:
        r = conn.execute("SELECT MAX(date) FROM lu_event").fetchone()
        date = r[0] if r and r[0] else None
    if not date:
        print("错误：lu_event 表为空。请先运行 update_data.py 抓数据，"
              "再运行 strategy.rebuild_signals() 重建信号。", file=sys.stderr)
        return 2

    events = load_events(conn, date)
    market = load_market(conn, date)
    names = A.name_map(conn)

    passed, dropped = [], []
    for e in events:
        ok, why = S.hard_filters(e)
        e["name"] = names.get(e["code"], "")
        if ok:
            passed.append(e)
        else:
            e["_why"] = why
            dropped.append(e)

    scored = S.score_events(passed, market)
    n_codes = conn.execute("SELECT COUNT(DISTINCT code) FROM daily").fetchone()[0] or None
    regime = S.market_regime(market, n_codes)
    picks = scored[:args.top]
    for e in picks:
        e["plan"] = S.build_plan(e, regime)

    if args.format == "json":
        txt = json.dumps({
            "date": date, "regime": regime, "market": market,
            "candidates": len(events), "passed": len(passed),
            "picks": [{k: v for k, v in e.items() if k != "parts"} for e in picks],
            "dropped": [{"code": d["code"], "reason": d["_why"]} for d in dropped],
        }, ensure_ascii=False, indent=2)
    else:
        txt = render_md(date, regime, picks, passed, market, dropped)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"已写入 {args.out}")
    elif args.format == "md":
        print(txt)

    if not args.no_save and picks:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.executemany(
            "INSERT OR REPLACE INTO plan(plan_date,rank,code,name,score,detail,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            [(date, i, e["code"], e.get("name"), e["score"],
              json.dumps({k: v for k, v in e.items() if k != "parts"},
                         ensure_ascii=False), now)
             for i, e in enumerate(picks, 1)])
        # 同日重跑时清掉多余的旧名次
        conn.execute("DELETE FROM plan WHERE plan_date=? AND rank>?", (date, len(picks)))
        conn.commit()
        if args.format == "json":
            print(f"已保存 {len(picks)} 条计划到 plan 表（plan_date={date}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
