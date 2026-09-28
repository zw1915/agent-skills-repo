#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股打板选股 — 基础库（数据获取 / 涨跌停制度 / SQLite 存储）

设计约束
--------
1. **零第三方依赖**：只用 Python 标准库（urllib / sqlite3 / json / decimal）。
   实测 akshare 在 Python 3.13 环境下依赖解析失败，且其依赖的东财 clist
   接口不稳定；自建轻量数据层反而更可靠、更易审计。
2. **不复权原始价格**：涨跌停价是按**未复权价**计算并四舍五入到分的，
   因此必须用原始价格判定涨停，复权价会破坏这个等式。
   同花顺接口的复权标志位必须取 ``00``（不复权）；``01``（前复权）不仅价格
   口径不对，其历史还被截断，详见下文 ``THS_YEAR_URL`` 处的说明。
3. **数据源可切换 + 自动降级**：主源同花顺（字段最全：OHLC+成交额+换手率，
   沪深北全覆盖，且抗并发）；备源新浪、东财（字段或限流各有短板）。

数据存放位置（**刻意放在技能目录之外**）
--------------------------------------
默认：``~/.workbuddy/data/ashare-limitup/market.db``
可用环境变量 ``ASHARE_DATA_HOME`` 覆盖。

放在包外有两个原因：一是技能包上传时目录只允许两级，运行时生成的
子目录会直接把包搞成不合规；二是数据可复用，重新安装技能不必重新下载。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

__all__ = [
    "data_home", "db_path", "connect", "init_schema", "set_meta", "get_meta",
    "http_get_text", "http_get_json",
    "fetch_universe", "fetch_kline_sina", "fetch_kline_em",
    "fetch_ths_last", "fetch_ths_year", "fetch_history", "SOURCES",
    "board_of", "secid_of", "sina_symbol_of",
    "limit_ratio", "limit_up_price", "limit_down_price",
    "looks_like_limit_up", "is_five_pct_regime",
    "trading_days", "load_panel", "name_map", "board_map", "DATA_VERSION",
]

DATA_VERSION = "1.0.0"

# 回测/选股默认起始年。新浪单次最多 3000 根日线，2026 年时约回溯到 2014-03，
# 故「12 年」是数据源能力上限而非刻意截断。
DEFAULT_START = "2014-01-01"


# ============================================================ 路径与配置

def data_home() -> str:
    """数据根目录（技能包之外）。"""
    p = os.environ.get("ASHARE_DATA_HOME")
    if not p:
        p = os.path.join(os.path.expanduser("~"), ".workbuddy", "data", "ashare-limitup")
    os.makedirs(p, exist_ok=True)
    return p


def db_path() -> str:
    return os.path.join(data_home(), "market.db")


# ============================================================ HTTP

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

HEADERS_SINA = {"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"}
HEADERS_EM = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}


def http_get_text(url: str, headers: dict = None, timeout: int = 30,
                  retries: int = 3, backoff: float = 1.6) -> str:
    """带指数退避的 GET。

    限流是真实存在的：实测高频请求东财会被短暂封禁（连接被直接关闭），
    因此所有抓取都必须走这里，不允许裸调 urlopen。
    """
    headers = headers or HEADERS_SINA
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001 - 网络异常种类多，统一退避重试
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff ** attempt)
    raise RuntimeError(f"请求失败（已重试 {retries} 次）：{last}")


def http_get_json(url: str, headers: dict = None, **kw):
    body = http_get_text(url, headers=headers, **kw)
    return json.loads(body)


# ============================================================ 涨跌停制度

def board_of(code: str) -> str:
    """按代码判断所属板块。"""
    c = str(code).strip()
    if c.startswith(("600", "601", "603", "605")):
        return "sh_main"
    if c.startswith(("000", "001", "002", "003")):
        return "sz_main"
    if c.startswith(("300", "301")):
        return "gem"          # 创业板
    if c.startswith(("688", "689")):
        return "star"         # 科创板
    if c.startswith(("4", "8", "920")):
        return "bj"           # 北交所（含原新三板精选层/创新层代码）
    return "other"


