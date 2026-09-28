#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首板打板策略一键回测（复用 screen_today 的同一套选股与打分口径）。

用法
----
    python backtest.py                          # 全样本回测（默认 T+1 收盘卖出）
    python backtest.py --top 10 --exit t1_oc
    python backtest.py --exit t2_oo --cost 0.0015
    python backtest.py --no-regime              # 关闭情绪闸门，对比用
    python backtest.py --oos 2020-06-01         # 样本内/外切分（按日期）

可实现性约束（回测最容易自欺的地方）
------------------------------------
1. **次日一字涨停开盘买不到**：这类样本直接剔除（``t1_tradable=0``）。
   不做这个剔除，回测收益会虚高一大截 —— 因为涨停开盘的票次日往往继续涨。
2. **次日跌停卖不掉**：若 ``t1_ld=1``，收盘卖出不成立，只能顺延到 T+2。
3. **除权日剔除**：跨日收益在除权日会被价格跳空污染，标记 ``exdiv_risk``
   的样本从跨日口径中剔除（日内口径不受影响）。
4. **交易成本**：默认双边 0.15%（含佣金、印花税与打板滑点）。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ashare_lib as A          # noqa: E402
import strategy as S            # noqa: E402

from screen_today import LU_COLS, load_events, load_market  # noqa: E402

EXIT_MODES = {"t1_oc": "T+1 收盘", "t2_oo": "T+2 开盘", "t2_oc": "T+2 收盘"}


# ---------------------------------------------------------------- 组合模拟

def run_backtest(conn, start=None, end=None, top=10, exit_mode="t1_oc",
                 cost=0.0015, use_regime=True, min_pick=1) -> dict:
    days = [d for d in A.trading_days(conn)
            if (not start or d >= start) and (not end or d <= end)]
    if not days:
        return {"error": "区间内无足够交易日（daily 表可能尚未填充）"}

    eq = 1.0
    curve = []           # (date, daily_ret, equity, n_trades, position)
    trades = []          # 每笔：dict
    skipped = {"untradable": 0, "regime_off": 0, "ld_hold": 0, "no_data": 0}
    per_day_candidates = []
    # 股票池规模：用于按规模缩放情绪闸门阈值（见 strategy.market_regime）
    n_codes = conn.execute("SELECT COUNT(DISTINCT code) FROM daily").fetchone()[0] or 0

    for d in days:
        events = load_events(conn, d)
        market = load_market(conn, d)
        regime = (S.market_regime(market, n_codes) if use_regime
                  else {"level": "off", "position": 1.0})
        passed = []
        for e in events:
            ok, _ = S.hard_filters(e)
            if ok:
                passed.append(e)
        _ = passed
        scored = S.score_events(passed, market)
        picks = scored[:top]
        per_day_candidates.append((d, scored))

        if not picks or regime["position"] <= 0:
            if picks:
                skipped["regime_off"] += 1
            curve.append((d, 0.0, eq, 0, regime["position"]))
            continue

        rets = []
        for e in picks:
            if e.get("t1_oc") is None:
                skipped["no_data"] += 1
                continue
            if e.get("t1_tradable") != 1:
                skipped["untradable"] += 1
                continue
            if exit_mode.startswith("t2") and e.get("exdiv_risk"):
                skipped["no_data"] += 1
                continue
            r = e.get(exit_mode)
            if r is None:
                skipped["no_data"] += 1
                continue
            # 次日跌停卖不掉 -> 顺延到 T+2 收盘
            if exit_mode == "t1_oc" and e.get("t1_ld") == 1:
                skipped["ld_hold"] += 1
                r = e.get("t2_oc")
                if r is None:
                    continue
            gross = r
            net = gross - cost
            rets.append(net)
            trades.append({
                "date": d, "code": e["code"], "score": e["score"],
                "shape": e.get("shape"), "vol_ratio": e.get("vol_ratio"),
                "amount_yi": e.get("amount_yi"), "price": e.get("price"),
                "prev_ret20": e.get("prev_ret20"), "pos60": e.get("pos60"),
                "body_depth": e.get("body_depth"), "turnover": e.get("turnover"),
                "lu_count": market.get("lu_count"),
                "yest_lu_premium": market.get("yest_lu_premium"),
                "regime": regime["level"], "gross": gross, "net": net,
            })

        if not rets:
            curve.append((d, 0.0, eq, 0, regime["position"]))
            continue
        # 组合日收益 = 情绪仓位 × 等权持仓收益
        w = min(1.0, len(rets) / float(top))
        day_ret = regime["position"] * w * (sum(rets) / len(rets))
        eq *= (1.0 + day_ret)
        curve.append((d, day_ret, eq, len(rets), regime["position"]))

    return {"curve": curve, "trades": trades, "skipped": skipped,
            "days": days, "per_day_candidates": per_day_candidates,
            "exit_mode": exit_mode, "cost": cost, "top": top, "use_regime": use_regime}


