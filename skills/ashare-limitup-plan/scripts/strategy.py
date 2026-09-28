#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打板策略层：涨停重建 → 首板因子 → 打分 → 市场情绪闸门 → 交易计划。

这个模块被 ``screen_today.py``（盘后选股）和 ``backtest.py``（回测）共用，
保证「选股口径」与「回测口径」完全一致 —— 很多策略回测好看、
实盘走样，根因就是这两处用了不同的代码路径。

设计原则
--------
1. **无未来函数**：选股只用 T 日及之前的数据。``lu_event`` 里的
   ``t1_*`` / ``t2_*`` 前瞻字段仅供回测评估，绝不参与打分。
   打分函数签名里也刻意不暴露这些字段。

2. **整数分价运算**：涨停判定在 1.4 万行量级的面板上要跑几十万次，
   用 Decimal 会慢一个数量级。这里把价格换算成「分」做整数运算，
   四舍五入用 ``(x*n+50)//100`` 实现 half-up，与交易所口径一致。

3. **封板强度只能近似**：日线拿不到封板时间与封单量（那些在分时/盘口
   数据里）。这里用「日内回撤深度」与「开盘是否即涨停」来近似，
   并在文档中明确标注这是近似量，不宣称等同于封单强度。
"""

from __future__ import annotations

import math
import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ashare_lib as A  # noqa: E402

# ---------------------------------------------------------------- 参数

LOOKBACK_FIRST = 20        # 首板判定回溯窗口（交易日）
MIN_BARS_LISTED = 60       # 上市不足此交易日数按次新股剔除
MIN_AMOUNT_YI = 0.5        # 最小成交额（亿元）
MAX_PREV_RET20 = 0.60      # 前 20 日累计涨幅上限（超过视为已拉升）
EVENT_BATCH = 20000        # 涨停事件分批落库的批大小（控制峰值内存）

# 打分权重 —— **先验设定，非样本内拟合**。
# 之所以强调这点：权重若在回测样本上优化出来，回测收益就不可信。
# 这里给的是基于打板逻辑的先验，回测的分档结论用于**验证方向**，
# 而不是反过来调参。若要调权重，请用 backtest.py 的样本外切分验证。
WEIGHTS = {
    "seal":   0.20,   # 封板形态（日内回撤越浅越强）
    "vol":    0.15,   # 量能适中
    "amount": 0.10,   # 成交额（流动性）
    "price":  0.10,   # 价格区间
    "prev":   0.15,   # 前 20 日涨幅（不追高）
    "pos":    0.15,   # 60 日位置（突破）
    "first":  0.15,   # 首板优先
}

# 区间型因子的理想带（低于/高于则线性衰减到 0）
BANDS = {
    "vol":    (1.5, 4.0, 2.5),      # 量能倍数 1.5~4 倍
    "amount": (1.0, 25.0, 8.0),     # 成交额 1~25 亿
    "price":  (3.0, 30.0, 4.0),     # 价格 3~30 元
    "prev":   (-0.10, 0.25, 0.35),  # 前 20 日涨幅 -10%~25%
}


# ---------------------------------------------------------------- 快速价格运算

def cent(x) -> int:
    """元 -> 分（整数）。"""
    return int(round(float(x) * 100))


def lu_by_ratio(pre_cents: int, ratio_pct: int) -> int:
    """涨停价（分）。half-up 四舍五入，与交易所口径一致。"""
    return (pre_cents * (100 + ratio_pct) + 50) // 100


def ld_by_ratio(pre_cents: int, ratio_pct: int) -> int:
    """跌停价（分）。"""
    return (pre_cents * (100 - ratio_pct) + 50) // 100


def ratio_pct_of(code: str, date: str, five_pct: bool = False) -> int:
    return int(round(A.limit_ratio(code, date, five_pct_regime=five_pct) * 100))


def _tol(pre_cents: int) -> int:
    """容差（分）：低价股按比例放宽，避免数据源小数精度造成漏判。"""
    return 1 if pre_cents < 500 else 2


# ---------------------------------------------------------------- 信号重建

def _five_pct_flags(closes: list, lookback: int = 60, min_bars: int = 40) -> list:
    """逐日标记该股当时是否处于 5% 涨跌幅制度（ST）。

    判据：滚动窗口内最大单日涨跌幅 ≤ 6% —— 5% 制度下不可能出现更大的波动。
    只依赖当日之前的数据，无未来函数。

    实现上不真的去扫窗口，而是记录「上一次出现大波动的位置」，
    在它过去 lookback 根之后即标记为 5% 制度。全样本 O(n)：
    朴素写法是 O(n×lookback)，在 1400 万行的全市场上会慢到不可用。
    """
    n = len(closes)
    flags = [0] * n
    last_big = -(10 ** 9)
    for i in range(n):
        if i >= 1:
            p = closes[i - 1]
            if p:
                if abs(closes[i] - p) * 100.0 / p > 6.0:
                    last_big = i
        if i >= min_bars and (i - last_big) >= lookback:
            flags[i] = 1
    return flags


def rebuild_signals(conn: sqlite3.Connection, start: str = None, end: str = None,
                    codes: list = None, with_future: bool = True,
                    quiet: bool = False) -> dict:
    """由日线重建涨停事件表与市场情绪表。幂等，可增量重跑。

    逐个股票流式处理（不一次性载入全市场），内存占用与单只股票的
    历史长度成正比，而不是与全库行数成正比。
    """
    t0 = time.time()
    A.init_schema(conn)          # 保证 lu_event / market_daily 存在（旧库升级也要能跑）
    codes_filter = codes
    if codes is None:
        # 以 daily 表为准，而不是 stock_meta —— 用 --codes 增量抓数时
        # stock_meta 可能没有对应行，会导致「有数据却重建出 0 个事件」。
        codes = [r[0] for r in conn.execute(
            "SELECT DISTINCT code FROM daily ORDER BY code")]

    # 全量重建（无日期区间、无指定股票）时先清空，避免数据修正后
    # 残留「已经不存在」的旧事件行 —— INSERT OR REPLACE 只会覆盖，
    # 不会删除消失的行。带 start/end 或 codes 的局部重建则不清空。
    if codes_filter is None and not start and not end:
        conn.execute("DELETE FROM lu_event")
        conn.execute("DELETE FROM market_daily")
        conn.commit()

    names = {}
    boards = {}
    st_flag = {}
    for c, n, b, s in conn.execute("SELECT code,name,board,is_st FROM stock_meta"):
        names[c], boards[c], st_flag[c] = n, b, s

    # 分批落库：全市场 12 年的涨停事件可达数十万条，若一次性攒在内存里
    # 再 INSERT，峰值内存会到几百 MB~1GB。改成攒满 BATCH 条就落库并清空，
    # 峰值内存只与 BATCH 成正比，与全样本规模无关。
    LU_SQL = "INSERT OR REPLACE INTO lu_event VALUES(" + ",".join("?" * 29) + ")"
    BATCH = EVENT_BATCH
    batch = []
    total_events = 0

    def _flush():
        if batch:
            conn.executemany(LU_SQL, batch)
            conn.commit()
            batch.clear()

    md = {}
    n_codes = 0
    for code in codes:
        rows = conn.execute(
            "SELECT date,open,high,low,close,volume,amount,turnover FROM daily "
            "WHERE code=? ORDER BY date", (code,)).fetchall()
        n = len(rows)
        if n < 30:
            continue
        n_codes += 1
        dates = [r[0] for r in rows]
        oc = [cent(r[1]) for r in rows]
        hc = [cent(r[2]) for r in rows]
        lc = [cent(r[3]) for r in rows]
        cc = [cent(r[4]) for r in rows]
        vol = [r[5] or 0 for r in rows]
        amt = [r[6] or 0 for r in rows]
        tov = [r[7] for r in rows]

        closes_f = [r[4] for r in rows]
        five = _five_pct_flags(closes_f)
        board = boards.get(code) or A.board_of(code)

        prev_lu = [0] * n     # 按日期下标记录涨停状态，供回溯计数
        streak_run = 0
        for i in range(1, n):
            d = dates[i]
            d_next = dates[i + 1] if i + 1 < n else None
            d_next2 = dates[i + 2] if i + 2 < n else None
            pre = cc[i - 1]
            if pre <= 0:
                continue
            rp = ratio_pct_of(code, d, bool(five[i - 1]))
            tol = _tol(pre)
            # ---- 涨停 / 跌停判定（整数分价） ----
            is_lu = abs(cc[i] - lu_by_ratio(pre, rp)) <= tol
            if not is_lu and rp != 5 and five[i - 1]:
                # 5% 制度股（主板 ST）：仅在滚动窗口推断出处于 5% 制度时才试 5% 阈值。
                # 不加这个门槛，任何恰好收在 +5.00% 的普通股都会被误判为涨停。
                is_lu = abs(cc[i] - lu_by_ratio(pre, 5)) <= tol
                if is_lu:
                    rp = 5
            is_ld = abs(cc[i] - ld_by_ratio(pre, rp)) <= tol
            # 必须按日期下标写入：若用 append，下标会与日期错开一位，
            # 导致回溯窗口把「当日」也算进去，「首板」将永远判定为 0。
            prev_lu[i] = 1 if is_lu else 0

            if is_ld:
                md.setdefault(d, {}).setdefault("ld", 0)
                md[d]["ld"] += 1

            if is_lu:
                streak_run += 1
            else:
                streak_run = 0

            # ---- 市场情绪：昨日涨停股今日表现 ----
            if is_lu and d_next:
                pre_next = cc[i]
                rp_next = ratio_pct_of(code, d_next, bool(five[i]))
                tol_n = _tol(pre_next)
                gap = (cc[i + 1] - pre_next) / pre_next if pre_next else 0.0
                exdiv = abs(gap) > (rp_next / 100.0 + 0.03)
                if not exdiv:
                    rec = md.setdefault(d_next, {})
                    rec["yp_sum"] = rec.get("yp_sum", 0.0) + gap
                    rec["yp_n"] = rec.get("yp_n", 0) + 1
                    rec["yp_win"] = rec.get("yp_win", 0) + (1 if gap > 0 else 0)

            if not is_lu:
                continue

            # ---- 以下只对涨停日计算因子（数量级小得多） ----
            lu = lu_by_ratio(pre, rp)
            rec = md.setdefault(d, {})
            rec["lu"] = rec.get("lu", 0) + 1
            rec["streak"] = max(rec.get("streak", 0), streak_run)

            # 形态分类。日线拿不到封板时间，只能从「开盘是否即涨停」与
            # 「日内最大回撤」两个可观测特征来分档，不要把它当成封板强度本身。
            if oc[i] == lu and lc[i] == lu:
                shape = "一字板"
            elif oc[i] == lu:
                shape = "T字板"
            else:
                body = (lu - lc[i]) / pre
                shape = "浅回撤" if body <= 0.03 else "深回撤"

            # 量能倍数：前 5 日均量（不含当日）
            j0 = max(0, i - 5)
            seg = [v for v in vol[j0:i] if v > 0]
            vr = (vol[i] / (sum(seg) / len(seg))) if seg and sum(seg) > 0 else None

            # 前 20 日累计涨幅（不含当日）
            pr = None
            if i - 21 >= 0 and cc[i - 21] > 0:
                pr = cc[i - 1] / cc[i - 21] - 1.0

            # 60 日位置
            w0 = max(0, i - 59)
            hi60 = max(cc[w0:i + 1]) if i >= w0 else cc[i]
            pos60 = cc[i] / hi60 if hi60 else None

            prior20 = sum(prev_lu[max(0, i - LOOKBACK_FIRST):i])
            is_first = 1 if prior20 == 0 else 0
            if is_first:
                rec["first"] = rec.get("first", 0) + 1

            # ---- 前瞻收益（仅回测用） ----
            t1_gap = t1_oc = t1_tradable = t1_ld = t2_oo = t2_oc = None
            exdiv_risk = 0
            if with_future and d_next:
                pre_next = cc[i]
                rp_next = ratio_pct_of(code, d_next, bool(five[i]))
                tol_n = _tol(pre_next)
                lu_next = lu_by_ratio(pre_next, rp_next)
                t1_gap = (oc[i + 1] - pre_next) / pre_next
                t1_oc = (cc[i + 1] - oc[i + 1]) / oc[i + 1] if oc[i + 1] else None
                t1_tradable = 1 if oc[i + 1] < lu_next - tol_n else 0
                t1_ld = 1 if abs(cc[i + 1] - ld_by_ratio(pre_next, rp_next)) <= tol_n else 0
                if abs(t1_gap) > (rp_next / 100.0 + 0.03):
                    exdiv_risk = 1
                if d_next2:
                    t2_oo = (oc[i + 2] - oc[i + 1]) / oc[i + 1] if oc[i + 1] else None
                    t2_oc = (cc[i + 2] - oc[i + 1]) / oc[i + 1] if oc[i + 1] else None
                    g2 = (oc[i + 2] - cc[i + 1]) / cc[i + 1] if cc[i + 1] else 0.0
                    if abs(g2) > (rp_next / 100.0 + 0.03):
                        exdiv_risk = 1

            if (start and d < start) or (end and d > end):
                continue
            batch.append((
                code, d, pre / 100.0, oc[i] / 100.0, hc[i] / 100.0,
                lc[i] / 100.0, cc[i] / 100.0, lu / 100.0,
                shape, (lu - lc[i]) / pre, (oc[i] - pre) / pre, None,
                vr, amt[i] / 1e8, tov[i], cc[i] / 100.0,
                pr, pos60, prior20, streak_run, is_first, i + 1,
                t1_gap, t1_oc, t1_tradable, t1_ld, t2_oo, t2_oc, exdiv_risk))
            total_events += 1
            if len(batch) >= BATCH:
                _flush()

    # ---- 落库 ----
    _flush()
    conn.executemany(
        "INSERT OR REPLACE INTO market_daily VALUES(?,?,?,?,?,?,?,?)",
        [(d, v.get("lu", 0), v.get("ld", 0), v.get("first", 0), v.get("streak", 0),
          (v.get("yp_sum", 0.0) / v["yp_n"]) if v.get("yp_n") else None,
          v.get("yp_n", 0),
          (v.get("yp_win", 0) / v["yp_n"]) if v.get("yp_n") else None)
         for d, v in sorted(md.items())])
    conn.commit()
    info = {"codes": n_codes, "events": total_events, "days": len(md),
            "elapsed": time.time() - t0}
    if not quiet:
        print(f"  信号重建完成：{n_codes} 只 / 涨停事件 {total_events:,} / "
              f"{len(md)} 个交易日 / {time.time()-t0:.1f}s")
    return info


# ---------------------------------------------------------------- 打分

def band_score(x, lo: float, hi: float, soft: float) -> float:
    """区间型因子打分：落在 [lo,hi] 内得 1，超出后线性衰减到 0。

    打板因子多是「适中最好」而非「越大越好」：量能太小说明无人关注，
    太大往往是高位放量出货；成交额太小流动性差容易被闷杀，
    太大则盘子重、次日溢价低。故用区间而非单调方向。
    """
    if x is None:
        return 0.5                       # 缺失给中性分，不奖不罚
    if lo <= x <= hi:
        return 1.0
    if x < lo:
        return max(0.0, 1.0 - (lo - x) / soft) if soft else 0.0
    return max(0.0, 1.0 - (x - hi) / soft) if soft else 0.0


def score_events(events: list, market: dict) -> list:
    """对同一交易日的候选打分 -> 0~100 的复合分。

    ``events`` 是当日候选（dict），``market`` 是市场情绪行。
    **注意：只用 T 日及之前的字段，签名里也不接受前瞻字段。**
    """
    if not events:
        return []
    # 秩次归一化（横截面），避免极端值主导
    def ranks(vals):
        idx = sorted(range(len(vals)), key=lambda i: (vals[i] is None, vals[i]))
        out = [0.0] * len(vals)
        cnt = 0
        for pos, i in enumerate(idx):
            if vals[i] is None:
                out[i] = 0.5
            else:
                out[i] = pos / max(1, len(vals) - 1)
                cnt += 1
        return out

    seal = ranks([-(e.get("body_depth") if e.get("body_depth") is not None else 0.05)
                  for e in events])
    vol = ranks([band_score(e.get("vol_ratio"), *BANDS["vol"]) for e in events])
    amt = ranks([band_score(e.get("amount_yi"), *BANDS["amount"]) for e in events])
    prc = ranks([band_score(e.get("price"), *BANDS["price"]) for e in events])
    prv = ranks([band_score(e.get("prev_ret20"), *BANDS["prev"]) for e in events])
    pos = ranks([e.get("pos60") if e.get("pos60") is not None else 0.5 for e in events])
    fst = [1.0 if e.get("is_first") else 0.35 for e in events]

    out = []
    for k, e in enumerate(events):
        s = (WEIGHTS["seal"] * seal[k] + WEIGHTS["vol"] * vol[k]
             + WEIGHTS["amount"] * amt[k] + WEIGHTS["price"] * prc[k]
             + WEIGHTS["prev"] * prv[k] + WEIGHTS["pos"] * pos[k]
             + WEIGHTS["first"] * fst[k])
        item = dict(e)
        item["score"] = round(s * 100, 2)
        item["parts"] = {"封板": round(seal[k], 3), "量能": round(vol[k], 3),
                         "成交额": round(amt[k], 3), "价格": round(prc[k], 3),
                         "涨幅": round(prv[k], 3), "位置": round(pos[k], 3),
                         "首板": round(fst[k], 3)}
        out.append(item)
    out.sort(key=lambda x: -x["score"])
    return out


def hard_filters(e: dict) -> tuple:
    """硬性剔除规则，返回 (是否通过, 原因)。全部只依赖 T 日信息。"""
    if not e.get("is_first"):
        return False, "非首板"
    if e.get("shape") == "一字板":
        return False, "一字板（次日大概率无法买入）"
    if (e.get("price") or 0) < 2.0:
        return False, "股价过低（面值退市风险）"
    if (e.get("amount_yi") or 0) < MIN_AMOUNT_YI:
        return False, f"成交额不足 {MIN_AMOUNT_YI} 亿"
    if (e.get("bars_listed") or 0) < MIN_BARS_LISTED:
        return False, "次新股（上市不足 60 交易日）"
    if e.get("prev_ret20") is not None and e["prev_ret20"] > MAX_PREV_RET20:
        return False, f"前 20 日涨幅超 {MAX_PREV_RET20:.0%}"
    if e.get("streak", 1) > 1:
        return False, "非首板"
    return True, ""


def market_regime(m: dict, n_codes: int = None) -> dict:
    """市场情绪闸门 -> 建议仓位。

    打板策略的收益高度依赖市场情绪周期：赚钱效应好时首板次日溢价高，
    冰点期则普遍炸板。因此情绪不参与**选股**（它对当日所有股票相同），
    而是决定**总仓位**——这是这类策略最有效的一道风控。

    主判据用 ``yest_lu_premium``（昨日涨停股今日平均涨幅），它是**个股级
    收益率**，与股票池大小无关；``lu_count`` 只作辅助确认，且阈值按股票池
    规模缩放 —— 固定阈值（如 60 家）在全市场合适，但在小样本上会让
    每一天都判为「冰点」而完全不开仓。
    """
    if not m:
        return {"level": "数据不足", "position": 0.0, "note": "无市场情绪数据"}
    prem = m.get("yest_lu_premium")
    lu = m.get("lu_count") or 0
    st_ = m.get("max_streak") or 0
    win = m.get("yest_lu_winrate")
    if prem is None:
        return {"level": "数据不足", "position": 0.0, "note": "昨日涨停样本为空"}

    # 涨停家数阈值随股票池规模缩放（以约 5000 只全市场为基准）
    scale = (n_codes / 5000.0) if n_codes else 1.0
    scale = min(1.0, max(0.02, scale))
    lu_strong = max(3, int(60 * scale))
    lu_ok = max(2, int(40 * scale))
    lu_dead = max(1, int(20 * scale))

    if prem > 0.02 and lu >= lu_strong and st_ >= 4:
        lv, pos = "进攻", 1.0
    elif prem > 0.0 and lu >= lu_ok:
        lv, pos = "平衡", 0.6
    elif prem > -0.03:
        lv, pos = "防守", 0.3
    else:
        lv, pos = "空仓", 0.0
    if lu < lu_dead:
        # 涨停家数过少说明市场没有做多合力，即便溢价尚可也应降档
        lv, pos = ("冰点", 0.0) if prem <= 0 else ("防守", min(pos, 0.3))
    return {"level": lv, "position": pos,
            "note": f"昨日涨停今日均涨 {prem:+.2%}（样本 {m.get('yest_lu_sample') or 0}，"
                    f"收红率 {(win or 0):.0%}）；涨停 {lu} 家，最高 {st_} 板；"
                    f"阈值按股票池 {n_codes or '全市场'} 只缩放"}


# ---------------------------------------------------------------- 交易计划

def build_plan(item: dict, regime: dict) -> dict:
    """把打分候选转成可执行的次日交易计划。

    计划刻意写得「有条件」：打板的关键不是选出来，而是**次日什么价格才值得买**。
    高开太多意味着溢价已被吃掉，低开说明昨日封板不被认可。
    """
    lu = item.get("lu_price") or item.get("price") or 0
    shape = item.get("shape") or "-"
    # 买入区间：竞价高开 0%~+4% 为佳；>7% 放弃；低开 -3% 以下放弃
    buy_lo, buy_hi, give_up = 0.00, 0.04, 0.07
    plan = {
        "code": item["code"], "date": item["date"], "score": item["score"],
        "buy_cond": (f"竞价高开 {buy_lo:+.0%}~{buy_hi:+.0%} 分批挂单；"
                     f"高开 >{give_up:.0%} 放弃（溢价已被吃掉）；"
                     f"低开 <-3% 放弃（昨日封板不被认可）"),
        "add_cond": "开盘未及区间但盘中再度封板，可跟随打板，仓位减半",
        "stop": f"跌破 {lu * 0.97:.2f}（T日涨停价 -3%）或跌破分时均价即离场",
        "target": "T+1 收盘前离场（首板次日溢价为主）；封板可持有至 T+2",
        "position": f"单票 {min(0.10, 0.10 * regime.get('position', 0)):.0%} 仓位",
        "invalidate": "次日高开低走且量能放大到昨日 1.5 倍以上，视为出货，立即离场",
    }
    return plan