# 涨跌幅制度的历史切换（日期, 比例），按时间升序
_RATIO_TIMELINE = {
    "sh_main": [("1996-12-16", 0.10)],
    "sz_main": [("1996-12-16", 0.10)],
    "gem": [("2009-10-30", 0.10), ("2020-08-24", 0.20)],
    "star": [("2019-07-22", 0.20)],
    "bj": [("2021-11-15", 0.30)],
    "other": [("1996-12-16", 0.10)],
}


def limit_ratio(code: str, date: str, is_st: bool = False,
                five_pct_regime: bool = False) -> float:
    """取该股在该交易日的涨跌幅上限比例。

    创业板 2020-08-24 起由 10% 改为 20%，科创板自开板即 20%，
    北交所 30% —— 这些切换点必须按日期区分，否则跨年回测会大面积误判。
    ST 股主板为 5%，用 ``is_st`` 或数据推断的 ``five_pct_regime`` 触发。
    """
    b = board_of(code)
    ratio = _RATIO_TIMELINE.get(b, _RATIO_TIMELINE["other"])[0][1]
    for eff, r in _RATIO_TIMELINE.get(b, _RATIO_TIMELINE["other"]):
        if date >= eff:
            ratio = r
    # 主板 / 中小板的 ST 股为 5%；创业板、科创板 ST 仍为 20%
    if (is_st or five_pct_regime) and b in ("sh_main", "sz_main", "other"):
        ratio = 0.05
    return ratio


def _round2(x: float) -> float:
    """四舍五入到分（half-up）。

    Python 内置 round() 是银行家舍入，算涨停价会错，
    必须用 Decimal 显式指定 ROUND_HALF_UP。
    """
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def limit_up_price(preclose: float, ratio: float) -> float:
    return _round2(preclose * (1.0 + ratio))


def limit_down_price(preclose: float, ratio: float) -> float:
    return _round2(preclose * (1.0 - ratio))


def looks_like_limit_up(close: float, preclose: float, ratio: float,
                        tol: float = 0.005) -> bool:
    """收盘价是否等于涨停价（含半分容差，兼容数据源的小数精度）。"""
    if not preclose or preclose <= 0 or not close:
        return False
    return abs(close - limit_up_price(preclose, ratio)) <= tol


def is_five_pct_regime(closes: list, lookback: int = 60,
                       tol: float = 0.055, min_bars: int = 40) -> bool:
    """从价格行为反推该股当时是否处于 5% 涨跌幅制度（即 ST 状态）。

    历史 ST 标记无法从 OHLCV 直接获得。但 5% 制度有一个可观测特征：
    在此制度下不存在单日超过约 5% 的波动。因此用**滚动窗口内最大单日
    涨幅**来推断，只依赖当日之前的数据，无未来函数。

    比「用当前名称里的 ST 回溯历史」更准 —— 后者会把现在被 ST、
    历史上未被 ST 的区间全部误判。
    """
    seg = closes[-(lookback + 1):]
    if len(seg) < min_bars:
        return False
    mx = 0.0
    for i in range(1, len(seg)):
        p, c = seg[i - 1], seg[i]
        if p and p > 0:
            mx = max(mx, abs(c / p - 1.0))
    return mx <= tol


def secid_of(code: str) -> str:
    """东财 secid：1=沪市，0=深市/北交所。"""
    b = board_of(code)
    return ("1." if b in ("sh_main", "star") else "0.") + str(code)


def sina_symbol_of(code: str) -> str:
    """新浪符号：sh/sz/bj 前缀。"""
    b = board_of(code)
    pre = {"sh_main": "sh", "star": "sh", "sz_main": "sz", "gem": "sz", "bj": "bj"}.get(b, "sz")
    return pre + str(code)


# ============================================================ 数据源：股票名单

