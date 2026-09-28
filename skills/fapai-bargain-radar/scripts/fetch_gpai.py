#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公拍网(gpai.net) 司法拍卖房源抓取（已实测可用，但**不按城市过滤**）。

为什么单独做这个源：公拍网是服务端渲染，Python 可直连；而淘宝/法院网/京东
的城市筛选是前端 JS 或 WAF 拦截，必须真实浏览器才能按城市过滤。

⚠️ 重要实测结论（务必照此告知用户，不要夸大）：
  - 公拍网本质是**上海/华东平台**；其搜索接口 `q=关键词` 实测**不会按城市过滤**，
    返回的是全国混合流（以上海/华东为主，夹杂其他省份）。
  - 因此本脚本拉回的是「公拍网全站 ≤ 价格 的标的」，并非某城市专属。
  - 真正按城市（如长沙/衡阳）拿全量，仍要靠淘宝/法院网/京东 + 真实浏览器，
    或用户手动筛选后把清单贴回，再用 score_listing.py 批量排名。
  - 本脚本的价值：证明「至少一个源可脚本直连」，并提供一个可继续打磨的解析骨架。

原理（已验证）：
  1. 先 GET 首页种下会话 cookie；
  2. 再 POST 到搜索接口 https://s.gpai.net/Sf/Search.do （表单字段 q=关键词）；
  3. 跟随 307 重定向（同会话 jar）拿到结果页；
  4. 解析列表卡片：详情链接 + 标题 + 起拍价 + 评估价/市场价 + 法院 + 时间。

用法：
  python fetch_gpai.py --keyword 住宅 --max-price 30
  python fetch_gpai.py --max-price 30 --out gpai.json

说明：
  --keyword 仅作站内搜索词，不会保证城市过滤；结果需用户按法院/地区人工筛。
  价格单位统一折算为「万元」输出。
"""
import argparse
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def _open(op, url, data=None, ref=None):
    hd = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if ref:
        hd["Referer"] = ref
    if data is not None:
        hd["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=hd)
    try:
        with op.open(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa
        # 307/302 重定向有时 urllib 处理不顺，退而手动跟随
        if isinstance(e, urllib.error.HTTPError) and e.code in (301, 302, 303, 307):
            loc = e.headers.get("Location")
            if loc:
                nxt = loc if loc.startswith("http") else urllib.parse.urljoin(url, loc)
                return _open(op, nxt, ref=url)
        raise


def _abs_url(href: str) -> str:
    h = href.strip()
    # 去掉结果页里偶发的重复域名前缀
    h = re.sub(r"^/+(?:www\.)?gpai\.net", "", h)
    if h.startswith("http"):
        return h
    if h.startswith("//"):
        return "https:" + h
    if h.startswith("/"):
        return "https://www.gpai.net" + h
    return "https://www.gpai.net/" + h


def search(keyword: str):
    jar = CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=CTX),
    )
    _open(op, "https://www.gpai.net", ref=None)  # 种 cookie
    data = urllib.parse.urlencode({"q": keyword}).encode("utf-8")
    html = _open(op, "https://s.gpai.net/Sf/Search.do", data=data, ref="https://www.gpai.net")
    return html


def _clean(txt):
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def parse(html, max_price=None):
    items = []
    seen = set()
    for m in re.finditer(r'href="([^"]*(?:item|content|/p/|detail)[^"]*)"', html, re.I):
        href = m.group(1)
        start = max(0, m.start() - 500)
        end = min(len(html), m.end() + 500)
        block = html[start:end]
        title = _clean(block)
        title = re.sub(r"^\s*.*?(?=司法|拍卖|[一-龥]{4})", "", title)[:80] or title[:80]
        sp = re.search(r'起拍价[：:\s]*[^\d]*?([\d,\.]+)\s*(?:万|元)?', block)
        ap = re.search(r'(?:评估价|市场价|参考价)[：:\s]*[^\d]*?([\d,\.]+)\s*(?:万|元)?', block)
        court = re.search(r'([\u4e00-\u9fa5]{2,}(?:法院|公证处|资产|公司))', block)
        tm = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', block)

        def to_wan(s):
            if not s:
                return None
            v = float(s.replace(",", ""))
            return round(v / 10000.0, 2) if v >= 10000 else round(v, 2)

        sp_w = to_wan(sp.group(1)) if sp else None
        ap_w = to_wan(ap.group(1)) if ap else None
        if sp_w is None:
            continue
        if max_price and sp_w > max_price:
            continue
        key = (title, sp_w)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "title": title,
            "url": _abs_url(href),
            "starting": sp_w,
            "appraisal": ap_w,
            "court": court.group(1) if court else "",
            "time": tm.group(1) if tm else "",
        })
    return items


def main():
    p = argparse.ArgumentParser(description="公拍网司法拍卖房源抓取（已实测，不按城市过滤）")
    p.add_argument("--keyword", default="", help="站内搜索词（不会保证城市过滤）")
    p.add_argument("--max-price", type=float, default=None, help="起拍价上限（万元）")
    p.add_argument("--out", help="导出 JSON 路径")
    args = p.parse_args()

    print("[提示] 公拍网 q=搜索实测不按城市过滤，返回全国混合流（上海/华东为主）。"
          "结果请按法院/地区人工筛选，不要当作某城市专属源。", file=sys.stderr)

    try:
        html = search(args.keyword)
    except Exception as e:  # noqa
        print(f"[错误] 检索失败: {e}", file=sys.stderr)
        sys.exit(1)
    items = parse(html, max_price=args.max_price)
    print(f"[检索] 解析到 {len(items)} 套 (≤{args.max_price}万)" if args.max_price
          else f"[检索] 解析到 {len(items)} 套", file=sys.stderr)

    print(json.dumps(items, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
        print(f"[已导出] {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
