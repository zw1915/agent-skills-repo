#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compliance_scan.py — 电商详情页文案合规扫描（确定性部分）

只做规则能做的事：词库匹配、上下文豁免、风险分级、逐句定位、替换建议。
句子级误导、对比贬低、证明材料核验必须由模型读文判断，脚本不负责。

用法:
  python compliance_scan.py --file draft.txt --category cosmetic --format md
  python compliance_scan.py --text "全网最低价，包治百病" --category general
  python compliance_scan.py --list-categories
  python compliance_scan.py --list-words --level high
"""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------- 词条分组
# 每组共享 level / cat / basis / fix；个别词可用 overrides 覆写 fix。
GROUPS = [
    # ============ A 绝对化用语 ============
    dict(level="high", cat="绝对化用语",
         basis="《广告法》第九条第(三)项",
         fix="删除形容词，改补可验证的具体优势（如「续航 12 小时，较上代提升 30%」）",
         words=["最好", "最佳", "最强", "最大", "最优", "最先进", "最低", "最便宜",
                "最受欢迎", "最优质", "最高端", "最专业", "最权威", "最有效", "最快",
                "最省", "最全", "最安全", "最健康", "最高级", "最舒适", "最时尚",
                "最流行", "最新", "最划算", "最超值", "最高", "最棒", "最好用"],
         overrides={"最新": "「最新」同属绝对化，改为具体时点，如「2026 春季新款」"}),
    dict(level="high", cat="绝对化用语",
         basis="《广告法》第九条第(三)项",
         fix="改为带来源与时点的排名事实；无第三方数据则删除结论，只留事实",
         words=["第一", "第1", "No.1", "TOP1", "排名第一", "销量第一", "全国第一",
                "全球第一", "行业第一", "同类第一", "全网第一", "销量冠军", "行业冠军",
                "销售冠军", "首选品牌", "首选"],
         overrides={"第一": "如需表达领先，写为「XX 平台 2025 年 XX 类目销量 Top10（来源：XX 数据，2026.01）」"}),
    dict(level="high", cat="绝对化用语",
         basis="《广告法》第九条第(三)项",
         fix="删除；有授权文件或专利者可保留，但必须标注证书编号",
         words=["唯一", "独家", "独一无二", "绝无仅有", "仅此一家", "仅此一款",
                "独家配方", "独家技术", "独家专利", "独家授权"],
         overrides={"独家授权": "有授权书时可保留，须标注授权方与授权期限"}),
    dict(level="high", cat="绝对化用语",
         basis="《广告法》第九条第(三)项",
         fix="改为具体规格或材质描述，用事实替换形容词（如「意大利头层牛皮」）",
         words=["顶级", "顶尖", "极致", "极品", "至尊", "巅峰", "终极", "王牌", "王者",
                "冠军品牌", "领导者", "领导品牌", "领先品牌", "全球领先", "世界领先",
                "国际领先", "行业领先", "国内领先", "领跑", "标杆", "国家级", "世界级",
                "国际级", "国宴级", "军工级", "医用级", "药妆级", "万能", "全能"],
         overrides={
             "国家级": "需国家主管部门认定文件方可使用，否则删除",
             "医用级": "非医疗器械不得使用，改为具体材质标准（如「316L 不锈钢」）",
             "军工级": "需军方认定文件，否则删除",
             "药妆级": "「药妆」已被明令禁止使用，须删除，不是改写项"}),
    dict(level="high", cat="绝对化用语",
         basis="《广告法》第九条第(三)项",
         fix="删除，或改为可量化的对比事实",
         words=["完美", "无瑕", "无可挑剔", "无与伦比", "史无前例", "空前绝后",
                "登峰造极", "绝版", "包治百病"]),

    # ============ B 效果与承诺 ============
    dict(level="high", cat="效果承诺",
         basis="《广告法》第二十八条",
         fix="需写明具体条件与期限，否则删除；金融类目绝对禁用",
         words=["无效退款", "无效退全款", "不满意退款", "零风险", "无风险", "稳赚不赔",
                "保本保息", "躺赚", "一夜暴富", "高回报", "保本", "保收益",
                "稳赚", "保证收益", "投资零风险"]),
    dict(level="high", cat="时效承诺",
         basis="《广告法》第二十八条",
         fix="删除；有临床或检测依据者可改为「实测数据 + 样本量 + 条件」",
         words=["一次见效", "立刻见效", "立即见效", "当天见效", "3天见效", "7天见效",
                "立竿见影", "药到病除", "根治", "彻底解决", "彻底治愈", "永久",
                "永不反弹", "断根", "永不复发", "一次根治"]),
    dict(level="high", cat="效果保证",
         basis="《广告法》第二十八条",
         fix="改为有依据的有效率表述（注明样本量与检测方式），无依据则删除",
         words=["100%有效", "绝对有效", "保证有效", "必瘦", "必买", "绝对安全",
                "绝对无副作用", "百分百有效", "绝对可靠"]),

    # ============ C 医疗与功效宣称 ============
    dict(level="high", cat="医疗功效宣称",
         basis="《广告法》第十七条",
         fix="非药品不得使用，整句删除；不可靠换词过关",
         words=["治疗", "治愈", "疗效", "药效", "消炎", "消肿", "止痛", "抗病毒",
                "抗肿瘤", "防癌", "抗癌", "降血压", "降血糖", "降血脂", "助眠",
                "预防疾病", "杀菌", "抑菌", "除菌", "消毒",
                "处方", "临床验证", "医学级", "修复受损屏障"]),
    dict(level="mid", cat="资质宣称（需证明）",
         basis="《广告法》第二十八条",
         fix="需提供对应资质证书编号；无资质即删除",
         words=["医疗器械", "械字号", "药字号", "处方药", "OTC", "国药准字"]),
    dict(level="high", cat="化妆品功效宣称",
         basis="《化妆品监督管理条例》（仅特殊化妆品可宣称，需注册证号）",
         fix="普通化妆品删除；特殊化妆品可保留但须与注册功效一致并标注注册证号",
         words=["祛斑", "美白", "防晒", "防脱发", "染发", "烫发", "祛痘", "抗敏",
                "脱敏", "淡斑", "祛皱", "抗皱"],
         overrides={"抗皱": "非注册功效表述，建议改为「肤感改善」或删除"}),
    dict(level="high", cat="保健功能宣称（需保健食品资质）",
         basis="《食品安全法》《广告法》第十八条",
         fix="普通食品不得使用；保健食品须与注册功能一致，并标明「本品不能代替药物」",
         words=["增强免疫力", "提高免疫力", "增强抵抗力", "改善睡眠", "辅助降血脂",
                "缓解疲劳", "增加骨密度", "调理肠胃", "促进消化", "排毒",
                "改善体质", "改善肠道", "预防感冒", "养胃", "护肝", "补气血"]),

    # ============ D 促销误导 ============
    dict(level="high", cat="促销误导",
         basis="《广告法》第二十八条",
         fix="无第三方比价依据即删除",
         words=["全网最低", "史上最低", "全网底价", "全网最低价", "史无前例低价"]),
    dict(level="mid", cat="促销误导",
         basis="《广告法》第二十八条（需与实际一致）",
         fix="活动机制必须真实可核，与实际不符即构成欺诈",
         words=["仅此一天", "最后一天", "错过再无", "明天恢复原价", "清仓价",
                "跳楼价", "亏本甩卖", "血亏", "假一赔十", "假一赔万"]),

    # ============ E 金融承诺 ============
    dict(level="high", cat="金融投资承诺",
         basis="《广告法》第二十五条",
         fix="金融类目绝对禁用，须删除并转持牌机构合规审查",
         words=["年化收益", "预期收益", "投资回报率", "无风险收益", "保底收益"]),

    # ============ F 迷信与涉政 ============
    dict(level="high", cat="迷信宣传",
         basis="《广告法》第九条第(八)项",
         fix="删除",
         words=["招财", "转运", "辟邪", "开光", "旺夫", "改运", "风水", "镇宅",
                "招桃花", "驱邪", "化煞"]),
    dict(level="high", cat="涉政特权",
         basis="《广告法》第九条第(一)(二)项",
         fix="删除；「国家级」需国家主管部门认定文件",
         words=["特供", "专供", "军供", "国宴", "人民大会堂", "领导人同款",
                "领导专用", "军队专用"]),

    # ============ G 成分与产地（需证明） ============
    dict(level="mid", cat="需证明材料",
         basis="《广告法》第二十八条（虚假广告）",
         fix="补检测报告 / 证书编号 / 授权文件；无材料即删除",
         words=["纯天然", "无添加", "零添加", "纯手工", "权威认证", "国际认证",
                "欧盟标准", "日本技术", "德国工艺", "原产地直供", "厂家直销",
                "专家推荐", "医生推荐", "明星同款", "国家专利", "独家工艺"]),

    # ============ H 程度词（需证据） ============
    dict(level="mid", cat="程度词（需证据）",
         basis="《广告法》第二十八条",
         fix="程度词需有对比基准或测试依据，否则改为具体数值（如「较上代提升 30%」）",
         words=["效果显著", "效果出众", "显著", "明显改善", "大幅提升", "极大改善",
                "超级", "超强", "巨划算", "白菜价"]),
]

# ---------------------------------------------------------------- 上下文豁免
# hard: 匹配则不报，列入「豁免」说明
# soft: 匹配则降级为 🟡 提示
EXEMPT = {
    # 「第一人称」「第一步」「第一周」都是客观表述，不是自我优越性宣称
    "第一": {
        "hard": [r"^第一(?:人称|步|次|批|页|层|课|梯队|阶段|章节|"
                 r"周|天|个月|月|年|季度|版|代|款)"],
        "soft": [r"^第一时间"],
    },
    "最好": {"hard": [r"^最好(?:是|别|不)"]},
    "最新": {"soft": [r"^最新(?:消息|动态|公告|版本|资讯|政策)"]},
    "独家": {"soft": [r"^独家(?:专利|授权|代理|供应|配方)(?=号|证|书|（|Z|z|\d)"]},
    "唯一": {"hard": [r"^唯一(?:的)?(?:一次|一回)"]},
    "100%": {
        "hard": [r"^100%\s*(?:棉|羊毛|真丝|实木|全棉|纯棉|山羊绒|蚕丝|莱赛尔|"
                 r"莫代尔|聚酯|涤纶|天然|原浆|果汁|新疆棉)"],
    },
    "百分百": {"hard": [r"^百分百(?:棉|羊毛|真丝|实木|全棉|纯棉)"]},
    # 技术规格中的「最大」是参数而非优越性断言
    "最大": {"hard": [r"^最大(?:承重|容量|功率|尺码|尺寸|长度|宽度|高度|深度|"
                     r"厚度|直径|亮度|音量|速度|转速|载荷|输出|吸入)"]},
}

# ---------------------------------------------------------------- 品类专属词条
# (词, 级别, 类别, 依据, 替换建议)
CATEGORY_EXTRA = {
    "food": [],
    "health_food": [
        ("治疗", "high", "超出注册功能", "《广告法》第十八条", "保健食品不得涉及疾病预防治疗，删除"),
        ("替代药物", "high", "超出注册功能", "《广告法》第十八条", "删除；正确表述是「本品不能代替药物」"),
    ],
    "cosmetic": [
        ("医用", "high", "医疗器械用语", "《化妆品监督管理条例》", "化妆品不得使用医疗用语，删除"),
        ("修复", "high", "功效宣称需谨慎", "《化妆品监督管理条例》", "改为「肤感改善」等非功效表述"),
        ("干细胞", "high", "无科学依据宣称", "《化妆品监督管理条例》", "删除"),
        ("抗菌", "mid", "需检测报告", "《广告法》第二十八条", "补检测报告编号，否则删除"),
    ],
    "cosmetic_special": [
        ("彻底祛除", "high", "超出注册功效", "《化妆品监督管理条例》", "改为与注册功效一致的表述，不得延伸为「彻底」「永久」"),
        ("永久美白", "high", "超出注册功效", "《化妆品监督管理条例》", "删除，改为与注册功效一致的表述"),
    ],
    "medical_device": [
        ("治愈率", "high", "医疗器械广告禁用", "《广告法》第十六条", "删除；医疗器械不得宣称治愈率、有效率"),
        ("有效率", "high", "医疗器械广告禁用", "《广告法》第十六条", "删除"),
        ("包好", "high", "效果承诺", "《广告法》第十六条", "删除"),
    ],
    "mother_baby": [
        ("替代母乳", "high", "母婴广告禁用", "《广告法》第二十条", "删除"),
        ("母乳化", "high", "母婴广告禁用", "《广告法》第二十条", "删除"),
        ("益智", "high", "婴幼儿配方乳粉禁用", "《广告法》第二十条", "删除"),
        ("增智", "high", "婴幼儿配方乳粉禁用", "《广告法》第二十条", "删除"),
        ("提高智力", "high", "婴幼儿配方乳粉禁用", "《广告法》第二十条", "删除"),
    ],
    "apparel": [
        ("抗菌", "mid", "功能性宣称需检测", "《广告法》第二十八条", "补检测报告编号（如 GB/T 20944.3），否则删除"),
        ("防水", "mid", "功能性宣称需检测", "《广告法》第二十八条", "补检测报告编号（如 GB/T 4745），否则删除"),
        ("抗皱", "mid", "功能性宣称需检测", "《广告法》第二十八条", "补检测报告编号，否则删除"),
        ("大牌同款", "high", "涉侵权", "《反不正当竞争法》", "删除"),
        ("原单", "high", "涉侵权", "《反不正当竞争法》", "删除"),
    ],
    "digital": [
        ("军规级", "mid", "需认证依据", "《广告法》第二十八条", "补认证标准编号（如 MIL-STD-810G），否则删除"),
        ("充电5分钟", "mid", "参数需注明条件", "《广告法》第二十八条", "注明测试条件；「充电 5 分钟通话 2 小时」需标实验室条件"),
        ("跑分第一", "high", "绝对化用语", "《广告法》第九条", "改为具体跑分数值 + 测试平台与时点"),
    ],
    "home": [
        ("除甲醛", "mid", "功效宣称需检测", "《广告法》第二十八条", "补 CMA/CNAS 检测报告编号，否则删除"),
        ("净化空气", "mid", "功效宣称需检测", "《广告法》第二十八条", "补检测报告编号，否则删除"),
        ("防螨", "mid", "功效宣称需检测", "《广告法》第二十八条", "补检测报告编号，否则删除"),
        ("食品级", "mid", "需依据", "《广告法》第二十八条", "补具体执行标准（如 GB 4806.1），否则删除"),
    ],
    "pet": [
        ("治皮肤病", "high", "宠物食品/用品不得宣称疗效", "《饲料和饲料添加剂管理条例》", "删除"),
        ("驱虫", "high", "需兽药资质", "《兽药管理条例》", "无兽药资质即删除"),
        ("处方粮", "high", "需资质", "《饲料和饲料添加剂管理条例》", "无资质即删除"),
    ],
    "finance": [],
    "education": [
        ("保过", "high", "教育培训广告禁用", "《广告法》第二十四条", "删除"),
        ("包过", "high", "教育培训广告禁用", "《广告法》第二十四条", "删除"),
        ("包上本科", "high", "教育培训广告禁用", "《广告法》第二十四条", "删除"),
        ("速成", "mid", "效果暗示", "《广告法》第二十四条", "改为课程内容与课时描述"),
        ("名师", "mid", "需资质证明", "《广告法》第二十四条", "补教师资格与职称证明，否则删除"),
    ],
    "general": [],
}

# ---------------------------------------------------------------- 品类必备提示语
# (正则, 缺失时的级别, 缺失时的说明, 依据)
REQUIRED = {
    "health_food": [
        (r"本品不能代替药物", "high", "保健食品广告必须显著标明「本品不能代替药物」", "《广告法》第十八条"),
        (r"国食健字|国食健注|食健备", "mid", "建议标注保健食品注册/备案号", "《保健食品注册与备案管理办法》"),
        (r"适宜人群|不适宜人群", "mid", "应标明适宜人群与不适宜人群", "《广告法》第十八条"),
    ],
    "medical_device": [
        (r"国械注[准进许]|械注准|械备", "high", "医疗器械广告须标注注册证编号", "《医疗器械监督管理条例》"),
        (r"械广审|广告审查", "high", "医疗器械广告须标注广告审查批准文号", "《医疗器械监督管理条例》"),
    ],
    "cosmetic_special": [
        (r"国妆特字|国妆特进字|卫妆特字", "high", "特殊化妆品须标注注册证编号", "《化妆品监督管理条例》"),
    ],
    "finance": [
        (r"风险提示|投资有风险", "high", "金融产品须有风险提示", "《广告法》第二十五条"),
    ],
}

# ---------------------------------------------------------------- 品类等级调整
# 「类别是合规规则的参数」的落地：同一组词在不同品类下等级不同。
# {品类: {词条类别: (新等级, 说明)}}
CATEGORY_ADJUST = {
    "cosmetic_special": {
        "化妆品功效宣称": (
            "notice",
            "特殊化妆品可宣称注册功效，须与注册证内容一致并标注注册证号（不得延伸为「彻底」「永久」）"),
    },
    "health_food": {
        "保健功能宣称（需保健食品资质）": (
            "mid",
            "保健食品可宣称注册功能，须与注册批件表述一致，并标明「本品不能代替药物」"),
    },
}

CATEGORIES = {
    "food": {"name": "普通食品", "reg": "《食品安全法》《广告法》§17",
             "note": "普通食品不得宣称任何保健功能或疾病预防治疗功能",
             "strong": False},
    "health_food": {"name": "保健食品", "reg": "《广告法》§18",
                    "note": "仅可宣称注册/备案的保健功能，须标「本品不能代替药物」",
                    "strong": True},
    "cosmetic": {"name": "普通化妆品", "reg": "《化妆品监督管理条例》",
                 "note": "不得宣称医疗作用；美白/祛斑/防晒/防脱/染发/烫发属特殊化妆品，需注册",
                 "strong": False},
    "cosmetic_special": {"name": "特殊化妆品", "reg": "《化妆品监督管理条例》",
                         "note": "可宣称注册功效，须标注注册证号且不得超范围",
                         "strong": True},
    "medical_device": {"name": "医疗器械", "reg": "《医疗器械监督管理条例》",
                       "note": "需注册证号 + 广告审查批准文号", "strong": True},
    "mother_baby": {"name": "母婴用品", "reg": "《广告法》§20、§40",
                    "note": "不得宣称替代母乳；婴幼儿配方乳粉不得宣称益智增智",
                    "strong": True},
    "apparel": {"name": "服饰鞋包", "reg": "《广告法》",
                "note": "成分需与实际一致；功能性宣称需检测依据", "strong": False},
    "digital": {"name": "3C数码", "reg": "《广告法》",
                "note": "参数需注明测试条件；对比数据需注明来源", "strong": False},
    "home": {"name": "家居日用", "reg": "《广告法》",
             "note": "功效类宣称需 CMA/CNAS 检测报告", "strong": False},
    "pet": {"name": "宠物用品", "reg": "《广告法》《饲料和饲料添加剂管理条例》",
            "note": "宠物食品不得宣称治疗功能", "strong": False},
    "finance": {"name": "金融产品", "reg": "《广告法》§25",
                "note": "禁止保本保收益承诺；本技能仅做风险标注，不做卖点优化",
                "strong": True},
    "education": {"name": "教育培训", "reg": "《广告法》§24",
                  "note": "不得对升学、通过考试作出保证性承诺", "strong": False},
    "general": {"name": "通用/其他", "reg": "《广告法》",
                "note": "仅应用通用红线", "strong": False},
}

LEVEL_LABEL = {
    "high": "🔴 高危",
    "mid": "🟠 中危",
    "notice": "🟡 提示",
}
LEVEL_RANK = {"high": 3, "mid": 2, "notice": 1}
LEVEL_PENALTY = {"high": 12.0, "mid": 5.0, "notice": 1.5}

DEFAULT_EXEMPT_REASON = "上下文为客观表述，不构成绝对化或功效宣称"


# ---------------------------------------------------------------- 工具函数
def cjk_len(s: str) -> int:
    """统计有效字数（中日韩字符按 1，连续拉丁字母按 1 个词算）。"""
    n = len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff]", s))
    n += len(re.findall(r"[A-Za-z]+", s))
    n += len(re.findall(r"\d+", s))
    return n


def split_sentences(text: str) -> list:
    """按句末标点与换行切句，保留标点。"""
    out = []
    for chunk in re.split(r"(?<=[。！？!?；;])", text):
        for line in chunk.split("\n"):
            for piece in re.split(r"(?<=[。！？!?])", line):
                s = piece.strip()
                if s:
                    out.append(s)
    return out


def build_lexicon(category: str) -> list:
    entries = []
    for g in GROUPS:
        ov = g.get("overrides") or {}
        for w in g["words"]:
            entries.append({
                "word": w, "level": g["level"], "cat": g["cat"],
                "basis": g["basis"], "fix": ov.get(w, g["fix"]),
            })
    for tup in CATEGORY_EXTRA.get(category, []):
        entries.append({"word": tup[0], "level": tup[1], "cat": tup[2],
                        "basis": tup[3], "fix": tup[4]})
    # 同词重复时取更严重的等级
    merged = {}
    for e in entries:
        w = e["word"]
        if w not in merged or LEVEL_RANK[e["level"]] > LEVEL_RANK[merged[w]["level"]]:
            merged[w] = e
    # 按品类调整等级：同一组词在不同类目下的合规结论不同
    adjust = CATEGORY_ADJUST.get(category, {})
    for e in merged.values():
        if e["cat"] in adjust and e["level"] != "notice":
            e["level"], e["fix"] = adjust[e["cat"]]
    # 长词优先，避免「销量第一」被「第一」抢先匹配
    return sorted(merged.values(), key=lambda x: -len(x["word"]))


def find_in_sentence(sentence: str, lexicon: list) -> list:
    """在一句中定位所有命中，返回按位置排序、去掉重叠的结果。"""
    raw = []
    for e in lexicon:
        try:
            for m in re.finditer(re.escape(e["word"]), sentence, re.IGNORECASE):
                raw.append((m.start(), m.end(), e))
        except re.error:
            continue
    # 同起点取最长，其次取更高等级
    raw.sort(key=lambda t: (t[0], -(t[1] - t[0]), -LEVEL_RANK[t[2]["level"]]))
    chosen, last_end = [], -1
    for st, en, e in raw:
        if st >= last_end:
            chosen.append((st, en, e))
            last_end = en
    return chosen


def classify_match(sentence: str, start: int, entry: dict):
    """返回 (级别, 豁免说明)。"""
    word = entry["word"]
    rules = EXEMPT.get(word)
    tail = sentence[start:]
    if rules:
        for pat in rules.get("hard", []):
            if re.match(pat, tail):
                return None, DEFAULT_EXEMPT_REASON
        for pat in rules.get("soft", []):
            if re.match(pat, tail):
                return "notice", "视上下文可能不构成违规，需人工确认"
    return entry["level"], None


def scan(text: str, category: str) -> dict:
    text = (text or "").strip()
    lexicon = build_lexicon(category)
    sentences = split_sentences(text)

    hits, exempts = [], []
    for idx, sent in enumerate(sentences, 1):
        for st, en, entry in find_in_sentence(sent, lexicon):
            level, exempt_reason = classify_match(sent, st, entry)
            if level is None:
                key = (entry["word"], sent)
                dup = next((x for x in exempts
                            if (x["word"], x["sentence"]) == key), None)
                if dup:
                    dup["count"] += 1
                else:
                    exempts.append({"word": entry["word"], "sentence": sent,
                                    "reason": exempt_reason, "count": 1})
                continue
            marked = sent[:st] + "【" + sent[st:en] + "】" + sent[en:]
            hits.append({
                "sentence_index": idx, "sentence": sent, "marked": marked,
                "word": entry["word"], "level": level,
                "level_label": LEVEL_LABEL[level], "cat": entry["cat"],
                "basis": entry["basis"], "fix": entry["fix"],
                "downgraded": level != entry["level"],
            })

    # 必备提示语缺失检查
    missing = []
    for pat, lvl, msg, basis in REQUIRED.get(category, []):
        if not re.search(pat, text):
            missing.append({"level": lvl, "level_label": LEVEL_LABEL[lvl],
                            "message": msg, "basis": basis})

    n_high = sum(1 for h in hits if h["level"] == "high")
    n_mid = sum(1 for h in hits if h["level"] == "mid")
    n_notice = sum(1 for h in hits if h["level"] == "notice")
    for m in missing:
        if m["level"] == "high":
            n_high += 1
        elif m["level"] == "mid":
            n_mid += 1
        else:
            n_notice += 1

    cri = round(min(100.0, n_high * LEVEL_PENALTY["high"]
                    + n_mid * LEVEL_PENALTY["mid"]
                    + n_notice * LEVEL_PENALTY["notice"]), 1)

    if cri == 0:
        verdict = "✅ 未发现风险，可直接发布"
    elif cri < 15:
        verdict = "🟡 建议微调"
    elif cri < 40:
        verdict = "🟠 需修改后发布"
    else:
        verdict = "🔴 不建议发布"
    if n_high and cri < 40:  # 存在高危项时至少为「需修改」
        verdict = "🟠 需修改后发布"

    return {
        "meta": {
            "category": category,
            "category_name": CATEGORIES[category]["name"],
            "regulation": CATEGORIES[category]["reg"],
            "note": CATEGORIES[category]["note"],
            "strong_regulated": CATEGORIES[category]["strong"],
            "chars": cjk_len(text),
            "sentences": len(sentences),
        },
        "hits": hits,
        "exempt": exempts,
        "missing_required": missing,
        "summary": {"high": n_high, "mid": n_mid, "notice": n_notice,
                    "cri": cri, "verdict": verdict},
        "todo_by_model": [
            "句子级误导：整句无违禁词但变相宣称了不得宣称的内容（如「用了一个月斑淡了」）",
            "对比误导：贬低同行或无依据对比（如「比某大牌好用」）",
            "证明材料核验：专利号/检测报告/销量排名/认证是否真实存在",
            "脚本与模型判定不一致时，以模型为准并在报告中说明调整理由",
        ],
    }


# ---------------------------------------------------------------- 输出
def render_md(r: dict) -> str:
    m, s = r["meta"], r["summary"]
    L = []
    L.append("# 详情页文案合规扫描")
    L.append("")
    L.append(f"- **品类**：{m['category_name']}（`{m['category']}`）")
    L.append(f"- **监管依据**：{m['regulation']}")
    L.append(f"- **字数 / 句数**：{m['chars']} / {m['sentences']}")
    if m["note"]:
        L.append(f"- **类目提示**：{m['note']}")
    if m["strong_regulated"]:
        L.append("- ⚠️ **强监管类目**：结论仅供风险参考，请以主管部门审查为准")
    L.append("")
    L.append(f"## 风险指数 CRI = {s['cri']}　→　{s['verdict']}")
    L.append("")
    L.append(f"🔴 高危 {s['high']} 处　｜　🟠 中危 {s['mid']} 处　｜　🟡 提示 {s['notice']} 处")
    L.append("")

    if r["hits"]:
        L.append("## 命中清单")
        L.append("")
        for lvl in ("high", "mid", "notice"):
            group = [h for h in r["hits"] if h["level"] == lvl]
            if not group:
                continue
            L.append(f"### {LEVEL_LABEL[lvl]}（{len(group)} 处）")
            L.append("")
            L.append("| # | 句号 | 命中 | 类别 | 依据 | 替换建议 |")
            L.append("|---|---|---|---|---|---|")
            for i, h in enumerate(group, 1):
                tag = "（已降级）" if h["downgraded"] else ""
                L.append(f"| {i} | 第 {h['sentence_index']} 句 | "
                         f"{h['word']}{tag} | {h['cat']} | {h['basis']} | {h['fix']} |")
            L.append("")
        L.append("### 命中原文定位")
        L.append("")
        for h in r["hits"]:
            L.append(f"- 第 {h['sentence_index']} 句：{h['marked']}")
        L.append("")

    if r["missing_required"]:
        L.append("## 必备提示语缺失")
        L.append("")
        L.append("| 级别 | 缺失项 | 依据 |")
        L.append("|---|---|---|")
        for x in r["missing_required"]:
            L.append(f"| {x['level_label']} | {x['message']} | {x['basis']} |")
        L.append("")

    if r["exempt"]:
        L.append("## 上下文豁免（脚本命中但不违规）")
        L.append("")
        L.append("| 词 | 次数 | 原句 | 理由 |")
        L.append("|---|---|---|---|")
        for x in r["exempt"]:
            L.append(f"| {x['word']} | {x.get('count', 1)} | "
                     f"{x['sentence'][:60]} | {x['reason']} |")
        L.append("")

    if not r["hits"] and not r["missing_required"]:
        L.append("未命中违禁词，且该品类必备提示语齐备。")
        L.append("")

    L.append("## 仍需模型复核")
    L.append("")
    for t in r["todo_by_model"]:
        L.append(f"- {t}")
    L.append("")
    L.append("> 本扫描为规则匹配，存在裁量空间，不构成法律意见。")
    return "\n".join(L)


def render_text(r: dict) -> str:
    m, s = r["meta"], r["summary"]
    L = [f"品类：{m['category_name']}　字数：{m['chars']}　句数：{m['sentences']}",
         f"CRI = {s['cri']}　{s['verdict']}",
         f"🔴{s['high']}　🟠{s['mid']}　🟡{s['notice']}", ""]
    if r["hits"]:
        L.append("命中：")
        for h in r["hits"]:
            tag = "（降级）" if h["downgraded"] else ""
            L.append(f"  [{h['level_label']}]{tag} 第{h['sentence_index']}句 "
                     f"「{h['word']}」— {h['cat']} / {h['basis']}")
            L.append(f"      → {h['fix']}")
    else:
        L.append("未命中违禁词。")
    if r["missing_required"]:
        L.append("")
        L.append("必备提示语缺失：")
        for x in r["missing_required"]:
            L.append(f"  [{x['level_label']}] {x['message']}")
    if r["exempt"]:
        L.append("")
        L.append("上下文豁免：")
        for x in r["exempt"]:
            L.append(f"  「{x['word']}」{x['reason']} ← {x['sentence'][:40]}")
    return "\n".join(L)


# ---------------------------------------------------------------- 入口
def main():
    ap = argparse.ArgumentParser(description="电商详情页文案合规扫描（确定性部分）")
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--file", help="待扫描的文本文件路径")
    src.add_argument("--text", help="直接传入文案文本")
    ap.add_argument("--category", "-c", default="general",
                    choices=sorted(CATEGORIES.keys()), help="产品类别（决定红线）")
    ap.add_argument("--format", "-f", default="md",
                    choices=["md", "text", "json"], help="输出格式")
    ap.add_argument("--score", action="store_true", help="仅输出评分摘要")
    ap.add_argument("--list-categories", action="store_true", help="列出支持的品类")
    ap.add_argument("--list-words", action="store_true", help="列出词库")
    ap.add_argument("--level", choices=["high", "mid", "notice"], help="配合 --list-words 过滤级别")
    args = ap.parse_args()

    if args.list_categories:
        print(f"{'键':<18}{'名称':<12}{'强监管':<8}说明")
        print("-" * 78)
        for k in sorted(CATEGORIES):
            c = CATEGORIES[k]
            print(f"{k:<18}{c['name']:<12}{'是' if c['strong'] else '否':<8}{c['note']}")
        return 0

    if args.list_words:
        seen, out = set(), []
        for g in GROUPS:
            if args.level and g["level"] != args.level:
                continue
            for w in g["words"]:
                if w not in seen:
                    seen.add(w)
                    out.append((w, g["level"], g["cat"]))
        for cat, tups in CATEGORY_EXTRA.items():
            if cat == "general":
                continue
            for t in tups:
                if args.level and t[1] != args.level:
                    continue
                out.append((t[0], t[1], f"{t[2]}（{CATEGORIES[cat]['name']}）"))
        for w, lv, cat in out:
            print(f"{LEVEL_LABEL[lv]:<10}{w:<14}{cat}")
        print(f"\n共 {len(out)} 条")
        return 0

    if not args.file and not args.text:
        ap.error("需要提供 --file 或 --text（或用 --list-categories / --list-words）")

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            with open(args.file, "r", encoding="gbk", errors="replace") as fh:
                text = fh.read()
    else:
        text = args.text

    result = scan(text, args.category)

    if args.score:
        s = result["summary"]
        print(json.dumps({"category": args.category, "cri": s["cri"],
                          "verdict": s["verdict"], "high": s["high"],
                          "mid": s["mid"], "notice": s["notice"]},
                         ensure_ascii=False))
    elif args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.format == "text":
        print(render_text(result))
    else:
        print(render_md(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