SINA_LIST_URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                 "Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1"
                 "&node=hs_a&symbol=&_s_r_a=page")


def fetch_universe(max_page: int = 80) -> list:
    """抓全 A 股名单（新浪 hs_a 节点，含北交所）。

    返回 [{code, symbol, name, price, float_mv, total_mv, turnover, amount}, ...]
    ``float_mv`` / ``total_mv`` 单位：亿元。

    注意：``nmc``/``mktcap`` 是**抓取当日**的市值，不是历史市值。
    用于历史回测时会引入轻微前视偏差，故策略里市值只作为辅助因子，
    主因子一律使用当日可由 OHLCV 推出的量（如成交额代理、量能倍数）。
    """
    out, seen = [], set()
    for page in range(1, max_page + 1):
        try:
            arr = http_get_json(SINA_LIST_URL.format(page=page), headers=HEADERS_SINA)
        except Exception:
            break
        if not arr:
            break
        for it in arr:
            code = str(it.get("code") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append({
                "code": code,
                "symbol": it.get("symbol") or sina_symbol_of(code),
                "name": (it.get("name") or "").strip(),
                "price": _f(it.get("trade")),
                "float_mv": _f(it.get("nmc")) / 1e8 if _f(it.get("nmc")) else None,
                "total_mv": _f(it.get("mktcap")) / 1e8 if _f(it.get("mktcap")) else None,
                "turnover": _f(it.get("turnoverratio")),
                "amount": _f(it.get("amount")),
            })
    return out


def _f(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# ============================================================ 数据源：日线

SINA_KLINE_URL = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                  "CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={n}")

EM_KLINE_URL = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                "fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                "&ut=fa5fd1943c7b386f172d6893dbfba10b&klt=101&fqt={fqt}"
                "&secid={secid}&beg={beg}&end={end}&lmt=1000000")


def fetch_kline_sina(symbol: str, datalen: int = 3000) -> list:
    """新浪日线（不复权）。备用源。

    返回 [(date, open, high, low, close, volume_shares, amount, turnover), ...]，按日期升序。
    成交额由 OHLC 均价推算，换手率缺失（新浪不提供）。
    """
    body = http_get_text(SINA_KLINE_URL.format(sym=symbol, n=datalen), headers=HEADERS_SINA)
    body = body.strip()
    if not body or body in ("null", "[]"):
        return []
    # 新浪偶发返回非严格 JSON（尾随逗号），做一次容错清洗
    body = re.sub(r",\s*([\]}])", r"\1", body)
    rows = json.loads(body)
    out = []
    for r in rows:
        d = (r.get("day") or "")[:10]
        o, h, l, c = _f(r.get("open")), _f(r.get("high")), _f(r.get("low")), _f(r.get("close"))
        v = _f(r.get("volume"))
        if not d or c is None or c <= 0:
            continue
        v = v or 0.0
        avg = (o + h + l + c) / 4.0 if None not in (o, h, l) else c
        out.append((d, o, h, l, c, v, v * avg, None))
    out.sort(key=lambda x: x[0])
    return out


def fetch_kline_em(secid: str, beg: str = "20140101", end: str = "20500101",
                   fqt: int = 0) -> list:
    """东财日线（默认不复权 fqt=0）。字段最全，作为第三备源。

    返回 8 元组，与其它数据源统一。
    """
    url = EM_KLINE_URL.format(secid=secid, beg=beg, end=end, fqt=fqt)
    d = http_get_json(url, headers=HEADERS_EM)
    ks = ((d or {}).get("data") or {}).get("klines") or []
    out = []
    for line in ks:
        p = line.split(",")
        if len(p) < 11:
            continue
        try:
            out.append((p[0][:10], float(p[1]), float(p[3]), float(p[4]), float(p[2]),
                        float(p[5]) * 100.0,      # 手 -> 股
                        _f(p[6]) or 0.0,          # 成交额（元）
                        _f(p[10])))               # 换手率 %
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


# ============================================================ 数据源：同花顺（主源）

