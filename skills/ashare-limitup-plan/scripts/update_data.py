#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收盘后增量更新全 A 股日线数据。

用法
----
    # 首次全量回填（12 年 × 全 A，约 40 分钟）
    python update_data.py --years 2014-2026

    # 日常增量（收盘后跑，约 3 分钟）—— 每只股票只需 1 个请求
    python update_data.py --incremental

    # 试跑 / 指定范围
    python update_data.py --incremental --limit 50
    python update_data.py --years 2024-2026 --codes 600000,000001,300750

设计要点
--------
1. **增量靠 `last.js`**：同花顺 last.js 单次返回最近约 140 根日线，
   并附带 ``year`` 年份映射（{年份: 交易日数}）。因此日常更新对每只股票
   只需 1 个请求，全市场约 3 分钟；同时它还能告诉我们该股有哪些年的历史，
   回填时无需额外探测。
   注意 URL 中的复权标志位必须为 ``00``（不复权）—— 详见 ashare_lib 的说明。

2. **网络与写库分离**：工作线程只做 HTTP + 解析，SQLite 写入集中在
   主线程按完成顺序批量提交。SQLite 单写者模型下这样最省心，
   也避免多线程写库的锁竞争。

3. **幂等**：全部走 INSERT OR REPLACE，重复跑不会产生脏数据，
   中断后重跑即可续上（按**已入库年份集合**判断缺口，不能用 last_date，
   原因见 ``plan_years``）。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ashare_lib as A  # noqa: E402


def parse_years(spec: str) -> list:
    """解析 ``2014-2026`` 或 ``2014,2016,2020`` 形式的年份。"""
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def upsert_meta_rows(conn, uni: list) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        "INSERT INTO stock_meta(code,symbol,name,board,is_st,float_mv,total_mv,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET symbol=excluded.symbol, name=excluded.name, "
        "board=excluded.board, is_st=excluded.is_st, float_mv=excluded.float_mv, "
        "total_mv=excluded.total_mv, updated_at=excluded.updated_at",
        [(u["code"], u["symbol"], u["name"], A.board_of(u["code"]),
          1 if ("ST" in (u["name"] or "")) else 0,
          u.get("float_mv"), u.get("total_mv"), now) for u in uni])
    conn.commit()


def write_rows(conn, code: str, rows: list) -> int:
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO daily(code,date,open,high,low,close,volume,amount,turnover) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        [(code,) + tuple(r) for r in rows])
    return len(rows)


def refresh_meta_stats(conn, code: str, years_hint: dict = None) -> None:
    r = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily WHERE code=?",
                     (code,)).fetchone()
    conn.execute("UPDATE stock_meta SET bars=?, list_hint=?, last_date=? WHERE code=?",
                 (r[0], r[1], r[2], code))


def plan_years(meta: dict, want: list, have_years: set) -> list:
    """确定该股还需要补哪些**年份**。

    关键点：不能用「最后日期」判断历史是否补齐 —— last.js 只给最近 140 根，
    它会让 last_date 看起来是最新的，从而误判为「无需回填」。
    必须比对**已入库年份集合**与目标年份集合的差集。

    ``meta['year']`` 来自 last.js，是 {年份: 交易日数}，直接用真实存在的年份，
    避免对未上市年份发无效请求。
    """
    avail = set((meta.get("year") or {}).keys())
    if not avail:
        return []
    lo, hi = min(want), max(want)
    target = {y for y in avail if lo <= y <= hi}
    return sorted(target - (have_years or set()))