# ---------------------------------------------------------------- 指标

def metrics(res: dict) -> dict:
    curve = res["curve"]
    trades = res["trades"]
    if not curve:
        return {}
    rets = [c[1] for c in curve]
    eq = [c[2] for c in curve]
    n = len(rets)
    total = eq[-1] - 1.0
    years = n / 244.0
    ann = (eq[-1] ** (1 / years) - 1) if years > 0 and eq[-1] > 0 else 0.0
    peak, mdd = -1e9, 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    vol = st.pstdev(rets) * math.sqrt(244) if n > 1 else 0.0
    sharpe = (ann / vol) if vol else 0.0
    wins = [t["net"] for t in trades if t["net"] > 0]
    loss = [t["net"] for t in trades if t["net"] <= 0]
    avg_w = st.mean(wins) if wins else 0.0
    avg_l = st.mean(loss) if loss else 0.0
    return {
        "交易日数": n, "交易笔数": len(trades),
        "累计收益": total, "年化收益": ann, "年化波动": vol, "夏普": sharpe,
        "最大回撤": mdd,
        "日胜率": sum(1 for r in rets if r > 0) / n if n else 0.0,
        "交易胜率": len(wins) / len(trades) if trades else 0.0,
        "平均盈利": avg_w, "平均亏损": avg_l,
        "盈亏比": (avg_w / abs(avg_l)) if avg_l < 0 else float("inf"),
        "单笔均值": st.mean([t["net"] for t in trades]) if trades else 0.0,
        "单笔中位数": st.median([t["net"] for t in trades]) if trades else 0.0,
        "单笔最好": max((t["net"] for t in trades), default=0.0),
        "单笔最差": min((t["net"] for t in trades), default=0.0),
    }


def by_year(trades: list, curve: list) -> list:
    acc = {}
    for d, r, e, nt, pos in curve:
        y = d[:4]
        a = acc.setdefault(y, {"ret": 1.0, "n": 0, "trades": 0})
        a["ret"] *= (1.0 + r)
        a["n"] += 1
    for t in trades:
        y = t["date"][:4]
        acc.setdefault(y, {"ret": 1.0, "n": 0, "trades": 0})["trades"] += 1
    out = []
    for y in sorted(acc):
        a = acc[y]
        out.append({"年": y, "收益": a["ret"] - 1.0, "交易日": a["n"], "交易笔数": a["trades"]})
    return out