# 同花顺 d.10jqka.com.cn 提供两种粒度：
#   last.js  -> 最近约 140 根日线 + 年份映射（增量更新只需 1 请求/股）
#   YYYY.js  -> 指定年份全年日线（历史回填用）
# 公开接口中它的字段最全：OHLC + 成交量 + 成交额 + 换手率，且覆盖沪深北。
# all.js 是列式差分编码（非明文），逆向成本高，故不使用。
#
# ！！！路径里的复权标志位是本项目最容易踩的坑 ！！！
# URL 中的 ``{mode}`` 段是复权口径，实测结论：
#   00 = 不复权   ← 本策略**必须**用这个
#   01 = 前复权   ← 曾误用过，两个致命问题（见下）
#   02 = 后复权
# 为什么必须用 00：
#   (1) 涨跌停价按未复权价四舍五入到分，复权价会破坏 close == round(pre×1.1) 这个等式；
#   (2) 更隐蔽的是，同花顺的前复权序列**历史被截断** ——
#       实测 600519 在 01 口径下 2014 年返回 0 根、2016 年只返回半年，
#       000001 只能回溯到 2024 年；而 00 口径下各年都完整（每年约 243 根）。
#       若用 01，会得到「看着有十几万行、实际每只股票只覆盖近几年」的残缺库，
#       而且绝对价格（价格因子、股价<2 元过滤）在历史区间全部失真。
#   (3) 00 口径下 600519 2014-01-02 收盘 125.98 元，与其真实历史价一致。
THS_LAST_URL = "https://d.10jqka.com.cn/v6/line/hs_{code}/00/last.js"
THS_YEAR_URL = "https://d.10jqka.com.cn/v6/line/hs_{code}/00/{year}.js"

HEADERS_THS = {"User-Agent": UA, "Referer": "https://stockpage.10jqka.com.cn/"}

_THS_JSONP = re.compile(r"\((\{.*\})\)", re.S)


def _ths_rows(payload: str) -> list:
    """解析同花顺明文字段：日期,开,高,低,收,成交量(股),成交额(元),换手率(%),?,?,?

    第 8 位是换手率（百分数）。后 3 位在实测中恒为空/0，未使用。
    """
    out = []
    for r in (payload or "").split(";"):
        p = r.split(",")
        if len(p) < 8 or len(p[0]) != 8 or not p[0].isdigit():
            continue
        o, h, l, c = _f(p[1]), _f(p[2]), _f(p[3]), _f(p[4])
        if None in (o, h, l, c) or c <= 0:
            continue
        out.append((f"{p[0][:4]}-{p[0][4:6]}-{p[0][6:]}", o, h, l, c,
                    _f(p[5]) or 0.0, _f(p[6]) or 0.0, _f(p[7])))
    return out


