#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decode_scan.py —— 「爆款结构逆向拆解器」平台识别 + 结构骨架扫描

两种用法：

1) 识别平台（拿到链接时先跑）
   python decode_scan.py --url "https://www.xiaohongshu.com/explore/xxx"
   输出：平台、内容形态、拆解框架、抓取难度、建议路径

2) 扫描结构骨架（拿到正文后跑）
   python decode_scan.py --file content.md --platform xiaohongshu --format md
   输出：标题构成、首句钩子类型、段落节奏、小标题间隔、金句候选、
        互动引导、标签与视觉元素、平台框架对照

可选参数：
   --text STR        直接传入正文
   --title STR       手动指定标题（默认从正文首行推断）
   --format md|json|text
   --list-platforms  打印平台对照表
   --url 与 --file/--text 可同时使用：先报平台判定，再给结构扫描

仅依赖 Python 标准库。词表需与 references/frameworks.md 保持一致。
"""

import argparse
import json
import re
import statistics
import sys

# --------------------------------------------------------------------------
# 平台表 —— 与 references/frameworks.md 第 1–8 节对应，改动请同步两处
# --------------------------------------------------------------------------

PLATFORMS = [
    {
        "key": "xiaohongshu", "name": "小红书",
        "form": "图文笔记 / 短视频",
        "framework": "封面标题组合 → 正文钩子 → 互动引导",
        "difficulty": "高",
        "advice": "反爬强、正文需登录态。不要硬试，直接请用户粘贴文本或发截图。",
        "hosts": ["xiaohongshu.com", "xhslink.com"],
    },
    {
        "key": "mp", "name": "微信公众号",
        "form": "长图文",
        "framework": "开篇引入法 → 小标题逻辑链 → 金句收尾",
        "difficulty": "中",
        "advice": "公开文章常可直接抓取，但可能触发验证页。先试一次，失败立即降级请用户粘贴。",
        "hosts": ["mp.weixin.qq.com"],
    },
    {
        "key": "channels", "name": "微信视频号",
        "form": "短视频",
        "framework": "前 3 秒钩子 → 结构节奏 → 结尾引导",
        "difficulty": "高",
        "advice": "无稳定的公开网页正文，需在微信内查看。请用户提供口播文字稿或截图。",
        "hosts": ["channels.weixin.qq.com", "finder.video.qq.com"],
    },
    {
        "key": "zhihu", "name": "知乎",
        "form": "问答 / 专栏",
        "framework": "问题定义 → 论证结构 → 情绪落点",
        "difficulty": "中",
        "advice": "答案多可公开阅读。注意补全被折叠的「展开全文」部分，否则会误判结构长度。",
        "hosts": ["zhihu.com", "zhuanlan.zhihu.com"],
    },
    {
        "key": "douyin", "name": "抖音",
        "form": "短视频",
        "framework": "3 秒钩子 → 完播结构 → 互动引导",
        "difficulty": "高",
        "advice": "需 App 内环境。请用户提供文字稿或截图。",
        "hosts": ["douyin.com", "iesdouyin.com", "v.douyin.com"],
    },
    {
        "key": "kuaishou", "name": "快手",
        "form": "短视频",
        "framework": "3 秒钩子 → 完播结构 → 互动引导",
        "difficulty": "高",
        "advice": "需 App 内环境。请用户提供文字稿。",
        "hosts": ["kuaishou.com", "v.kuaishou.com"],
    },
    {
        "key": "bilibili", "name": "B站",
        "form": "中长视频",
        "framework": "标题封面 → 开场承诺 → 章节推进 → 三连引导",
        "difficulty": "低",
        "advice": "页面可抓取，可取标题 / 简介 / 字幕。优先取字幕；无字幕请用户提供文字稿。",
        "hosts": ["bilibili.com", "b23.tv"],
    },
    {
        "key": "weibo", "name": "微博",
        "form": "短图文",
        "framework": "热点锚点 → 观点爆点 → 转发话术",
        "difficulty": "中",
        "advice": "公开微博可读，长文可能跳转。先试抓取。",
        "hosts": ["weibo.com", "weibo.cn", "m.weibo.cn", "s.weibo.com", "t.cn"],
    },
    {
        "key": "podcast", "name": "播客 / 长音频",
        "form": "音频",
        "framework": "开场承诺 → 话题分段 → 结尾钩子",
        "difficulty": "低",
        "advice": "节目简介与 show notes 通常可直接抓取。无文字稿时请用户提供转录。",
        "hosts": ["xiaoyuzhoufm.com", "ximalaya.com", "podcasts.apple.com",
                  "music.163.com", "lizhi.fm"],
    },
    {
        "key": "youtube", "name": "YouTube",
        "form": "中长视频",
        "framework": "标题封面 → 开场承诺 → 章节推进 → 引导",
        "difficulty": "低",
        "advice": "可取标题 / 简介 / 字幕。",
        "hosts": ["youtube.com", "youtu.be"],
    },
    {
        "key": "toutiao", "name": "今日头条 / 百家号",
        "form": "图文 / 短视频",
        "framework": "通用五层：注意力 → 承诺 → 主体 → 情绪 → 引导",
        "difficulty": "中",
        "advice": "图文部分多可抓取；视频需文字稿。",
        "hosts": ["toutiao.com", "baijiahao.baidu.com"],
    },
    {
        "key": "generic", "name": "未识别平台",
        "form": "未知",
        "framework": "通用五层：注意力 → 承诺 → 主体 → 情绪 → 引导",
        "difficulty": "中",
        "advice": "未能识别平台。按通用五层拆解，并请用户补充平台与内容形态以套用更准的框架。",
        "hosts": [],
    },
]

SHORT_LINK_HOSTS = ["t.cn", "dwz.cn", "url.cn", "suo.im", "sourl.cn", "xhslink.com",
                    "b23.tv", "v.douyin.com", "v.kuaishou.com"]

PLATFORM_BY_KEY = {p["key"]: p for p in PLATFORMS}

# --------------------------------------------------------------------------
# 检测词表
# --------------------------------------------------------------------------

HOOK_TYPES = {
    "提问型": [r"[？?]", r"为什么", r"怎么(办|做|样)", r"如何", r"凭什么", r"是不是", r"有没有"],
    "反常识": [r"别再", r"千万不要?", r"其实(不|并)", r"你以为", r"真相", r"反而", r"错了", r"不是.{0,10}而是", r"没什么用"],
    "结果前置": [r"我(把|用|花了|做|试)", r"已经", r"搞定", r"完成了", r"亲测"],
    "痛点共鸣": [r"是不是也", r"都这样", r"你是不是", r"有没有人", r"每(次|天)都", r"总是", r"又.{0,4}了"],
    "身份代入": [r"作为", r"身为", r"做了?\s*\d+\s*年", r"\d+\s*年经验", r"我是"],
    "成本量化": [r"只花了", r"不到\s*\d", r"\d+\s*(块|元|分钟|小时|天|周)", r"一个月", r"零成本"],
    "数字清单": [r"\d+\s*(个|条|种|招|步|点|件事)", r"^第[一二三四五六七八九十]+\s*[个条点步种]"],
    "利益承诺": [r"教你", r"方法", r"技巧", r"公式", r"模板", r"清单", r"攻略", r"避坑", r"保姆级"],
    "故事开场": [r"有一天", r"那天", r"上周", r"昨天", r"前[几两]天", r"有一次", r"有个",
                 r"一位", r"朋友", r"同事", r"客户", r"老板", r"小[张王李赵周吴陈刘]"],
    "场景白描": [r"[零一二三四五六七八九十\d]{1,3}\s*点", r"\d+\s*月\s*\d+\s*日", r"凌晨"],
    "冲突悬念": [r"没想到", r"竟然", r"反转", r"意外", r"结果发现", r"翻车"],
    "权威引用": [r"(报告|数据|研究|调查|统计)[^。，,]{0,4}(显示|表明|发现|指出|证明)",
                 r"据[^。，,]{0,8}(统计|调查|报道)", r"《[^》]{1,20}》"],
}

CTA_TYPES = {
    "收藏型": [r"收藏", r"码住", r"马住", r"先存", r"保存起来", r"建议收藏"],
    "关注型": [r"关注我", r"关注不迷路", r"点个关注", r"蹲(一个|后续)", r"后续(更新|会)"],
    "评论关键词": [r"评论区", r"留言", r"扣\s*1", r"扣一", r"扣[0-9]", r"评论区见", r"说说你们?的"],
    "提问式": [r"你怎么看", r"你们(都|一般|会)", r"你是怎么", r"评论区(告诉我|聊聊)"],
    "转发型": [r"转发", r"分享给", r"发给", r"扩散", r"转给"],
    "私信引流": [r"私信", r"后台回复", r"滴滴我", r"需要的?[说告]一声"],
    "点赞型": [r"点赞", r"双击", r"点个赞"],
    "三连型": [r"三连", r"一键三连"],
    "在看型": [r"在看", r"点个在看"],
}

HEADING_PATTERNS = [
    r"^#{2,6}\s+",                       # markdown 小标题
    r"^[一二三四五六七八九十]+\s*[、．.，,]",  # 一、
    r"^\d{1,2}\s*[、．.](?!\d)\s*\S",     # 1. 小标题（避开 2024.5 这类）
    r"^【.{1,20}】\s*$",                   # 【小标题】
    r"^[（(]\s*[一二三四五六七八九十\d]+\s*[）)]",  # (一)
    r"^[^\w]{0,3}\s*第\s*[一二三四五六七八九十\d]+\s*[步点条部分章]",  # ✅ 第一步 / 第二点
    r"^[^\w]{0,3}\s*Step\s*\d+",          # Step 1
]

PUNCT = "　 \t\r\n，。！？；：、（）()《》〈〉「」『』“”‘’\"'…—-—·,.!?;:[]{}<>/~`|\\+*&^%$#@="
EMOJI_RX = "[\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF\u2600-\u27BF\u2B00-\u2BFF]"


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------

def cjk_len(s: str) -> int:
    s = re.sub(r"[A-Za-z0-9]+", "A", s)
    return len([c for c in s if c not in PUNCT and not c.isspace()])


def split_sentences(text: str) -> list:
    parts = re.split(r"[。！？!?；;]+|\n+", text)
    return [p.strip() for p in parts if cjk_len(p.strip()) > 0]


def is_heading(line: str) -> bool:
    return any(re.match(p, line.strip()) for p in HEADING_PATTERNS)


def clean_heading(line: str) -> str:
    return re.sub(r"^#{1,6}\s*", "", line.strip()).strip()


def parse_blocks(text: str) -> list:
    """把文本切成块：heading（小标题，单行）与 para（正文段，可多行）。

    空行与「小标题行」都会终止当前段落——否则小标题和它的正文会被并成一块，
    导致节奏数据与逻辑链判定全部失准。
    """
    blocks, cur = [], []

    def flush():
        if cur:
            blocks.append({"type": "para", "text": "\n".join(cur).strip()})
            cur.clear()

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            flush()
            continue
        if is_heading(s):
            flush()
            blocks.append({"type": "heading", "text": clean_heading(s)})
            continue
        cur.append(s)
    flush()
    return blocks


def safe_stdev(vals: list) -> float:
    return round(statistics.pstdev(vals), 2) if len(vals) > 1 else 0.0


def norm_host(url: str) -> str:
    m = re.match(r"^[a-zA-Z]+://([^/?#]+)", url.strip())
    host = m.group(1) if m else url.strip().split("/")[0]
    return re.sub(r"^(www|m)\.", "", host.lower())


# --------------------------------------------------------------------------
# 平台识别
# --------------------------------------------------------------------------

def detect_platform(url: str) -> dict:
    host = norm_host(url)
    for p in PLATFORMS:
        for h in p["hosts"]:
            if host == h or host.endswith("." + h):
                res = dict(p)
                res["matched_host"] = host
                res["is_short_link"] = host in SHORT_LINK_HOSTS
                if res["is_short_link"]:
                    res["advice"] = ("短链。需先展开真实地址再判断，"
                                     "展开属于抓取动作，失败同样按降级阶梯处理。" + res["advice"])
                return res
    res = dict(PLATFORM_BY_KEY["generic"])
    res["matched_host"] = host
    res["is_short_link"] = host in SHORT_LINK_HOSTS
    return res


# --------------------------------------------------------------------------
# 结构扫描
# --------------------------------------------------------------------------

def scan(text: str, platform_key: str = "generic", title: str = None) -> dict:
    text = text.strip()

    if title is None:
        cand = ""
        for raw in text.split("\n"):
            s = raw.strip()
            if not s:
                continue
            s2 = re.sub(r"^#{1,6}\s*", "", s).strip()
            if cjk_len(s2) <= 40:
                cand = s2
            break
        title = cand

    blocks = parse_blocks(text)
    # 标题不是正文段落，先剔除，否则会污染节奏数据与金句候选
    if title and blocks and blocks[0]["type"] == "para":
        ls = blocks[0]["text"].split("\n")
        if ls and re.sub(r"^#{1,6}\s*", "", ls[0].strip()).strip() == str(title).strip():
            rest = ls[1:]
            if any(x.strip() for x in rest):
                blocks[0]["text"] = "\n".join(rest).strip()
            else:
                blocks.pop(0)

    body_paras = [b["text"] for b in blocks if b["type"] == "para"]
    body = "\n\n".join(body_paras)

    sents = split_sentences(body if body else text)
    slens = [cjk_len(s) for s in sents]
    plens = [cjk_len(p) for p in body_paras]

    headings = []
    cur_chars = 0
    for b in blocks:
        if b["type"] == "heading":
            headings.append({"序号": len(headings) + 1, "文本": b["text"][:40],
                             "此前正文字数": cur_chars})
            cur_chars = 0
        else:
            cur_chars += cjk_len(b["text"])
    intervals = [h["此前正文字数"] for h in headings[1:]]

    first_sent = sents[0] if sents else ""
    hook_hits = [k for k, regs in HOOK_TYPES.items()
                 if any(re.search(r, first_sent) for r in regs)]
    cta_hits = {}
    for name, regs in CTA_TYPES.items():
        found = []
        for r in regs:
            for m in re.finditer(r, text):
                found.append(m.group(0))
        if found:
            cta_hits[name] = len(found)

    quotes = []
    for b in blocks:
        if b["type"] == "heading":
            continue
        p = b["text"]
        n = cjk_len(p)
        if 6 <= n <= 30 and "\n" not in p:
            if not any(any(re.search(r, p) for r in regs) for regs in CTA_TYPES.values()):
                quotes.append(p.strip())
        if len(quotes) >= 8:
            break

    tags = re.findall(r"#([^#\s\[\]]{1,20})(?:\[话题\])?", text)
    t_chars = cjk_len(title) if title else 0
    body_chars = cjk_len(body)

    return {
        "平台": PLATFORM_BY_KEY.get(platform_key, PLATFORM_BY_KEY["generic"])["name"],
        "平台key": platform_key,
        "拆解框架": PLATFORM_BY_KEY.get(platform_key, PLATFORM_BY_KEY["generic"])["framework"],
        "标题": {
            "文本": title,
            "字数": t_chars,
            "含数字": bool(re.search(r"\d", title or "")),
            "含分隔符": bool(re.search(r"[|｜/·—]", title or "")),
            "含疑问": bool(re.search(r"[？?]", title or "")),
            "含括号强调": bool(re.search(r"[【\[（(]", title or "")),
            "含emoji": len(re.findall(EMOJI_RX, title or "")),
            "超长警告": t_chars > 30,
        },
        "首句钩子": {
            "原文": first_sent[:80],
            "命中类型": hook_hits if hook_hits else ["未命中标准类型"],
        },
        "节奏": {
            "正文总字数": body_chars,
            "段落数": len(body_paras),
            "段长均值": round(statistics.mean(plens), 1) if plens else 0,
            "段长标准差": safe_stdev(plens),
            "最短段": min(plens) if plens else 0,
            "最长段": max(plens) if plens else 0,
            "句子数": len(sents),
            "句长均值": round(statistics.mean(slens), 1) if slens else 0,
            "短句占比(≤15字)": round(sum(1 for x in slens if x <= 15) / len(slens), 3) if slens else 0,
        },
        "小标题": {
            "数量": len(headings),
            "清单": headings,
            "平均间隔字数": round(statistics.mean(intervals), 1) if intervals else 0,
            "过长间隔警告": [i for i in intervals if i > 1000],
        },
        "金句候选": quotes,
        "互动引导": cta_hits,
        "标签": tags,
        "视觉元素": {
            "emoji个数": len(re.findall(EMOJI_RX, text)),
            "第二人称(每千字)": round(
                len(re.findall(r"你|您", text)) * 1000 / max(body_chars, 1), 2),
            "数字(每千字)": round(
                len(re.findall(r"\d+", text)) * 1000 / max(body_chars, 1), 2),
        },
    }


# --------------------------------------------------------------------------
# 平台框架对照
# --------------------------------------------------------------------------

FRAMEWORK_CHECKS = {
    "xiaohongshu": [("封面标题组合", "标题构成 + 封面类型（封面需人工看图）"),
                    ("正文钩子", "首句类型 + 前 3 行是否给足继续读的理由"),
                    ("互动引导", "CTA 类型 + 位置")],
    "mp": [("开篇引入法", "引入类型 + 第几段完成立论过渡"),
           ("小标题逻辑链", "逻辑链类型 + 间隔节奏"),
           ("金句收尾", "收尾类型 + 可独立传播的句子")],
    "zhihu": [("问题定义", "是重新定义、否定前提还是补足条件"),
              ("论证结构", "结构类型 + 信任状位置"),
              ("情绪落点", "落点类型 + 最后一句")],
    "channels": [("前 3 秒钩子", "口播 / 画面 / 文字，至少一个强"),
                 ("结构节奏", "结构类型 + 信息点间隔"),
                 ("结尾引导", "只放一个 CTA")],
    "douyin": [("3 秒钩子", "冲突 / 悬念 / 视觉奇观 / 身份宣言"),
               ("完播结构", "前置高潮 / 信息密度 / 中途反转"),
               ("互动引导", "评论区提问 / 二选一 / 结尾留钩")],
    "kuaishou": [("3 秒钩子", "同抖音"),
                 ("完播结构", "同抖音"),
                 ("互动引导", "同抖音")],
    "bilibili": [("标题封面", "标题给信息增量，封面给话题性"),
                 ("开场承诺", "前 15 秒承诺了什么"),
                 ("章节推进", "分段感与小结"),
                 ("三连引导", "位置是否在价值峰值之后")],
    "weibo": [("热点锚点", "挂了什么热点、挂得自然与否"),
              ("观点爆点", "可引用的一句话"),
              ("转发话术", "让转发者显得有态度")],
    "podcast": [("开场承诺", "前 2 分钟是否说清收听理由"),
                ("话题分段", "话题切换信号"),
                ("结尾钩子", "下期预告 / 金句回扣")],
    "generic": [("L1 注意力", "钩子类型 + 位置"),
                ("L2 承诺", "给了什么预期"),
                ("L3 主体", "结构原型 + 分段逻辑"),
                ("L4 情绪", "峰值位置 + 手法"),
                ("L5 引导", "CTA 类型 + 位置")],
}


def render_platform_md(p: dict, url: str = "") -> str:
    L = ["## 平台判定\n"]
    if url:
        L.append(f"- 链接：`{url}`")
    L.append(f"- **平台**：{p['name']}")
    L.append(f"- **内容形态**：{p['form']}")
    L.append(f"- **套用框架**：{p['framework']}")
    L.append(f"- **抓取难度**：{p['difficulty']}")
    if p.get("is_short_link"):
        L.append("- ⚠️ 检测到短链，需先展开再判断")
    L.append(f"- **建议路径**：{p['advice']}")
    L.append("")
    return "\n".join(L)


def render_md(m: dict) -> str:
    L = []
    A = L.append
    A("## 结构骨架扫描\n")
    t = m["标题"]
    A("### 标题构成")
    A(f"- 文本：{t['文本'] or '（未识别到标题）'}")
    A(f"- 字数 **{t['字数']}**"
      + ("　⚠️ 超过 30 字，点击率通常受损" if t["超长警告"] else ""))
    marks = [k for k in ["含数字", "含分隔符", "含疑问", "含括号强调"] if t[k]]
    A(f"- 命中成分：{'、'.join(marks) if marks else '无'}　｜　emoji {t['含emoji']} 个")
    A("- 对照公式：人群词 + 时间/成本 + 结果 + 情绪钩子（缺哪项需人工补判）")
    A("")

    h = m["首句钩子"]
    A("### 首句钩子（L1/L2 关键位）")
    A(f"- 原文：「{h['原文']}」")
    A(f"- 命中类型：**{'、'.join(h['命中类型'])}**")
    A("")

    r = m["节奏"]
    A("### 节奏数据")
    A(f"- 正文 {r['正文总字数']} 字，共 {r['段落数']} 段")
    A(f"- 段长：均值 {r['段长均值']}　标准差 **{r['段长标准差']}**　"
      f"最短 {r['最短段']} / 最长 {r['最长段']}")
    A(f"- 句长均值 {r['句长均值']}　短句占比（≤15 字）**{r['短句占比(≤15字)']}**")
    A("")
    A("> 参照：段长标准差大 = 节奏有起伏；短句占比高 = 更口语、更适合图文平台。")
    A("")

    sh = m["小标题"]
    A("### 小标题与逻辑链")
    if sh["数量"]:
        A(f"- 共 {sh['数量']} 个，平均间隔 **{sh['平均间隔字数']}** 字")
        for it in sh["清单"]:
            A(f"  {it['序号']}. {it['文本']}　（此前 {it['此前正文字数']} 字）")
        if sh["过长间隔警告"]:
            A(f"- ⚠️ 存在超过 1000 字无小标题的区段：{sh['过长间隔警告']}")
    else:
        A("- 未识别到小标题（图文短内容可能本就没有；长文缺失则逻辑链断裂）")
    A("")

    A("### 金句候选（独立成段的短句）")
    if m["金句候选"]:
        for q in m["金句候选"]:
            A(f"- 「{q}」")
    else:
        A("- 无。缺少可截图的传播句，是常见短板。")
    A("")

    A("### 互动引导")
    if m["互动引导"]:
        for k, v in sorted(m["互动引导"].items(), key=lambda x: -x[1]):
            A(f"- **{k}** ×{v}")
        if len(m["互动引导"]) > 2:
            A("- ⚠️ CTA 类型超过 2 种，容易互相稀释，通常只保留一种转化更好。")
    else:
        A("- 未检出 CTA，内容缺少行动引导。")
    A("")

    if m["标签"]:
        A("### 话题标签")
        A("- " + "、".join("#" + x for x in m["标签"][:15]))
        A("")

    v = m["视觉元素"]
    A("### 视觉与语言密度")
    A(f"- emoji {v['emoji个数']} 个")
    A(f"- 第二人称（每千字）**{v['第二人称(每千字)']}**　→ 越高越像对话")
    A(f"- 数字（每千字）{v['数字(每千字)']}")
    A("")

    A("### 平台框架对照")
    A(f"- 平台：**{m['平台']}**　框架：{m['拆解框架']}")
    A("")
    A("| 拆解层 | 本层要判定的东西 | 扫描能给的线索 |")
    A("|---|---|---|")
    for layer, what in FRAMEWORK_CHECKS.get(m["平台key"], FRAMEWORK_CHECKS["generic"]):
        A(f"| {layer} | {what} | 见上方对应小节 |")
    A("")
    A("> 扫描只给骨架数据。每一层「为什么有效」必须由模型读原文后判定，")
    A("> 并写清位置（第几句 / 第几段 / 约第几秒）。")
    return "\n".join(L)


def render_text(m: dict) -> str:
    return "\n".join([
        f"平台 {m['平台']} | 框架 {m['拆解框架']}",
        f"标题 {m['标题']['字数']}字 | 首句钩子 {'、'.join(m['首句钩子']['命中类型'])}",
        f"正文 {m['节奏']['正文总字数']}字 {m['节奏']['段落数']}段 | "
        f"段长sd {m['节奏']['段长标准差']} | 短句占比 {m['节奏']['短句占比(≤15字)']}",
        f"小标题 {m['小标题']['数量']}个 平均间隔 {m['小标题']['平均间隔字数']}字",
        f"金句候选 {len(m['金句候选'])} | CTA {list(m['互动引导'].keys()) or '无'}",
        f"标签 {len(m['标签'])} | emoji {m['视觉元素']['emoji个数']}",
    ])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="爆款结构逆向拆解器 · 平台识别 + 结构扫描")
    ap.add_argument("--url", help="内容链接，用于识别平台")
    ap.add_argument("--file", help="正文文件路径（UTF-8）")
    ap.add_argument("--text", help="直接传入正文")
    ap.add_argument("--title", help="手动指定标题")
    ap.add_argument("--platform", help="指定平台 key（覆盖识别结果）")
    ap.add_argument("--format", choices=["md", "json", "text"], default="md")
    ap.add_argument("--list-platforms", action="store_true", help="打印平台对照表")
    args = ap.parse_args()

    if args.list_platforms:
        print("| key | 平台 | 内容形态 | 抓取难度 | 拆解框架 |")
        print("|---|---|---|---|---|")
        for p in PLATFORMS:
            print(f"| `{p['key']}` | {p['name']} | {p['form']} | {p['difficulty']} | {p['framework']} |")
        return 0

    if not args.url and not args.file and not args.text:
        ap.print_help()
        return 2

    plat = None
    if args.url:
        plat = detect_platform(args.url)

    platform_key = args.platform or (plat["key"] if plat else "generic")
    if platform_key not in PLATFORM_BY_KEY:
        print(f"[警告] 未知平台 key `{platform_key}`，回退到 generic。"
              f"可用值见 --list-platforms", file=sys.stderr)
        platform_key = "generic"

    text = ""
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"[错误] 无法读取文件：{e}", file=sys.stderr)
            return 2
    elif args.text:
        text = args.text

    if args.format == "json":
        out = {}
        if plat:
            out["platform_detection"] = plat
        if text.strip():
            out["scan"] = scan(text, platform_key, args.title)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    chunks = []
    if plat:
        chunks.append(render_platform_md(plat, args.url))
    if text.strip():
        chunks.append(render_md(scan(text, platform_key, args.title)))
    elif plat and args.format != "text":
        chunks.append("> 未提供正文。请抓取成功后用 `--file` 或 `--text` 再跑一次结构扫描，"
                      "或请用户粘贴正文 / 发截图。\n")

    if args.format == "text":
        print(render_text(scan(text, platform_key, args.title)) if text.strip()
              else f"平台 {plat['name']} | 抓取难度 {plat['difficulty']}")
    else:
        print("\n".join(chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
