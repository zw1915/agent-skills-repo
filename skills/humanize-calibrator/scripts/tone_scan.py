#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tone_scan.py —— 「人味校准器」确定性文本体检脚本

对文本做与 skill 检查清单（references/checklist.md）对齐的客观统计：
黑话/万能副词/抽象名词密度、机械序号、套路连接词、句长与段落节奏、
人称与具体信息密度、网络流行语（过改预警）。

用法：
    python tone_scan.py --file draft.md
    python tone_scan.py --text "待检测的文本"
    python tone_scan.py --file draft.md --format json
    cat draft.md | python tone_scan.py

参数：
    --file PATH     输入文件（UTF-8）
    --text STR      直接传文本
    --format md|json|text   输出格式，默认 md
    --score         额外输出启发式估算分数（仅供参考）
    --top N         词频榜显示前 N 项，默认 12

退出码：0 正常；2 输入错误。
仅依赖 Python 标准库。
"""

import argparse
import json
import re
import statistics
import sys

# --------------------------------------------------------------------------
# 词表 —— 必须与 references/patterns.md 保持一致；改动请同步两处
# --------------------------------------------------------------------------

JARGON = [
    "赋能", "抓手", "闭环", "沉淀", "对齐", "颗粒度", "心智", "打法", "组合拳",
    "底层逻辑", "护城河", "生态位", "拉通", "协同", "势能", "飞轮", "落地",
    "复盘", "拉齐", "增效", "提质", "破局", "卡位", "面纱", "共振",
]

ABSTRACT_NOUNS = [
    "价值", "维度", "层面", "体系", "机制", "能力", "链路", "矩阵", "生态",
    "范式", "路径", "方法论", "模型", "框架", "策略", "举措", "要素", "指标",
]

ADVERBS = [
    "极大地", "显著地", "有效地", "充分地", "深度地", "进一步", "持续不断地",
    "不断地", "日益", "大力", "全面", "切实", "有力地", "大幅度地", "尤为",
    "更加", "愈发", "持续", "高度",
]

EMPHASIS_HYPE = [
    "非常重要", "极其关键", "至关重要", "核心中的核心", "重中之重", "意义重大",
    "前所未有的", "颠覆性的", "革命性的", "开创性的", "极具创新", "完美解决",
    "全面提升", "极大地提升",
]

SLANG_OVERFIX = [
    "家人们", "谁懂啊", "绝绝子", "yyds", "YYDS", "冲就完事了", "真的会谢",
    "栓Q", "破防", "直接封神", "咱就是说", "无语子", "宝子", "姐妹们",
    "狠狠", "拉满", "拿捏", "泪目", "呜呜", "救命",
]

# 结构 / 套路模板：名称 -> (说明, [正则])
PATTERNS = {
    "D1-1 机械序号": ("先/其/再/最后、第一第二第三等显式编号", [
        r"首先", r"其次", r"再次", r"最后", r"第一[，,、]", r"第二[，,、]",
        r"第三[，,、]", r"其一", r"其二", r"一是", r"二是", r"三是",
    ]),
    "D6-1 背景起手": ("随着…的发展／在…背景下", [
        r"随着[^。；\n]{0,20}?(发展|深入|推进|普及|兴起)",
        r"在[^。；\n]{0,15}?的?大背景下",
        r"在当今[^。；\n]{0,15}?的?(时代|社会|环境)",
        r"众所周知",
        r"近年来[，,]",
    ]),
    "D6-3 升华收尾": ("综上所述／总而言之／希望有所帮助", [
        r"综上所述", r"总而言之", r"总的来说", r"总的来说",
        r"让我们一起", r"相信在不久的将来", r"只有这样[，,]?才能",
        r"希望(对您|对你)?有所帮助", r"如有(疑问|问题)[，,]?欢迎",
    ]),
    "D6-4 提示型过渡": ("值得注意的是／需要强调的是", [
        r"值得注意的是", r"需要强调的是", r"尤其需要指出的是",
        r"不得不说的是?", r"不可否认", r"毋庸置疑",
    ]),
    "D6-6 设问自答": ("那么，X是什么？X就是…", [
        r"那么[，,][^。？\n]{0,20}?(是什么|怎么做|如何)[？?]",
        r"什么是[^。？\n]{0,12}?[？?]",
    ]),
    "D6-2 万能递进": ("不仅…而且／既…又／一方面…另一方面", [
        r"不仅[^。\n]{0,40}?(而且|还|也)",
        r"既[^。\n]{0,25}?又",
        r"一方面[^。\n]{0,60}?另一方面",
    ]),
}

PUNCT = "　 \t\r\n，。！？；：、（）()《》〈〉「」『』“”‘’\"'…—-—·,.!?;:[]{}<>/~`|\\+*&^%$#@="


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def cjk_len(s: str) -> int:
    """计长：中文字 + 拉丁字母数字串，忽略空白与标点。"""
    s = re.sub(r"[A-Za-z0-9]+", "A", s)
    return len([c for c in s if c not in PUNCT and not c.isspace()])


def count_any(text: str, words: list) -> dict:
    hits = {}
    for w in words:
        n = text.count(w)
        if n:
            hits[w] = n
    return hits


def split_sentences(text: str) -> list:
    parts = re.split(r"[。！？!?；;\n]+", text)
    return [p.strip() for p in parts if cjk_len(p.strip()) > 0]


def split_paragraphs(text: str) -> list:
    if re.search(r"\n\s*\n", text):
        chunks = re.split(r"\n\s*\n+", text)
    else:
        chunks = text.split("\n")
    return [c.strip() for c in chunks if c.strip()]


def safe_stdev(vals: list) -> float:
    return round(statistics.pstdev(vals), 2) if len(vals) > 1 else 0.0


def scan_patterns(text: str) -> dict:
    out = {}
    for name, (_desc, regexes) in PATTERNS.items():
        samples, total = [], 0
        for rx in regexes:
            for m in re.finditer(rx, text):
                total += 1
                if len(samples) < 3:
                    samples.append(m.group(0))
        if total:
            out[name] = {"count": total, "samples": samples}
    return out


# --------------------------------------------------------------------------
# 主扫描
# --------------------------------------------------------------------------

def scan(text: str, top: int = 12) -> dict:
    text = text.strip()
    total_chars = cjk_len(text)
    sents = split_sentences(text)
    paras = split_paragraphs(text)
    slens = [cjk_len(s) for s in sents]
    plens = [len(split_sentences(p)) for p in paras]

    jargon = count_any(text, JARGON)
    abstract = count_any(text, ABSTRACT_NOUNS)
    adverbs = count_any(text, ADVERBS)
    hype = count_any(text, EMPHASIS_HYPE)
    slang = count_any(text, SLANG_OVERFIX)
    patterns = scan_patterns(text)

    per1000 = lambda n: round(n * 1000 / total_chars, 2) if total_chars else 0.0

    jargon_n = sum(jargon.values())
    abstract_n = sum(abstract.values())
    adverb_n = sum(adverbs.values())
    hype_n = sum(hype.values())
    pattern_n = sum(v["count"] for v in patterns.values())
    slang_n = sum(slang.values())
    emoji_n = len(re.findall(
        "[\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF\u2600-\u27BF]", text))

    first_person_n = len(re.findall(r"我|我们|咱|本人|笔者", text))
    digits_n = len(re.findall(r"\d+(?:\.\d+)?", text))
    percent_n = len(re.findall(r"\d+(?:\.\d+)?\s*%|百分之", text))
    date_n = len(re.findall(r"\d{4}\s*年|\d{1,2}\s*月|\d{1,2}\s*日|Q[1-4]|第[一二三四]季度", text))
    proper_n = len(re.findall(r"《[^》]{1,20}》", text))

    short_ratio = round(
        sum(1 for x in slens if x <= 10) / len(slens), 3) if slens else 0.0
    para_std = safe_stdev(plens)
    sent_std = safe_stdev(slens)
    ratio = round(max(slens) / min(slens), 2) if slens and min(slens) > 0 else 0.0

    return {
        "规模": {
            "总字数": total_chars,
            "句子数": len(sents),
            "段落数": len(paras),
        },
        "节奏": {
            "句长均值": round(statistics.mean(slens), 1) if slens else 0,
            "句长标准差": sent_std,
            "最短句": min(slens) if slens else 0,
            "最长句": max(slens) if slens else 0,
            "最长最短比": ratio,
            "短句占比(≤10字)": short_ratio,
            "段落句数均值": round(statistics.mean(plens), 1) if plens else 0,
            "段落句数标准差": para_std,
        },
        "词汇": {
            "黑话命中": jargon,
            "黑话数(每千字)": per1000(jargon_n),
            "抽象名词": abstract,
            "抽象名词数(每千字)": per1000(abstract_n),
            "万能副词": adverbs,
            "万能副词数(每千字)": per1000(adverb_n),
            "形容词通胀": hype,
            "形容词通胀数(每千字)": per1000(hype_n),
        },
        "结构套路": patterns,
        "套路总数": pattern_n,
        "具体性": {
            "数字个数": digits_n,
            "百分比个数": percent_n,
            "时间表达个数": date_n,
            "书名号引用个数": proper_n,
            "具体信息数(每千字)": per1000(digits_n + date_n + proper_n),
        },
        "人称与在场感": {
            "第一人称出现次数": first_person_n,
            "第一人称(每千字)": per1000(first_person_n),
        },
        "过改预警": {
            "网络流行语": slang,
            "网络流行语数(每千字)": per1000(slang_n),
            "emoji个数": emoji_n,
        },
    }


# --------------------------------------------------------------------------
# 启发式参考分（可选，仅供对照，正式评分以 checklist 人工/模型评定为准）
# --------------------------------------------------------------------------

WEIGHTS = {"D1": 15, "D2": 18, "D3": 18, "D4": 14, "D5": 12, "D6": 13, "D7": 10}


def clamp(x, lo=0.5, hi=10.0):
    return max(lo, min(hi, x))


def sat(n: float, max_pen: float, ref: float, p: float = 1.5) -> float:
    """饱和惩罚：n 很小时近乎线性、n 很大时收敛到 max_pen，避免长文/短文评分失稳。"""
    if n <= 0 or max_pen <= 0:
        return 0.0
    x = (n / max(ref, 1e-6)) ** p
    return max_pen * x / (1.0 + x)


def heuristic_scores(m: dict) -> dict:
    L = max(m["规模"]["总字数"], 1)
    ref = lambda div, floor_: max(floor_, L / div)  # noqa: E731
    pat = m["结构套路"]

    # D1 结构机械度
    n_seq = pat.get("D1-1 机械序号", {}).get("count", 0)
    uni = 0.0
    if m["规模"]["段落数"] >= 2:
        uni = max(0.0, 1.5 - m["节奏"]["段落句数标准差"]) * 1.2
    d1 = clamp(10 - sat(n_seq, 8.5, ref(600, 1.0)) - uni)

    # D2 词汇空泛度（按信息负载加权：黑话最重，抽象名词最轻）
    v = m["词汇"]
    n_vocab = (sum(v["黑话命中"].values()) * 1.0
               + sum(v["万能副词"].values()) * 0.5
               + sum(v["抽象名词"].values()) * 0.3
               + sum(v["形容词通胀"].values()) * 1.2)
    d2 = clamp(10 - sat(n_vocab, 9.0, ref(400, 1.5)))

    # D3 细节具体度（可验证信息密度）
    info = m["具体性"]["具体信息数(每千字)"]
    xi = info / 6.0
    d3 = clamp(2.5 + 7.5 * (xi / (1 + xi)))

    # D4 立场与声音（第一人称密度，置信度低）
    fp = m["人称与在场感"]["第一人称(每千字)"]
    xf = fp / 8.0
    d4 = clamp(2.5 + 6.5 * (xf / (1 + xf)))

    # D5 节奏起伏度
    sd = m["节奏"]["句长标准差"]
    ratio = m["节奏"]["最长最短比"]
    short_r = m["节奏"]["短句占比(≤10字)"]
    d5 = clamp(1.5 + sd * 0.35 + max(0.0, ratio - 1.5) * 0.8 + short_r * 5)

    # D6 逻辑套壳度
    shell = sum(vv["count"] for kk, vv in pat.items() if kk != "D1-1 机械序号")
    d6 = clamp(10 - sat(shell, 9.0, ref(500, 1.0)))

    # D7 信息增量度（可自动测量的部分有限，置信度低）
    n_waffle = sum(v["万能副词"].values()) + sum(v["形容词通胀"].values()) * 2
    d7 = clamp(6.5 + min(2.5, info * 0.4)
               - sat(n_waffle, 4.0, ref(600, 1.0)))

    subs = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "D6": d6, "D7": d7}
    hi = round(sum(subs[k_] * WEIGHTS[k_] for k_ in WEIGHTS) / 10, 1)
    return {
        "子分": {kk: round(vv, 1) for kk, vv in subs.items()},
        "HI": hi,
        "低置信维度": ["D4", "D7"],
    }


def grade(hi: float) -> str:
    if hi >= 85:
        return "人味充足（只做微调）"
    if hi >= 70:
        return "轻度 AI 味（处理最低的 1–2 维）"
    if hi >= 50:
        return "明显 AI 味（处理 3–4 维）"
    if hi >= 30:
        return "模板化严重（建议重构骨架）"
    return "机器腔（多半要重写）"


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

DIMG = {
    "D1": "结构机械度", "D2": "词汇空泛度", "D3": "细节具体度", "D4": "立场与声音",
    "D5": "节奏起伏度", "D6": "逻辑套壳度", "D7": "信息增量度",
}


def kv_table(d: dict) -> str:
    if not d:
        return "_（无）_"
    return "、".join(f"{k}×{v}" for k, v in sorted(d.items(), key=lambda x: -x[1]))


def render_md(m: dict, sc=None) -> str:
    L = []
    A = L.append
    A("## 人味校准 · 机器体检报告\n")
    A("### 规模")
    A(f"- 总字数 **{m['规模']['总字数']}**　句子 {m['规模']['句子数']}　段落 {m['规模']['段落数']}\n")

    A("### 节奏（D5 证据）")
    r = m["节奏"]
    A(f"- 句长：均值 {r['句长均值']}　标准差 **{r['句长标准差']}**　"
      f"最短 {r['最短句']} / 最长 {r['最长句']}（比 **{r['最长最短比']}**）")
    A(f"- 短句占比（≤10 字）：**{r['短句占比(≤10字)']}**")
    A(f"- 段落句数：均值 {r['段落句数均值']}　标准差 **{r['段落句数标准差']}**")
    A("")
    A("> 参照：句长标准差 < 8 属平铺；最长最短比 < 2.5 属缺乏起伏。\n")

    A("### 词汇（D2 证据）")
    v = m["词汇"]
    A(f"- 黑话命中 **{sum(v['黑话命中'].values())}** 处（每千字 {v['黑话数(每千字)']}）：{kv_table(v['黑话命中'])}")
    A(f"- 万能副词 **{sum(v['万能副词'].values())}** 处（每千字 {v['万能副词数(每千字)']}）：{kv_table(v['万能副词'])}")
    A(f"- 抽象名词 **{sum(v['抽象名词'].values())}** 处（每千字 {v['抽象名词数(每千字)']}）：{kv_table(v['抽象名词'])}")
    A(f"- 形容词通胀 **{sum(v['形容词通胀'].values())}** 处：{kv_table(v['形容词通胀'])}")
    A("")

    A("### 结构套路（D1 / D6 证据）")
    if m["结构套路"]:
        for name, info in m["结构套路"].items():
            ex = "；".join(info["samples"][:2])
            A(f"- **{name}** ×{info['count']}　例：{ex}")
    else:
        A("- 未命中结构套路模板")
    A("")

    A("### 具体性（D3 证据）")
    s = m["具体性"]
    A(f"- 数字 {s['数字个数']}　百分比 {s['百分比个数']}　时间表达 {s['时间表达个数']}　"
      f"书名号引用 {s['书名号引用个数']}")
    A(f"- 具体信息密度：**{s['具体信息数(每千字)']}** / 千字")
    A("")

    A("### 人称与在场感（D4 证据）")
    p = m["人称与在场感"]
    A(f"- 第一人称 {p['第一人称出现次数']} 次（每千字 **{p['第一人称(每千字)']}**）")
    A("")

    A("### 过改预警")
    o = m["过改预警"]
    if sum(o["网络流行语"].values()) or o["emoji个数"]:
        A(f"- ⚠️ 网络流行语 {sum(o['网络流行语'].values())} 处：{kv_table(o['网络流行语'])}")
        A(f"- ⚠️ emoji {o['emoji个数']} 个")
        A("- 提醒：人味 ≠ 网感，堆砌流行语与 emoji 属于过改，会拉低 D2/D7。")
    else:
        A("- 未检出网络流行语与 emoji")
    A("")

    if sc:
        A("### 启发式参考分（仅供对照）")
        A("")
        A("| 维度 | 名称 | 参考子分 | 权重 |")
        A("|---|---|---|---|")
        for k_ in WEIGHTS:
            A(f"| {k_} | {DIMG[k_]} | {sc['子分'][k_]} | {WEIGHTS[k_]} |")
        A("")
        A(f"**参考 HI = {sc['HI']}　→　{grade(sc['HI'])}**")
        A("")
        A(f"- 低置信维度：{'、'.join(sc['低置信维度'])}——脚本只能测到密度信号，"
          "是否真的「无立场」「无信息增量」必须由模型读文后判定。")
        A("")
        A("> 该分数由规则启发式估算，仅用于快速定位量级。")
        A("> 正式评分必须由模型按 `references/checklist.md` 逐维取证后给出，两者不一致时以后者为准。")
    return "\n".join(L)


def render_text(m: dict) -> str:
    r, v = m["节奏"], m["词汇"]
    lines = [
        f"总字数 {m['规模']['总字数']} | 句 {m['规模']['句子数']} | 段 {m['规模']['段落数']}",
        f"句长 均值{r['句长均值']} sd{r['句长标准差']} 比{r['最长最短比']} 短句占比{r['短句占比(≤10字)']}",
        f"段落句数 sd{r['段落句数标准差']}",
        f"黑话 {sum(v['黑话命中'].values())} | 副词 {sum(v['万能副词'].values())} | "
        f"抽象名词 {sum(v['抽象名词'].values())} | 通胀词 {sum(v['形容词通胀'].values())}",
        f"套路 {m['套路总数']} | 具体信息/千字 {m['具体性']['具体信息数(每千字)']} | "
        f"第一人称/千字 {m['人称与在场感']['第一人称(每千字)']}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="人味校准器 · 确定性文本体检")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--file", help="输入文件路径（UTF-8）")
    src.add_argument("--text", help="直接传入文本")
    ap.add_argument("--format", choices=["md", "json", "text"], default="md")
    ap.add_argument("--score", action="store_true", help="输出启发式参考分")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"[错误] 无法读取文件：{e}", file=sys.stderr)
            return 2
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("[错误] 输入文本为空", file=sys.stderr)
        return 2

    m = scan(text, args.top)
    sc = heuristic_scores(m) if (args.score or args.format == "md") else None

    if args.format == "json":
        payload = {"metrics": m}
        if args.score:
            payload["heuristic"] = sc
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == "text":
        print(render_text(m))
    else:
        print(render_md(m, sc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