def _rank(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    for pos, i in enumerate(order):
        r[i] = pos + 1.0
    return r


def _spearman(x, y):
    if len(x) < 5:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else None


FACTORS = [
    ("body_depth", "日内回撤深度（越小越强）", -1),
    ("vol_ratio", "量能倍数", 1),
    ("amount_yi", "成交额（亿）", 1),
    ("price", "股价", 1),
    ("prev_ret20", "前 20 日涨幅", 1),
    ("pos60", "60 日位置", 1),
    ("turnover", "换手率", 1),
]


def factor_analysis(res: dict, exit_mode="t1_oc", deciles=5) -> list:
    """单因子分层 + IC。只用**可交易**样本，避免一字板造成的乐观偏差。"""
    rows = []
    for t in res["trades"]:
        rows.append(t)
    out = []
    for key, label, direction in FACTORS:
        vals = [(t[key], t["gross"]) for t in rows if t.get(key) is not None]
        if len(vals) < 100:
            out.append({"因子": label, "样本": len(vals), "说明": "样本不足"})
            continue
        vals.sort(key=lambda x: x[0])
        k = len(vals) // deciles
        groups = []
        for g in range(deciles):
            seg = vals[g * k:(g + 1) * k] if g < deciles - 1 else vals[g * k:]
            if seg:
                groups.append((sum(v[1] for v in seg) / len(seg), len(seg)))
        # 日度 IC
        ics = []
        daymap = {}
        for t in rows:
            if t.get(key) is not None:
                daymap.setdefault(t["date"], []).append((t[key], t["gross"]))
        for d, arr in daymap.items():
            if len(arr) >= 5:
                ic = _spearman([a[0] for a in arr], [a[1] for a in arr])
                if ic is not None:
                    ics.append(ic)
        ic_mean = st.mean(ics) if ics else 0.0
        ic_std = st.pstdev(ics) if len(ics) > 1 else 0.0
        out.append({
            "因子": label, "键": key, "样本": len(vals),
            "最低组": groups[0][0], "最高组": groups[-1][0],
            "组间差(高-低)": groups[-1][0] - groups[0][0],
            "单调性": _monotonic([g[0] for g in groups]),
            "IC均值": ic_mean, "ICIR": (ic_mean / ic_std) if ic_std else 0.0,
            "IC样本日": len(ics),
            "各层收益": [g[0] for g in groups],
            "方向": direction,
        })
    return out


def _monotonic(arr) -> float:
    """单调性：相邻组同号变动的比例，1=完全单调。"""
    if len(arr) < 2:
        return 0.0
    s = sum(1 for i in range(1, len(arr)) if (arr[i] - arr[i - 1]) * (arr[-1] - arr[0]) > 0)
    return s / (len(arr) - 1)


# ---------------------------------------------------------------- 输出

def fmt_pct(x, nd=2):
    return f"{x*100:.{nd}f}%"


def render_md(res: dict, m: dict, yrs: list, fa: list, title: str) -> str:
    L = []
    L.append(f"# {title}")
    L.append("")
    L.append(f"> 卖出口径：**{EXIT_MODES.get(res['exit_mode'], res['exit_mode'])}**　"
             f"双边成本 {res['cost']*100:.2f}%　每期取前 {res['top']} 只　"
             f"情绪闸门 {'开启' if res['use_regime'] else '关闭'}")
    L.append("")
    L.append("## 一、整体表现")
    L.append("")
    L.append("| 指标 | 数值 | 指标 | 数值 |")
    L.append("|---|---|---|---|")
    L.append(f"| 交易笔数 | {m.get('交易笔数')} | 单笔均值 | {fmt_pct(m.get('单笔均值',0))} |")
    L.append(f"| 累计收益 | {fmt_pct(m.get('累计收益',0))} | 单笔中位数 | {fmt_pct(m.get('单笔中位数',0))} |")
    L.append(f"| 年化收益 | {fmt_pct(m.get('年化收益',0))} | 单笔最好 | {fmt_pct(m.get('单笔最好',0))} |")
    L.append(f"| 年化波动 | {fmt_pct(m.get('年化波动',0))} | 单笔最差 | {fmt_pct(m.get('单笔最差',0))} |")
    L.append(f"| 夏普 | {m.get('夏普',0):.2f} | 盈亏比 | {m.get('盈亏比',0):.2f} |")
    L.append(f"| 最大回撤 | {fmt_pct(m.get('最大回撤',0))} | 交易胜率 | {fmt_pct(m.get('交易胜率',0))} |")
    L.append("")
    sk = res["skipped"]
    L.append(f"可实现性处理：剔除次日一字开盘（买不到）{sk['untradable']} 笔；"
             f"次日跌停顺延卖出 {sk['ld_hold']} 笔；情绪闸门空仓 {sk['regime_off']} 天；"
             f"数据缺失 {sk['no_data']} 笔。")
    L.append("")
    L.append("## 二、分年表现")
    L.append("")
    L.append("| 年 | 策略收益 | 交易日 | 交易笔数 |")
    L.append("|---|---|---|---|")
    for y in yrs:
        L.append(f"| {y['年']} | {fmt_pct(y['收益'])} | {y['交易日']} | {y['交易笔数']} |")
    L.append("")
    L.append("## 三、单因子分层与 IC")
    L.append("")
    L.append("分层为**按因子值排序后等分**，第一层为因子值最低组。"
             "收益均为「次日开盘买入、T+1 收盘卖出」的可交易样本均值（未扣成本）。")
    L.append("")
    L.append("| 因子 | 样本 | 最低组 | 最高组 | 高-低 | 单调性 | IC均值 | ICIR |")
    L.append("|---|---|---|---|---|---|---|---|")
    for f in fa:
        if "说明" in f:
            L.append(f"| {f['因子']} | {f['样本']} | — | — | — | — | — | {f['说明']} |")
            continue
        L.append(f"| {f['因子']} | {f['样本']} | {fmt_pct(f['最低组'])} | "
                 f"{fmt_pct(f['最高组'])} | {fmt_pct(f['组间差(高-低)'])} | "
                 f"{f['单调性']:.2f} | {f['IC均值']:.3f} | {f['ICIR']:.2f} |")
    L.append("")
    for f in fa:
        if "各层收益" in f:
            L.append(f"- **{f['因子']}** 各层收益（低→高）："
                     + " / ".join(fmt_pct(x) for x in f["各层收益"]))
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="首板打板策略回测")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--exit", default="t1_oc", choices=list(EXIT_MODES))
    ap.add_argument("--cost", type=float, default=0.0015)
    ap.add_argument("--no-regime", action="store_true", help="关闭情绪闸门")
    ap.add_argument("--oos", default=None, help="样本外起点日期（如 2020-06-01）")
    ap.add_argument("--out", default=None, help="Markdown 报告输出路径")
    ap.add_argument("--json", default=None, help="指标 JSON 输出路径")
    args = ap.parse_args()

    conn = A.connect()
    A.init_schema(conn)
    days = A.trading_days(conn)
    if not days:
        print("错误：无交易日数据，请先运行 update_data.py 并重建信号。", file=sys.stderr)
        return 2
    print(f"数据区间：{days[0]} ~ {days[-1]}（{len(days)} 个交易日）")

    t0 = datetime.now()
    res = run_backtest(conn, args.start, args.end, args.top, args.exit,
                       args.cost, not args.no_regime)
    if "error" in res:
        print("错误：" + res["error"], file=sys.stderr)
        return 2
    m = metrics(res)
    yrs = by_year(res["trades"], res["curve"])
    fa = factor_analysis(res, args.exit)
    title = f"首板打板策略回测 · {res['days'][0]} ~ {res['days'][-1]}"
    md = render_md(res, m, yrs, fa, title)
    print(md)

    # ---- 样本内外切分 ----
    if args.oos:
        print("\n\n" + "=" * 70)
        print(f"样本内 / 外切分（分界 {args.oos}）")
        print("=" * 70)
        segs = [("样本内", res["days"][0], args.oos),
                ("样本外", args.oos, res["days"][-1])]
        for label, s, e in segs:
            rr = run_backtest(conn, s, e, args.top, args.exit, args.cost,
                              not args.no_regime)
            mm = metrics(rr) if "error" not in rr else {}
            if not mm:
                print(f"  {label}: 无数据")
                continue
            print(f"  {label}（{s} ~ {e}）")
            print(f"    交易 {mm['交易笔数']:>5} 笔　累计 {fmt_pct(mm['累计收益']):>9}"
                  f"　年化 {fmt_pct(mm['年化收益']):>9}　最大回撤 {fmt_pct(mm['最大回撤']):>8}"
                  f"　交易胜率 {fmt_pct(mm['交易胜率']):>7}　单笔均值 {fmt_pct(mm['单笔均值'])}")

    # ---- 落库 ----
    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    conn.execute("INSERT OR REPLACE INTO backtest_run VALUES(?,?,?,?)",
                 (run_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  json.dumps({"start": args.start, "end": args.end, "top": args.top,
                              "exit": args.exit, "cost": args.cost,
                              "regime": not args.no_regime}, ensure_ascii=False),
                  json.dumps({"metrics": m, "by_year": yrs,
                              "factors": fa, "skipped": res["skipped"]},
                             ensure_ascii=False)))
    conn.commit()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\n已写入报告 {args.out}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"metrics": m, "by_year": yrs, "factors": fa,
                       "skipped": res["skipped"],
                       "params": {"start": args.start, "end": args.end,
                                  "top": args.top, "exit": args.exit,
                                  "cost": args.cost, "regime": not args.no_regime}},
                      f, ensure_ascii=False, indent=2)
        print(f"已写入指标 {args.json}")
    print(f"\nrun_id = {run_id}　耗时 {(datetime.now()-t0).total_seconds():.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
