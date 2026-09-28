#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法拍房捡漏评分器 v2（批量 + 排名 + 价格单位自适应）。

v2 改进：
  - 价格单位自适应：传入值 >= 10000 视为「元」，自动折算为「万元」。
  - 评估价缺失时以 market(市场价) 兜底折价率，并标注。
  - 新增批量模式：--batch 读取 JSON 数组或 CSV，逐套评分后按分降序排名，
    支持 --top N 截取前 N 套、--out 导出 Markdown 报告。
  - 单套模式保持向后兼容。

用法：
  # 单套
  python score_listing.py --starting 280 --appraisal 400 --tax 各付 --occupancy 空置
  python score_listing.py --starting 269400 --appraisal 396000   # 元/万 自动识别
  python score_listing.py --json '{"starting":280,"appraisal":400,"occupancy":"不清场","land":"划拨"}'

  # 批量（推荐）：listings.json = [{title,city,starting,appraisal,market,tax,occupancy,lease,land,loan,usage}, ...]
  python score_listing.py --batch listings.json --top 10 --out report.md
  # 也支持 CSV（表头含中文或英文字段名均可）
  python score_listing.py --batch listings.csv --top 10
"""
import argparse
import csv
import json
import os
import re
import sys

# 评级阈值（0-100）
GRADE_STRONG = 75   # 强烈捡漏
GRADE_GOOD = 60     # 较优
GRADE_CAUTION = 45  # 谨慎


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "y", "是")


def _norm_money(v):
    """价格单位自适应：None 原样返回；>=10000 视为元并折算为万元。"""
    if v is None or v == "":
        return None
    f = float(v)
    if abs(f) >= 10000:      # 判定为「元」
        return f / 10000.0
    return f                  # 否则视为「万元」


def score(data: dict) -> dict:
    starting = _norm_money(data.get("starting"))
    appraisal = _norm_money(data.get("appraisal"))
    market = _norm_money(data.get("market"))
    tax = str(data.get("tax", "各付")).strip()
    occupancy = str(data.get("occupancy", "空置")).strip()
    lease = _truthy(data.get("lease", False))
    land = str(data.get("land", "出让")).strip()
    loan = _truthy(data.get("loan", False))
    usage = str(data.get("usage", "住宅")).strip()

    if not starting or starting <= 0:
        return {"error": "缺少必填项或无效：起拍价(starting) 必须为正数"}

    score_val = 60  # 基线分
    flags = []

    # 折价基准：优先评估价，缺失时以市场价兜底
    base = appraisal if (appraisal and appraisal > 0) else market
    if base and base > 0:
        discount = (1 - starting / base) * 100
        if not appraisal:
            flags.append("未提供评估价，折价率以市场价近似计算（可能偏乐观）")
    else:
        discount = 0
        flags.append("缺评估价/市场价，折价率无法计算（评分不含折价加分）")

    # 折价率（核心加分项）
    if discount >= 30:
        score_val += 20
    elif discount >= 20:
        score_val += 12
    elif discount >= 10:
        score_val += 6
    elif discount >= 0:
        pass
    else:
        score_val -= 10
        flags.append("起拍价高于基准价，无折价空间")

    # 占用 / 腾退风险
    occ_penalty = {"空置": 0, "自用": -8, "出租": -15, "不清场": -30}
    score_val += occ_penalty.get(occupancy, -10)
    if occupancy == "不清场":
        flags.append("重大风险：标的声明不清场，可能无法顺利收房/入住")
    elif occupancy == "出租":
        flags.append("有占用/出租，需核实腾退安排与租约剩余期限")
    elif occupancy == "自用":
        flags.append("原业主自用，需确认交付时间与配合意愿")

    # 租约（买卖不破租赁）
    if lease:
        score_val -= 10
        flags.append("存在租约，买卖不破租赁，可能影响收房与收益")

    # 税费承担
    if tax == "买家全付":
        score_val -= 12
        flags.append("税费由买受人全额承担，实际成本上升")
    else:
        flags.append("税费各付（较优）")

    # 土地性质
    if land == "划拨":
        score_val -= 10
        flags.append("划拨土地，过户时可能需补缴土地出让金")
    else:
        flags.append("出让土地（权属相对清晰）")

    # 房屋用途
    if usage == "商办":
        score_val -= 8
        flags.append("商办类流动性差、交易税费高")
    else:
        flags.append("住宅类（流动性较好）")

    # 法拍贷
    if loan:
        score_val += 5
    else:
        flags.append("不可法拍贷，需自有资金/全款参拍")

    score_val = max(0, min(100, score_val))

    if score_val >= GRADE_STRONG:
        grade = "强烈捡漏（重点尽调后参拍）"
    elif score_val >= GRADE_GOOD:
        grade = "较优（可纳入候选）"
    elif score_val >= GRADE_CAUTION:
        grade = "谨慎（需核实重大风险）"
    else:
        grade = "建议避开"

    return {
        "title": data.get("title", ""),
        "city": data.get("city", ""),
        "starting": round(starting, 2),
        "appraisal": round(appraisal, 2) if appraisal else None,
        "market": round(market, 2) if market else None,
        "discount_pct": round(discount, 1) if base else None,
        "score": score_val,
        "grade": grade,
        "flags": flags,
    }


def _render_one(r: dict):
    if "error" in r:
        print("错误：" + r["error"])
        return
    print("=" * 46)
    print("法拍房捡漏评分报告")
    print("=" * 46)
    if r.get("title"):
        print(f"标的      : {r['title']}")
    if r.get("city"):
        print(f"城市      : {r['city']}")
    print(f"起拍价    : {r['starting']} 万")
    if r.get("appraisal"):
        print(f"评估价    : {r['appraisal']} 万")
    if r.get("market"):
        print(f"市场参考价: {r['market']} 万")
    if r.get("discount_pct") is not None:
        print(f"折价率    : {r['discount_pct']}%")
    print(f"捡漏评分  : {r['score']}/100")
    print(f"综合评级  : {r['grade']}")
    if r["flags"]:
        print("-" * 46)
        print("风险标记 / 备注:")
        for f in r["flags"]:
            print("  • " + f)
    print("=" * 46)
    print("JSON:" + json.dumps(r, ensure_ascii=False))


def _load_batch(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        rows = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append({k: (v if v != "" else None) for k, v in row.items()})
        return rows
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        # 允许 {"listings":[...]} 或单个对象
        if "listings" in data:
            return data["listings"]
        return [data]
    return data


# 中英文字段名映射（CSV 友好）
_FIELD_ALIASES = {
    "title": ["title", "标题", "标的", "name"],
    "city": ["city", "城市"],
    "starting": ["starting", "起拍价", "starting_price"],
    "appraisal": ["appraisal", "评估价", "appraisal_price"],
    "market": ["market", "市场价", "market_price"],
    "tax": ["tax", "税费", "税费承担"],
    "occupancy": ["occupancy", "占用", "占用情况"],
    "lease": ["lease", "租约", "租赁"],
    "land": ["land", "土地", "土地性质"],
    "loan": ["loan", "法拍贷", "贷款"],
    "usage": ["usage", "用途", "房屋用途"],
}


def _normalize_keys(row: dict):
    out = {}
    lower = {k.lower(): v for k, v in row.items()}
    for canon, aliases in _FIELD_ALIASES.items():
        for a in aliases:
            if a.lower() in lower and lower[a.lower()] not in (None, ""):
                out[canon] = lower[a.lower()]
                break
    return out


def _render_batch(rows, top=None, out=None):
    results = []
    for i, raw in enumerate(rows):
        item = _normalize_keys(raw) if isinstance(raw, dict) else {}
        r = score(item)
        if "error" in r:
            r["_src"] = raw.get("title") or raw.get("starting") or f"第{i+1}条"
            r["_err"] = r.pop("error")
        results.append(r)

    # 有评分的按分降序；解析失败的排最后
    def _key(r):
        return r.get("score", -1)
    results.sort(key=_key, reverse=True)

    n = top if top else len(results)
    picked = results[:n]

    lines = []
    lines.append("# 法拍房捡漏排名（按评分降序）\n")
    lines.append(f"共纳入 {len(results)} 套，展示前 {len(picked)} 套（评分≥{GRADE_GOOD} 视为候选）。\n")
    lines.append("| 排名 | 城市 | 标的 | 起拍价(万) | 折价率 | 评分 | 评级 | 主要风险 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for idx, r in enumerate(picked, 1):
        if "_err" in r:
            lines.append(f"| {idx} | - | {r.get('_src','?')} | - | - | - | 解析失败 | {r['_err']} |")
            continue
        top_flag = "; ".join(f for f in r["flags"] if "风险" in f or "重大" in f)[:40] or "-"
        lines.append(
            f"| {idx} | {r.get('city','-')} | {r.get('title','-')} | {r['starting']} | "
            f"{r['discount_pct'] if r.get('discount_pct') is not None else '-'}% | "
            f"{r['score']} | {r['grade']} | {top_flag} |"
        )
    lines.append("")
    lines.append("> 评级阈值：≥75 强烈捡漏 / ≥60 较优 / ≥45 谨慎 / <45 避开。折价率优先以评估价计算，评估价缺失时以市场价近似。所有判断以法院公告原文为准。")

    md = "\n".join(lines)
    print(md)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
        print(f"\n[已导出报告] {out}")
    return md


def main():
    p = argparse.ArgumentParser(description="法拍房捡漏评分器 v2（支持批量排名）")
    p.add_argument("--json", help="单套房源 JSON 字符串")
    p.add_argument("--batch", help="批量文件：JSON 数组 / {listings:[...]} / CSV")
    p.add_argument("--top", type=int, default=None, help="批量模式下仅展示前 N 套")
    p.add_argument("--out", help="批量模式下导出 Markdown 报告路径")
    # 单套字段
    p.add_argument("--starting", type=float, help="起拍价（万元或元，自动识别）")
    p.add_argument("--appraisal", type=float, help="评估价（万元或元）")
    p.add_argument("--market", type=float, help="市场参考价（万元或元），评估价缺失时兜底")
    p.add_argument("--tax", default="各付", help="税费承担: 各付 / 买家全付")
    p.add_argument("--occupancy", default="空置", help="占用: 空置/自用/出租/不清场")
    p.add_argument("--lease", default=False, help="是否租约(true/false)")
    p.add_argument("--land", default="出让", help="土地性质: 出让 / 划拨")
    p.add_argument("--loan", default=False, help="是否可法拍贷(true/false)")
    p.add_argument("--usage", default="住宅", help="用途: 住宅 / 商办")
    args = p.parse_args()

    if args.batch:
        if not os.path.exists(args.batch):
            print(f"批量文件不存在: {args.batch}")
            sys.exit(1)
        rows = _load_batch(args.batch)
        _render_batch(rows, top=args.top, out=args.out)
        return

    data = {}
    if args.json:
        try:
            data = json.loads(args.json)
        except Exception as e:  # noqa
            print("JSON 解析失败:", e)
            sys.exit(1)

    for k in ("starting", "appraisal", "market", "tax", "occupancy", "lease", "land", "loan", "usage"):
        if getattr(args, k) is not None:
            data[k] = getattr(args, k)

    # lease/loan 字符串转布尔
    if "lease" in data:
        data["lease"] = _truthy(data["lease"])
    if "loan" in data:
        data["loan"] = _truthy(data["loan"])

    _render_one(score(data))


if __name__ == "__main__":
    main()
