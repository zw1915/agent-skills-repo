#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股深度投研报告渲染器（stdlib only）

用法:
    python build_research_report.py \
        --input  data/688356_input.json \
        --body   data/688356_body.md \
        --meta   data/688356_meta.json \
        --out    reports/688356_深度研报.html

职责:
    1. 读取 OHLCV + 基本面快照 + 事件清单
    2. 纯本地计算技术指标（MA/MACD/RSI/KDJ/BOLL/ATR/量能倍数/回撤/乖离）
    3. 渲染自包含 HTML（内嵌 SVG 图表，零外部依赖，可直接交付或转 PDF）

设计约束:
    - 不使用 pandas / numpy / 任何第三方库（保证在任何 Python 3.8+ 环境可跑）
    - 不使用 CDN（离线可打开）
"""
import argparse
import html
import json
import math
import os
import re
import sys


# ---------------------------------------------------------------- 技术指标

def sma(vals, n):
    out = []
    for i in range(len(vals)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(vals[i + 1 - n:i + 1]) / n)
    return out


def ema(vals, n):
    out = []
    k = 2.0 / (n + 1)
    prev = None
    for v in vals:
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    ef, es = ema(closes, fast), ema(closes, slow)
    dif = [a - b for a, b in zip(ef, es)]
    dea = ema(dif, signal)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]
    return dif, dea, hist


def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(closes) - 1):
        g, l = gains[i], losses[i]
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def kdj(highs, lows, closes, n=9, m1=3, m2=3):
    k_list, d_list, j_list = [], [], []
    k_prev, d_prev = 50.0, 50.0
    for i in range(len(closes)):
        if i + 1 < n:
            k_list.append(None); d_list.append(None); j_list.append(None)
            continue
        hh = max(highs[i + 1 - n:i + 1])
        ll = min(lows[i + 1 - n:i + 1])
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
        k = (m1 - 1) / m1 * k_prev + 1.0 / m1 * rsv
        d = (m2 - 1) / m2 * d_prev + 1.0 / m2 * k
        k_list.append(k); d_list.append(d); j_list.append(3 * k - 2 * d)
        k_prev, d_prev = k, d
    return k_list, d_list, j_list


def boll(closes, n=20, k=2):
    mid = sma(closes, n)
    up, low = [], []
    for i in range(len(closes)):
        if mid[i] is None:
            up.append(None); low.append(None); continue
        seg = closes[i + 1 - n:i + 1]
        mu = mid[i]
        sd = math.sqrt(sum((x - mu) ** 2 for x in seg) / n)
        up.append(mu + k * sd); low.append(mu - k * sd)
    return up, mid, low


def atr(highs, lows, closes, n=14):
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i],
                      abs(highs[i] - closes[i - 1]),
                      abs(lows[i] - closes[i - 1])))
    out = [None] * len(tr)
    if len(tr) >= n:
        prev = sum(tr[:n]) / n
        out[n - 1] = prev
        for i in range(n, len(tr)):
            prev = (prev * (n - 1) + tr[i]) / n
            out[i] = prev
    return out


def compute_indicators(bars):
    dates = [b[0] for b in bars]
    o = [float(b[1]) for b in bars]
    h = [float(b[2]) for b in bars]
    l = [float(b[3]) for b in bars]
    c = [float(b[4]) for b in bars]
    v = [float(b[5]) for b in bars]

    dif, dea, hist = macd(c)
    up, mid, low = boll(c)
    rk, rd, rj = kdj(h, l, c)
    a14 = atr(h, l, c)
    v5, v20, v60 = sma(v, 5), sma(v, 20), sma(v, 60)

    ind = {
        "date": dates, "open": o, "high": h, "low": l, "close": c, "vol": v,
        "ma5": sma(c, 5), "ma10": sma(c, 10), "ma20": sma(c, 20), "ma60": sma(c, 60),
        "dif": dif, "dea": dea, "hist": hist,
        "rsi": rsi(c), "kdj_k": rk, "kdj_d": rd, "kdj_j": rj,
        "boll_up": up, "boll_mid": mid, "boll_low": low,
        "atr": a14, "vma5": v5, "vma20": v20, "vma60": v60,
    }

    i = len(c) - 1
    last = c[i]

    def ret(n):
        return None if i - n < 0 else (last / c[i - n] - 1) * 100

    n20_h = max(h[i - 19:i + 1]); n20_l = min(l[i - 19:i + 1])
    n60_h = max(h[i - 59:i + 1]); n60_l = min(l[i - 59:i + 1])
    window_h = max(h); window_l = min(l)
    hi_at = dates[h.index(window_h)]; lo_at = dates[l.index(window_l)]

    ma_now = {k: (ind[k][i] if ind[k][i] is not None else None)
              for k in ("ma5", "ma10", "ma20", "ma60")}

    # 斐波那契回撤：以样本区间高低点为基准，价位 = 高点 - (高点-低点) × 比例
    # 0.382 = 浅回撤（反弹阻力）；0.618 = 深回撤（结构生命线）
    span = window_h - window_l
    fib = {("f%.3f" % r): (window_h - span * r)
           for r in (0.236, 0.382, 0.5, 0.618, 0.786)}

    summary = {
        "last_close": last,
        "last_date": dates[i],
        "prev_close": c[i - 1],
        "chg_pct": (last / c[i - 1] - 1) * 100,
        "ret5": ret(5), "ret10": ret(10), "ret20": ret(20), "ret60": ret(60),
        "high_20": n20_h, "low_20": n20_l,
        "high_60": n60_h, "low_60": n60_l,
        "window_high": window_h, "window_high_date": hi_at,
        "window_low": window_l, "window_low_date": lo_at,
        "drawdown_from_high": (last / window_h - 1) * 100,
        "rally_from_low": (last / window_l - 1) * 100,
        "ma": ma_now,
        "bias": {k: ((last / v - 1) * 100 if v else None) for k, v in ma_now.items()},
        "rsi14": rsi(c)[i],
        "kdj_j": rj[i],
        "macd": {"dif": dif[i], "dea": dea[i], "hist": hist[i]},
        "atr14": a14[i],
        "atr_pct": (a14[i] / last * 100) if a14[i] else None,
        "boll": {"up": up[i], "mid": mid[i], "low": low[i]},
        "fib": fib,
        "vol": v[i],
        "vol_vs_prev": v[i] / v[i - 1] if v[i - 1] else None,
        "vol_vs_vma5": v[i] / v5[i] if v5[i] else None,
        "vol_vs_vma20": v[i] / v20[i] if v20[i] else None,
        "vol_vs_vma60": v[i] / v60[i] if v60[i] else None,
        "peak_vol": max(v),
        "peak_vol_date": dates[v.index(max(v))],
        "bars": len(c),
    }
    return ind, summary


# ---------------------------------------------------------------- SVG 图表

UP = "#d13b3b"      # A股约定：涨=红
DOWN = "#128a53"    # 跌=绿
GRAY = "#8a8f99"


def _fmt(v, nd=2):
    if v is None:
        return "—"
    return f"{v:.{nd}f}"


def build_price_svg(ind, take=90, width=1180, ph=430, vh=130):
    """返回 (svg_str)。上半=蜡烛+均线，下半=成交量。"""
    n = len(ind["date"])
    s = max(0, n - take)
    idx = list(range(s, n))
    dates = [ind["date"][i] for i in idx]

    pad_l, pad_r, pad_t = 58, 16, 14
    body_w_total = width - pad_l - pad_r
    n0 = len(idx)
    slot = body_w_total / n0
    bw = max(1.6, slot * 0.62)

    lo = min(ind["low"][i] for i in idx)
    hi = max(ind["high"][i] for i in idx)
    for k in ("ma5", "ma20", "ma60"):
        sub = [ind[k][i] for i in idx if ind[k][i] is not None]
        if sub:
            lo = min(lo, min(sub)); hi = max(hi, max(sub))
    span = (hi - lo) or 1.0
    lo -= span * 0.06; hi += span * 0.06
    span = hi - lo

    P_TOT = ph + vh
    price_h = ph - pad_t - 22          # 价格区绘图高度
    vol_top = ph + 16
    vol_h = vh - 30

    def py(v):
        return pad_t + (hi - v) / span * price_h

    def vx(pos):
        return pad_l + slot * (pos + 0.5)

    maxv = max(ind["vol"][i] for i in idx) or 1.0

    def vy(v):
        return vol_top + vol_h - v / maxv * vol_h

    o_parts = [f'<svg viewBox="0 0 {width} {P_TOT}" xmlns="http://www.w3.org/2000/svg" '
               f'font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">']
    o_parts.append(f'<rect x="0" y="0" width="{width}" height="{P_TOT}" fill="#ffffff"/>')

    # 网格 + Y轴
    steps = 6
    for k in range(steps + 1):
        val = lo + span * k / steps
        y = py(val)
        o_parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
                       f'stroke="#eceef2" stroke-width="1"/>')
        o_parts.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" '
                       f'font-size="11" fill="{GRAY}">{val:.1f}</text>')

    # X轴标签（等距取样）
    step_lbl = max(1, n0 // 9)
    for p, i in enumerate(idx):
        if p % step_lbl == 0 or p == n0 - 1:
            o_parts.append(f'<text x="{vx(p):.1f}" y="{pad_t+price_h+16}" text-anchor="middle" '
                           f'font-size="10.5" fill="{GRAY}">{dates[p][4:6]}-{dates[p][6:8]}</text>')

    # 成交量
    for p, i in enumerate(idx):
        v = ind["vol"][i]
        up = ind["close"][i] >= ind["open"][i]
        col = UP if up else DOWN
        y0 = vy(v)
        o_parts.append(f'<rect x="{vx(p)-bw/2:.2f}" y="{y0:.2f}" width="{bw:.2f}" '
                       f'height="{max(0.6, vol_top+vol_h-y0):.2f}" fill="{col}" opacity="0.42"/>')
    o_parts.append(f'<line x1="{pad_l}" y1="{vol_top+vol_h:.1f}" x2="{width-pad_r}" '
                   f'y2="{vol_top+vol_h:.1f}" stroke="#d7dae0"/>')
    o_parts.append(f'<text x="{pad_l-8}" y="{vol_top+14}" text-anchor="end" font-size="10.5" '
                   f'fill="{GRAY}">量(手)</text>')

    # 蜡烛
    for p, i in enumerate(idx):
        o_, h_, l_, c_ = ind["open"][i], ind["high"][i], ind["low"][i], ind["close"][i]
        up = c_ >= o_
        col = UP if up else DOWN
        x = vx(p)
        o_parts.append(f'<line x1="{x:.2f}" y1="{py(h_):.2f}" x2="{x:.2f}" y2="{py(l_):.2f}" '
                       f'stroke="{col}" stroke-width="1"/>')
        ytop, ybot = py(max(o_, c_)), py(min(o_, c_))
        hgt = max(1.0, ybot - ytop)
        if up:
            o_parts.append(f'<rect x="{x-bw/2:.2f}" y="{ytop:.2f}" width="{bw:.2f}" '
                           f'height="{hgt:.2f}" fill="#ffffff" stroke="{col}" stroke-width="1"/>')
        else:
            o_parts.append(f'<rect x="{x-bw/2:.2f}" y="{ytop:.2f}" width="{bw:.2f}" '
                           f'height="{hgt:.2f}" fill="{col}"/>')

    # 均线
    ma_conf = [("ma5", "#f0a02a", 1.6), ("ma20", "#3a7bd5", 1.6), ("ma60", "#8e5fd6", 1.6)]
    for key, col, wdt in ma_conf:
        pts = [(vx(p), py(ind[key][i])) for p, i in enumerate(idx) if ind[key][i] is not None]
        if len(pts) < 2:
            continue
        d = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(pts))
        o_parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{wdt}" '
                       f'stroke-linejoin="round" opacity="0.95"/>')

    # 图例
    lx = pad_l + 6
    for key, col, wdt in ma_conf:
        nm = {"ma5": "MA5", "ma20": "MA20", "ma60": "MA60"}[key]
        o_parts.append(f'<line x1="{lx}" y1="{pad_t+8}" x2="{lx+16}" y2="{pad_t+8}" '
                       f'stroke="{col}" stroke-width="{wdt}"/>')
        o_parts.append(f'<text x="{lx+20}" y="{pad_t+12}" font-size="11" fill="#5b6472">{nm}</text>')
        lx += 58

    o_parts.append("</svg>")
    return "".join(o_parts)


def build_macd_svg(ind, take=90, width=1180, mh=170):
    n = len(ind["date"])
    s = max(0, n - take)
    idx = list(range(s, n))
    pad_l, pad_r, pad_t = 58, 16, 16
    body_w = width - pad_l - pad_r
    n0 = len(idx)
    slot = body_w / n0
    bw = max(1.6, slot * 0.6)

    vals = [ind["hist"][i] for i in idx] + [ind["dif"][i] for i in idx] + [ind["dea"][i] for i in idx]
    hi, lo = max(vals), min(vals)
    span = (hi - lo) or 1.0
    hi += span * 0.12; lo -= span * 0.12
    span = hi - lo
    plot_h = mh - pad_t - 22
    zero = pad_t + (hi - 0) / span * plot_h

    p = [f'<svg viewBox="0 0 {width} {mh}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">']
    p.append(f'<rect width="{width}" height="{mh}" fill="#ffffff"/>')
    p.append(f'<line x1="{pad_l}" y1="{zero:.1f}" x2="{width-pad_r}" y2="{zero:.1f}" '
             f'stroke="#c8ccd4" stroke-dasharray="3,3"/>')
    for i2, i in enumerate(idx):
        x = pad_l + slot * (i2 + 0.5)
        hv = ind["hist"][i]
        y0 = pad_t + (hi - hv) / span * plot_h
        yz = pad_t + (hi - 0) / span * plot_h
        ytop, hh = (y0, abs(yz - y0)) if hv >= 0 else (yz, abs(y0 - yz))
        p.append(f'<rect x="{x-bw/2:.2f}" y="{ytop:.2f}" width="{bw:.2f}" height="{max(0.6,hh):.2f}" '
                 f'fill="{UP if hv>=0 else DOWN}" opacity="0.55"/>')

    def path(key, col):
        pts = [(pad_l + slot * (k + 0.5), pad_t + (hi - ind[key][i]) / span * plot_h)
               for k, i in enumerate(idx)]
        return " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(pts))

    p.append(f'<path d="{path("dif","#f0a02a")}" fill="none" stroke="#f0a02a" stroke-width="1.6"/>')
    p.append(f'<path d="{path("dea","#3a7bd5")}" fill="none" stroke="#3a7bd5" stroke-width="1.6"/>')
    p.append(f'<text x="{pad_l+4}" y="{pad_t+12}" font-size="11" fill="#5b6472">'
             f'MACD(12,26,9)　<span fill="#f0a02a">DIF</span>　<span fill="#3a7bd5">DEA</span></text>')
    p.append("</svg>")
    return "".join(p).replace("<span fill=", "<tspan fill=").replace("</span>", "</tspan>")


# ---------------------------------------------------------------- Markdown 解析

def md_inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'`(.+?)`', r'<code>\1</code>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', t)
    return t


def md_to_html(text):
    """支持: #/##/### 标题、段落、无序/有序列表、表格、分隔线、引用块。"""
    lines = text.split("\n")
    out, i = [], 0
    para = []

    def flush():
        if para:
            out.append("<p>" + md_inline(" ".join(para).strip()) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i].rstrip()
        st = ln.strip()

        if not st:
            flush(); i += 1; continue

        if st.startswith("---") and set(st) <= set("- "):
            flush(); out.append("<hr/>"); i += 1; continue

        m = re.match(r'^(#{1,4})\s+(.*)$', st)
        if m:
            flush()
            lv = min(len(m.group(1)) + 1, 4)
            out.append(f'<h{lv}>{md_inline(m.group(2))}</h{lv}>')
            i += 1; continue

        if st.startswith("|") and i + 1 < len(lines) and re.match(r'^\|[\s:\-\|]+\|$', lines[i + 1].strip()):
            flush()
            head = [c.strip() for c in st.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{md_inline(c)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>"
                          for r in rows)
            out.append(f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead>'
                       f'<tbody>{trs}</tbody></table></div>')
            continue

        if st.startswith(">"):
            flush()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            out.append(f'<blockquote>{md_inline(" ".join(buf))}</blockquote>')
            continue

        if re.match(r'^[-*]\s+', st):
            flush(); items = []
            while i < len(lines) and re.match(r'^[-*]\s+', lines[i].strip()):
                items.append(md_inline(re.sub(r'^[-*]\s+', '', lines[i].strip())))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue

        if re.match(r'^\d+[.)]\s+', st):
            flush(); items = []
            while i < len(lines) and re.match(r'^\d+[.)]\s+', lines[i].strip()):
                items.append(md_inline(re.sub(r'^\d+[.)]\s+', '', lines[i].strip())))
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue

        para.append(st); i += 1

    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- HTML 组装

CSS = """
:root{
  --up:#d13b3b; --down:#128a53; --ink:#1b1f27; --sub:#5b6472; --line:#e4e7ec;
  --bg:#f5f6f8; --card:#ffffff; --accent:#1f4e8c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  line-height:1.75;font-size:15px;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 72px}
.hero{background:linear-gradient(135deg,#12233d 0%,#1f4e8c 100%);color:#fff;
  border-radius:14px;padding:26px 30px;margin-bottom:20px}
.hero .tag{display:inline-block;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.28);
  padding:2px 10px;border-radius:999px;font-size:12px;letter-spacing:.5px}
.hero h1{margin:10px 0 6px;font-size:28px;letter-spacing:.5px}
.hero .sub{opacity:.86;font-size:13.5px}
.hero .pxline{margin-top:16px;display:flex;flex-wrap:wrap;gap:22px;align-items:baseline}
.hero .px{font-size:34px;font-weight:700;letter-spacing:.5px}
.hero .px small{font-size:15px;font-weight:500;opacity:.85;margin-left:8px}
.up{color:var(--up)} .down{color:var(--down)}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin:18px 0 22px}
.kpi .c{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:13px 15px}
.kpi .l{font-size:12px;color:var(--sub);letter-spacing:.3px}
.kpi .v{font-size:19px;font-weight:650;margin-top:3px;letter-spacing:.3px}
.kpi .n{font-size:11.5px;color:#8a8f99;margin-top:2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px 26px;
  margin-bottom:18px}
.card h2{font-size:20px;margin:0 0 4px;padding-bottom:10px;border-bottom:2px solid var(--line)}
.card h3{font-size:16px;margin:20px 0 6px;color:var(--accent)}
.card h4{font-size:14.5px;margin:16px 0 4px;color:#3c4657}
.card p{margin:9px 0}
.card ul,.card ol{margin:9px 0;padding-left:24px}
.card li{margin:5px 0}
blockquote{margin:12px 0;padding:11px 16px;background:#fbf9f2;border-left:4px solid #e2b53c;
  border-radius:0 8px 8px 0;color:#4a4030;font-size:14.5px}
code{background:#f0f2f5;padding:1px 6px;border-radius:4px;font-size:13px;
  font-family:"SF Mono",Consolas,monospace}
hr{border:0;border-top:1px solid var(--line);margin:20px 0}
.tablewrap{overflow-x:auto;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
th{background:#f2f4f7;font-weight:650;color:#2c3444;white-space:nowrap}
tbody tr:nth-child(even){background:#fafbfc}
.chart{margin:6px 0 2px}
.chart svg{width:100%;height:auto;display:block}
.legend{font-size:12px;color:var(--sub);margin-top:6px}
.verdict{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 4px}
.vd{flex:1 1 210px;border-radius:11px;padding:14px 16px;border:1px solid var(--line);background:#fff}
.vd .t{font-size:12.5px;color:var(--sub)}
.vd .s{font-size:17px;font-weight:700;margin-top:3px}
.bar{height:7px;border-radius:4px;background:#eceff3;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;border-radius:4px}
.foot{margin-top:26px;padding:16px 20px;background:#fff;border:1px solid var(--line);
  border-radius:11px;font-size:12.5px;color:var(--sub)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:860px){.grid2{grid-template-columns:1fr}}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}
  .card{break-inside:avoid;border-radius:0;border:0;border-top:1px solid #ddd}}
"""


def pct_cls(v):
    return "up" if (v or 0) >= 0 else "down"


def render(data, ind, summ, body_md, meta, out_path):
    snap = data.get("snapshot", {})
    fund = data.get("fundamentals", {})
    name, code = data.get("name"), data.get("code")

    verdicts = meta.get("verdicts", [])
    score = meta.get("score", None)

    hero = []
    hero.append(f'<div class="hero">')
    hero.append(f'<span class="tag">{html.escape(meta.get("badge","深度个股研究"))}</span>')
    hero.append(f'<h1>{html.escape(name)}　<span style="opacity:.7;font-weight:400">'
                f'{html.escape(code)}</span></h1>')
    hero.append(f'<div class="sub">数据基准日 {html.escape(str(snap.get("数据日期","—")))}　·　'
                f'{html.escape(str(meta.get("market","—")))}　·　'
                f'样本区间 {ind["date"][0]} ~ {ind["date"][-1]}（{summ["bars"]}根日K，前复权）</div>')
    chg = summ["chg_pct"]
    hero.append('<div class="pxline">')
    hero.append(f'<span class="px {pct_cls(chg)}">{summ["last_close"]:.2f}'
                f'<small>{chg:+.2f}%</small></span>')
    hero.append(f'<span>换手 <b>{html.escape(str(snap.get("换手率","—")))}</b></span>')
    hero.append(f'<span>成交额 <b>{snap.get("成交额_元",0)/1e8:.2f}亿</b></span>')
    hero.append(f'<span>总市值 <b>{snap.get("总市值_元",0)/1e8:.2f}亿</b></span>')
    hero.append(f'<span>TTM-PE <b>{_fmt(snap.get("TTM市盈率"))}</b></span>')
    hero.append(f'<span>PB <b>{_fmt(snap.get("PB"))}</b></span>')
    hero.append('</div></div>')

    # KPI
    kpis = [
        ("近5日", f'{summ["ret5"]:+.2f}%' if summ["ret5"] is not None else "—", "短线动能"),
        ("近20日", f'{summ["ret20"]:+.2f}%' if summ["ret20"] is not None else "—", "中期动量"),
        ("近60日", f'{summ["ret60"]:+.2f}%' if summ["ret60"] is not None else "—", "波段趋势"),
        ("距区间高点", f'{summ["drawdown_from_high"]:+.1f}%', f'高点 {summ["window_high_date"]}'),
        ("距区间低点", f'{summ["rally_from_low"]:+.1f}%', f'低点 {summ["window_low_date"]}'),
        ("RSI(14)", f'{summ["rsi14"]:.1f}' if summ["rsi14"] else "—", "超买>70 / 超卖<30"),
        ("ATR(14)", f'{summ["atr14"]:.2f}', f'波动率 {_fmt(summ["atr_pct"],1)}%'),
        ("量能 / MA20", f'{summ["vol_vs_vma20"]:.2f}×' if summ["vol_vs_vma20"] else "—", "放量倍数"),
    ]
    k = ['<div class="kpi">']
    for l, v, n in kpis:
        cls = ""
        if l.startswith(("近", "距")) and v not in ("—",):
            cls = pct_cls(float(v.replace("%", "").replace("×", "")) if v.endswith(("%", "×")) else 0)
        k.append(f'<div class="c"><div class="l">{l}</div>'
                 f'<div class="v {cls}">{v}</div><div class="n">{n}</div></div>')
    k.append("</div>")

    # 结论卡
    vhtml = []
    if verdicts:
        vhtml.append('<div class="verdict">')
        for v in verdicts:
            col = v.get("color", "#5b6472")
            vhtml.append(f'<div class="vd"><div class="t">{html.escape(v.get("label",""))}</div>'
                         f'<div class="s" style="color:{col}">{html.escape(v.get("value",""))}</div>'
                         f'<div style="font-size:12.5px;color:#7a8290;margin-top:3px">'
                         f'{html.escape(v.get("note",""))}</div></div>')
        vhtml.append("</div>")
    if score:
        sv = score.get("value", 0); mx = score.get("max", 100)
        ratio = max(0, min(100, sv / mx * 100))
        col = UP if ratio >= 60 else ("#e2a03a" if ratio >= 40 else DOWN)
        vhtml.append(f'<div style="margin:12px 0 0"><div style="font-size:12.5px;color:#5b6472">'
                     f'{html.escape(score.get("label","综合评分"))}　'
                     f'<b style="color:{col}">{sv}</b> / {mx}</div>'
                     f'<div class="bar"><i style="width:{ratio:.1f}%;background:{col}"></i></div></div>')

    price_svg = build_price_svg(ind, take=meta.get("chart_bars", 90))
    macd_svg = build_macd_svg(ind, take=meta.get("chart_bars", 90))

    # 技术面数据卡（自动计算，不与正文重复叙事）
    ma = summ["ma"]; bias = summ["bias"]
    tech_rows = "".join(
        f'<tr><td>{nm}</td><td>{_fmt(ma[k])}</td>'
        f'<td class="{pct_cls(bias[k])}">{bias[k]:+.2f}%</td></tr>'
        for k, nm in [("ma5", "MA5"), ("ma10", "MA10"), ("ma20", "MA20"), ("ma60", "MA60")]
        if ma.get(k) is not None)
    tech = f"""
<div class="card">
  <h2>技术面量化读数</h2>
  <div class="grid2">
    <div>
      <h3>均线体系与乖离</h3>
      <div class="tablewrap"><table><thead><tr><th>均线</th><th>数值</th><th>乖离率</th></tr></thead>
      <tbody>{tech_rows}</tbody></table></div>
      <h3>动量与波动</h3>
      <div class="tablewrap"><table>
        <tbody>
          <tr><td>MACD (DIF / DEA / 柱)</td><td>{_fmt(summ["macd"]["dif"])} / {_fmt(summ["macd"]["dea"])} / {_fmt(summ["macd"]["hist"])}</td></tr>
          <tr><td>KDJ (J值)</td><td>{_fmt(summ["kdj_j"])}</td></tr>
          <tr><td>BOLL (上 / 中 / 下)</td><td>{_fmt(summ["boll"]["up"])} / {_fmt(summ["boll"]["mid"])} / {_fmt(summ["boll"]["low"])}</td></tr>
          <tr><td>20日区间</td><td>{_fmt(summ["low_20"])} ~ {_fmt(summ["high_20"])}</td></tr>
          <tr><td>60日区间</td><td>{_fmt(summ["low_60"])} ~ {_fmt(summ["high_60"])}</td></tr>
        </tbody>
      </table></div>
    </div>
    <div>
      <h3>量能与筹码</h3>
      <div class="tablewrap"><table>
        <tbody>
          <tr><td>当日成交量</td><td>{summ["vol"]:,.0f} 手</td></tr>
          <tr><td>量能 / 5日均量</td><td>{_fmt(summ["vol_vs_vma5"],2)} ×</td></tr>
          <tr><td>量能 / 20日均量</td><td>{_fmt(summ["vol_vs_vma20"],2)} ×</td></tr>
          <tr><td>量能 / 60日均量</td><td>{_fmt(summ["vol_vs_vma60"],2)} ×</td></tr>
          <tr><td>区间峰值成交</td><td>{summ["peak_vol"]:,.0f} 手 @ {summ["peak_vol_date"]}</td></tr>
          <tr><td>ATR(14) 真实波幅</td><td>{_fmt(summ["atr14"])} 元（{_fmt(summ["atr_pct"],1)}%）</td></tr>
        </tbody>
      </table></div>
    </div>
  </div>
</div>"""

    body_html = md_to_html(body_md)

    events = data.get("events", [])
    if events:
        rows = "".join(f'<tr><td>{html.escape(e.get("date",""))}</td>'
                       f'<td>{html.escape(e.get("type",""))}</td>'
                       f'<td>{html.escape(e.get("text",""))}</td></tr>' for e in events)
        ev_card = f"""
<div class="card">
  <h2>关键事件时间线</h2>
  <div class="tablewrap"><table><thead><tr><th>日期</th><th>类型</th><th>事项</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
</div>"""
    else:
        ev_card = ""

    disclaimer = meta.get("disclaimer",
        "本报告由量化数据流水线自动生成，数据来源为公开行情与公告资讯，所有数值均可回溯核验。"
        "报告仅为研究讨论，不构成任何投资建议；市场有风险，决策请自负。")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(name)} {html.escape(code)} · 深度投研报告</title>