def worker(code: str, want_years: list, have_years: set, source: str):
    """线程体：只做网络与解析，不碰数据库。"""
    try:
        if source == "ths":
            meta, recent = A.fetch_ths_last(code)
            rows = list(recent)
            for y in plan_years(meta, want_years, have_years):
                try:
                    rows += A.fetch_ths_year(code, y)
                except Exception:
                    continue
            dedup = {}
            for r in rows:
                dedup[r[0]] = r
            rows = [dedup[d] for d in sorted(dedup)]
            return code, rows, meta.get("name"), None
        if source == "sina":
            return code, A.fetch_kline_sina(A.sina_symbol_of(code), 3000), None, None
        return code, A.fetch_kline_em(A.secid_of(code)), None, None
    except Exception as exc:  # noqa: BLE001
        return code, [], None, f"{type(exc).__name__}: {str(exc)[:80]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="A股日线增量更新")
    ap.add_argument("--years", default="2014-2026", help="历史回填年份，如 2014-2026")
    ap.add_argument("--incremental", action="store_true",
                    help="增量模式：只补最近缺口（每只股票 1 个请求）")
    ap.add_argument("--codes", default="", help="仅处理指定代码，逗号分隔")
    ap.add_argument("--limit", type=int, default=0, help="仅处理前 N 只（试跑用）")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--source", default="ths", choices=list(A.SOURCES))
    ap.add_argument("--no-universe", action="store_true", help="跳过名单刷新")
    args = ap.parse_args()

    t_all = time.time()
    conn = A.connect()
    A.init_schema(conn)

    # ---------- 1. 股票名单 ----------
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        print(f"[1/3] 使用指定代码 {len(codes)} 只")
    elif args.no_universe:
        codes = [r[0] for r in conn.execute("SELECT code FROM stock_meta ORDER BY code")]
        print(f"[1/3] 沿用库内名单 {len(codes)} 只")
    else:
        t0 = time.time()
        print("[1/3] 抓取全 A 股名单（新浪 hs_a，含北交所）...", flush=True)
        uni = A.fetch_universe()
        upsert_meta_rows(conn, uni)
        codes = [u["code"] for u in uni]
        print(f"      拿到 {len(codes)} 只，耗时 {time.time()-t0:.1f}s；"
              f"ST {sum(1 for u in uni if 'ST' in (u['name'] or ''))} 只", flush=True)

    if args.limit:
        codes = codes[:args.limit]

    want_years = parse_years(args.years)

    # ---------- 2. 逐股抓取 ----------
    # 已入库年份集合：用于判断哪些年份还需要回填（见 plan_years 的说明）
    have_years = {}
    for c, y in conn.execute(
            "SELECT code, substr(date,1,4) FROM daily GROUP BY code, substr(date,1,4)"):
        have_years.setdefault(c, set()).add(int(y))
    if args.incremental:
        for c in codes:                       # 增量模式：不补年份，只吃 last.js
            have_years[c] = set(range(min(want_years), max(want_years) + 1))
    tasks = [(c, want_years, have_years.get(c, set()), args.source) for c in codes]

    print(f"[2/3] 抓取日线：{len(tasks)} 只，线程 {args.workers}，源 {args.source}，"
          f"目标年份 {min(want_years)}-{max(want_years)}", flush=True)
    t0 = time.time()
    total_rows, done, failed, empty = 0, 0, [], 0
    window = max(args.workers * 4, 16)
    pending, it = [], iter(tasks)

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        def submit_more():
            for _ in range(window - len(pending)):
                try:
                    pending.append(ex.submit(worker, *next(it)))
                except StopIteration:
                    break
        submit_more()
        while pending:
            fut = pending.pop(0)
            code, rows, _, err = fut.result()
            if err:
                failed.append((code, err))
            elif not rows:
                empty += 1
            n = write_rows(conn, code, rows)
            total_rows += n
            refresh_meta_stats(conn, code)
            done += 1
            if done % 200 == 0:
                conn.commit()
                el = time.time() - t0
                rps = done / el if el else 0
                eta = (len(tasks) - done) / rps / 60 if rps else 0
                print(f"      {done}/{len(tasks)}  行数 {total_rows:,}  "
                      f"耗时 {el/60:.1f}min  ETA {eta:.1f}min", flush=True)
            submit_more()
    conn.commit()

    # ---------- 3. 收尾 ----------
    refresh_all = conn.execute(
        "UPDATE stock_meta SET bars=(SELECT COUNT(*) FROM daily d WHERE d.code=stock_meta.code),"
        " list_hint=(SELECT MIN(date) FROM daily d WHERE d.code=stock_meta.code),"
        " last_date=(SELECT MAX(date) FROM daily d WHERE d.code=stock_meta.code)")
    conn.commit()
    # 交易日历门槛按实际股票数自适应，避免小样本试跑时得到空日历
    n_active = conn.execute("SELECT COUNT(DISTINCT code) FROM daily").fetchone()[0] or 1
    days = A.trading_days(conn, min_stocks=max(5, int(n_active * 0.3)))
    last_day = days[-1] if days else "无"
    A.set_meta(conn, "last_update", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    A.set_meta(conn, "last_trade_date", last_day)
    A.set_meta(conn, "data_version", A.DATA_VERSION)
    conn.commit()

    n_rows = conn.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    n_codes = conn.execute("SELECT COUNT(DISTINCT code) FROM daily").fetchone()[0]
    db_mb = os.path.getsize(A.db_path()) / 1024 / 1024

    print("\n" + "=" * 62)
    print("更新完成")
    print("=" * 62)
    print(f"  数据库        : {A.db_path()}  ({db_mb:.0f} MB)")
    print(f"  本次写入      : {total_rows:,} 行 / {done} 只")
    print(f"  库内累计      : {n_rows:,} 行 / {n_codes} 只")
    print(f"  交易日        : {len(days)} 天  {days[0] if days else '-'} ~ {last_day}")
    print(f"  空数据        : {empty} 只")
    print(f"  失败          : {len(failed)} 只")
    for c, e in failed[:8]:
        print(f"      {c}  {e}")
    print(f"  总耗时        : {(time.time()-t_all)/60:.1f} 分钟")

    # ---------- 4. 数据完整性自检 ----------
    # 专门预警「复权口径取错 → 历史被截断」这一类问题：同花顺 URL 中间那一位
    # 为 00（不复权）时老股应覆盖到目标起始年；若误用 01（前复权），
    # 前复权序列是滚动重算的，同花顺只提供有限起点，老股会只覆盖近几年。
    # 用几只长期上市的参照股做哨兵，一旦起始日期明显偏晚就报警。
    print("\n  数据完整性自检：")
    y_lo = min(want_years)
    sentinels = ["600519", "600022", "601398", "000001"]
    bad = []
    for c in sentinels:
        r = conn.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM daily WHERE code=?",
                         (c,)).fetchone()
        if not r or not r[0]:
            print(f"      {c}: 无数据 ⚠️")
            bad.append(c)
            continue
        print(f"      {c}: {r[0]} ~ {r[1]}  {r[2]} 根")
        if r[0][:4] > str(y_lo):
            bad.append(c)
    n_full = conn.execute(
        "SELECT COUNT(*) FROM (SELECT code FROM daily GROUP BY code HAVING MIN(date) <= ?)",
        (f"{y_lo}-06-30",)).fetchone()[0]
    print(f"      覆盖到 {y_lo} 年上半年前的股票：{n_full} / {n_codes} 只")
    if bad:
        print(f"      ⚠️ 警告：参照股 {','.join(bad)} 历史疑似被截断 —— "
              f"请检查数据源复权口径（同花顺 URL 中必须为 /00/ 不复权，"
              f"误用 /01/ 前复权会截断历史并使绝对价格失真）。")

    if failed:
        print("\n  提示：失败多为限流或停牌，直接重跑即可（幂等续传）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