def fetch_ths_last(code: str) -> tuple:
    """取最近约 140 根日线 + 元信息（含年份映射）。

    返回 (meta, rows)：``meta['year']`` 是 {年份: 该年交易日数}，
    用它即可知道该股有哪些年的历史，无需额外探测。

    注意：last.js 用 ``year`` 字段（字典），all.js 用 ``sortYear``（列表），
    两者键名与结构都不同 —— 只读 sortYear 会静默拿到空映射，
    进而导致历史回填被跳过。
    """
    body = http_get_text(THS_LAST_URL.format(code=code), headers=HEADERS_THS)
    m = _THS_JSONP.search(body)
    if not m:
        return {}, []
    obj = json.loads(m.group(1))
    raw = obj.get("year")
    if raw is None:
        raw = obj.get("sortYear")
    years = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                years[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                years[int(item[0])] = int(item[1])
    meta = {"year": years, "start": obj.get("start"), "total": obj.get("total"),
            "name": obj.get("name")}
    return meta, _ths_rows(obj.get("data"))


def fetch_ths_year(code: str, year: int) -> list:
    """取指定年份全年日线。"""
    body = http_get_text(THS_YEAR_URL.format(code=code, year=year), headers=HEADERS_THS)
    m = _THS_JSONP.search(body)
    if not m:
        return []
    return _ths_rows(json.loads(m.group(1)).get("data"))


# 数据源注册表：按优先级排序，逐个回退
SOURCES = ("ths", "sina", "em")


def fetch_history(code: str, years: list, source: str = "ths") -> list:
    """按指定年份清单抓历史（多源回退），返回合并后的 8 元组列表。"""
    rows = []
    if source == "ths":
        for y in years:
            try:
                rows += fetch_ths_year(code, y)
            except Exception:
                continue
    elif source == "sina":
        rows = fetch_kline_sina(sina_symbol_of(code), 3000)
    elif source == "em":
        rows = fetch_kline_em(secid_of(code))
    rows.sort(key=lambda x: x[0])
    # 去重（同一天重复时保留后者）
    dedup = {}
    for r in rows:
        dedup[r[0]] = r
    return [dedup[d] for d in sorted(dedup)]



# ============================================================ SQLite 存储

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_meta (
    code        TEXT PRIMARY KEY,
    symbol      TEXT,
    name        TEXT,
    board       TEXT,
    is_st       INTEGER DEFAULT 0,
    float_mv    REAL,          -- 亿元，抓取当日快照
    total_mv    REAL,          -- 亿元，抓取当日快照
    list_hint   TEXT,          -- 第一条日线日期，用于判断上市时间
    last_date   TEXT,          -- 已入库的最后交易日
    bars        INTEGER DEFAULT 0,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS daily (
    code     TEXT NOT NULL,
    date     TEXT NOT NULL,
    open     REAL, high REAL, low REAL, close REAL,
    volume   REAL,             -- 股
    amount   REAL,             -- 元（成交额；新浪源为 OHLC 均价推算值）
    turnover REAL,             -- %（换手率；新浪源为 NULL）
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily(date);
CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily(code, date);
CREATE TABLE IF NOT EXISTS plan (
    plan_date  TEXT NOT NULL,
    rank       INTEGER,
    code       TEXT,
    name       TEXT,
    score      REAL,
    detail     TEXT,
    created_at TEXT,
    PRIMARY KEY (plan_date, code)
);
CREATE TABLE IF NOT EXISTS backtest_run (
    run_id     TEXT PRIMARY KEY,
    created_at TEXT,
    params     TEXT,
    metrics    TEXT
);

-- 涨停事件表：由日线重建，含因子与前瞻收益，选股与回测共用同一口径
CREATE TABLE IF NOT EXISTS lu_event (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    -- 当日行情（未复权）
    preclose    REAL, open REAL, high REAL, low REAL, close REAL,
    lu_price    REAL,
    -- 形态因子
    shape       TEXT,        -- 一字 / T字 / 实体 / 开板
    body_depth  REAL,        -- (涨停价-最低价)/昨收，日内回撤深度，越小越强
    gap_open    REAL,        -- 开盘涨幅
    seal_minute INTEGER,     -- 占位：日线无法得到封板时间，恒为 NULL
    -- 量能因子
    vol_ratio   REAL,        -- 量能倍数 = 当日量 / 前5日均量
    amount_yi   REAL,        -- 成交额（亿元）
    turnover    REAL,        -- 换手率 %
    price       REAL,        -- 收盘价（≈涨停价）
    -- 位置与形态因子
    prev_ret20  REAL,        -- 前 20 日累计涨幅（不含当日）
    pos60       REAL,        -- 收盘 / 近 60 日最高收盘
    prior_lu20  INTEGER,     -- 前 20 日涨停次数
    streak      INTEGER,     -- 连板数（含当日）
    is_first    INTEGER,     -- 是否首板
    bars_listed INTEGER,     -- 上市至当日的交易日数
    -- 前瞻收益（回测用；--no-future 时全为 NULL）
    t1_gap      REAL,        -- T+1 开盘 / T 收盘 - 1
    t1_oc       REAL,        -- T+1 收盘 / T+1 开盘 - 1（日内，除权日仍有效）
    t1_tradable INTEGER,     -- 1=次日开盘可买入（非一字涨停开盘）
    t1_ld       INTEGER,     -- 1=次日跌停（无法卖出）
    t2_oo       REAL,        -- T+2 开盘 / T+1 开盘 - 1
    t2_oc       REAL,        -- T+2 收盘 / T+1 开盘 - 1
    exdiv_risk  INTEGER,     -- 1=疑似除权日，跨日收益不可信
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_lu_date ON lu_event(date);
CREATE INDEX IF NOT EXISTS idx_lu_first ON lu_event(is_first, date);

-- 市场情绪日表：全市场口径，用作仓位闸门
CREATE TABLE IF NOT EXISTS market_daily (
    date            TEXT PRIMARY KEY,
    lu_count        INTEGER,   -- 涨停家数
    ld_count        INTEGER,   -- 跌停家数
    first_count     INTEGER,   -- 首板家数
    max_streak      INTEGER,   -- 最高连板高度
    yest_lu_premium REAL,      -- 昨日涨停股今日平均涨幅（打板赚钱效应）
    yest_lu_sample  INTEGER,   -- 样本数
    yest_lu_winrate REAL       -- 昨日涨停股今日收红比例
);
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


def connect(path: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path(), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def set_meta(conn, k: str, v: str) -> None:
    conn.execute("INSERT INTO meta(k,v) VALUES(?,?) "
                 "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def get_meta(conn, k: str, default=None):
    r = conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


# ============================================================ 面板读取

def trading_days(conn: sqlite3.Connection, min_stocks: int = None) -> list:
    """交易日历：以「当日有行情的股票数」为门槛，滤掉个别异常日期。

    ``min_stocks`` 默认自适应为当前库内股票数的 30% —— 固定阈值（如 300）
    在全市场跑没问题，但小样本试跑时会直接返回空日历，让人误以为数据没抓到。
    """
    if min_stocks is None:
        n = conn.execute("SELECT COUNT(DISTINCT code) FROM daily").fetchone()[0] or 1
        min_stocks = max(3, int(n * 0.3))
    rs = conn.execute(
        "SELECT date, COUNT(*) c FROM daily GROUP BY date HAVING c >= ? ORDER BY date",
        (min_stocks,)).fetchall()
    return [r[0] for r in rs]


def load_panel(conn: sqlite3.Connection, start: str = None, end: str = None,
               codes: list = None) -> dict:
    """读日线面板 -> {code: [(date, o,h,l,c, volume, amount, turnover), ...]}

    这是策略层唯一的数据入口，保证选股与回测使用完全一致的取数口径。
    """
    q = "SELECT code,date,open,high,low,close,volume,amount,turnover FROM daily WHERE 1=1"
    args = []
    if start:
        q += " AND date >= ?"; args.append(start)
    if end:
        q += " AND date <= ?"; args.append(end)
    if codes:
        q += " AND code IN (%s)" % ",".join("?" * len(codes)); args += list(codes)
    q += " ORDER BY code, date"
    panel = {}
    for code, d, o, h, l, c, v, a, t in conn.execute(q, args):
        panel.setdefault(code, []).append((d, o, h, l, c, v, a, t))
    return panel


def name_map(conn: sqlite3.Connection) -> dict:
    return {c: n for c, n in conn.execute("SELECT code,name FROM stock_meta")}


def board_map(conn: sqlite3.Connection) -> dict:
    return {c: b for c, b in conn.execute("SELECT code,board FROM stock_meta")}


# ============================================================ 杂项

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def shift_date(d: str, days: int) -> str:
    return (datetime.strptime(d[:10], "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


if __name__ == "__main__":
    print("数据目录:", data_home())
    print("数据库  :", db_path())
    conn = connect()
    init_schema(conn)
    print("已建表  :", [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
    print("交易日数:", len(trading_days(conn)))