<style>{CSS}</style></head>
<body><div class="wrap">
{''.join(hero)}
{''.join(k)}
<div class="card">{''.join(vhtml)}</div>
<div class="card">
  <h2>价格结构与量能</h2>
  <div class="chart">{price_svg}</div>
  <div class="legend">上半：日K + MA5/MA20/MA60　|　下半：成交量（手）。红涨绿跌，遵循A股习惯。</div>
  <div class="chart" style="margin-top:10px">{macd_svg}</div>
</div>
{tech}
{ev_card}
<div class="card">
{body_html}
</div>
<div class="foot">{html.escape(disclaimer)}</div>
</div></body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="A股深度投研报告渲染器")
    ap.add_argument("--input", required=True, help="OHLCV + 基本面 + 事件 JSON")
    ap.add_argument("--body", required=True, help="六段式正文 Markdown")
    ap.add_argument("--meta", required=True, help="元信息 JSON（结论/评分/免责）")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    a = ap.parse_args()

    with open(a.input, encoding="utf-8") as f:
        data = json.load(f)
    with open(a.body, encoding="utf-8") as f:
        body = f.read()
    meta = {}
    if os.path.exists(a.meta):
        with open(a.meta, encoding="utf-8") as f:
            meta = json.load(f)

    bars = data["bars"]
    if len(bars) < 65:
        print("[warn] K线样本少于65根，MA60/ATR 等指标可能不完整", file=sys.stderr)

    ind, summ = compute_indicators(bars)
    p = render(data, ind, summ, body, meta, a.out)

    print("=" * 62)
    print(f"标的      : {data.get('name')} ({data.get('code')})")
    print(f"基准日    : {summ['last_date']}   收盘 {summ['last_close']:.2f} ({summ['chg_pct']:+.2f}%)")
    print(f"MA5/10/20/60 : " + " / ".join(
        _fmt(summ['ma'][k]) for k in ('ma5', 'ma10', 'ma20', 'ma60')))
    print(f"乖离      : " + " / ".join(
        f"{summ['bias'][k]:+.2f}%" if summ['bias'][k] is not None else "—"
        for k in ('ma5', 'ma10', 'ma20', 'ma60')))
    print(f"MACD      : DIF {_fmt(summ['macd']['dif'])} / DEA {_fmt(summ['macd']['dea'])} "
          f"/ 柱 {_fmt(summ['macd']['hist'])}")
    print(f"RSI14     : {_fmt(summ['rsi14'],1)}    KDJ-J {_fmt(summ['kdj_j'],1)}")
    print(f"ATR14     : {_fmt(summ['atr14'])} ({_fmt(summ['atr_pct'],1)}%)")
    print(f"量能倍数  : vs MA5 {_fmt(summ['vol_vs_vma5'],2)}x / vs MA20 {_fmt(summ['vol_vs_vma20'],2)}x "
          f"/ vs MA60 {_fmt(summ['vol_vs_vma60'],2)}x")
    print(f"BOLL      : 上 {_fmt(summ['boll']['up'])} / 中 {_fmt(summ['boll']['mid'])} "
          f"/ 下 {_fmt(summ['boll']['low'])}")
    print(f"20日区间  : {_fmt(summ['low_20'])} ~ {_fmt(summ['high_20'])}"
          f"    60日区间: {_fmt(summ['low_60'])} ~ {_fmt(summ['high_60'])}")
    print(f"斐波回撤  : " + " / ".join(
        f"{k[1:]}→{_fmt(v)}" for k, v in sorted(summ['fib'].items())))
    print(f"区间位置  : 高点 {summ['window_high']:.2f}({summ['window_high_date']}) "
          f"低点 {summ['window_low']:.2f}({summ['window_low_date']})")
    print(f"回撤/反弹 : {summ['drawdown_from_high']:+.1f}% / {summ['rally_from_low']:+.1f}%")
    print("=" * 62)
    print(f"✅ 报告已生成 → {os.path.abspath(p)}")


if __name__ == "__main__":
    main()
