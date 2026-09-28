#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-build WorkBuddy Team-type expert packages from a JSON spec.

Usage:
    python build_teams.py teams.json [--category 08-FinanceInvestment] [--plugins DIR] [--dist DIR]

Spec: a JSON array of team objects (see references/spec-schema.md).

Bakes in the two upload-validation hard rules:
  1. members[].name MUST be {en, zh}
  2. members[].avatar paths MUST physically exist in the package
"""
import os, json, sys, subprocess, shutil, argparse

FONT_CANDIDATES = [
    'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
]

FRAMEWORK = {
    'research':  ["界定问题与范围，明确关键变量", "多源数据交叉验证，剔除噪音", "形成结论、置信度与跟踪指标"],
    'macro':     ["解读政策与数据，识别预期差", "推演传导链条与时间路径", "映射到相关资产的配置含义"],
    'strategy':  ["判定当前状态与所处阶段", "构建基准/乐观/悲观情景假设", "给出策略、仓位建议与失效条件"],
    'quant':     ["构造信号与因子暴露", "样本内外回测，评估收益/回撤/换手", "稳健性与过拟合检验，标定参数区间"],
    'valuation': ["明确核心假设与预测口径", "搭建模型并计算价值区间", "做敏感性与情景分析，给出安全边际"],
    'risk':      ["识别主要风险敞口与相关性", "量化度量（极端情景/回撤）", "给出风险预算、缓释与止损建议"],
    'flow':      ["采集资金/筹码/活跃度数据", "拆解结构与边际变化", "判断资金意图与潜在反转信号"],
    'execution': ["拆解成本、滑点与流动性", "设计执行方案与仓位规则", "纪律复核与事后归因"],
    'tech':      ["理解机制与技术架构", "评估性能、可行性与安全", "给出技术判断与采用路径"],
    'token':     ["拆解供需、释放与解锁", "分析激励设计与价值捕获", "给出估值区间与风险提示"],
    'defi':      ["解析协议机制与收益来源", "评估合约/清算/脱锚风险", "给出策略与风险控制建议"],
    'dev':       ["明确技术目标与约束", "设计架构与实现路径", "评估成本、可行性与风险"],
    'security':  ["识别攻击面与薄弱环节", "验证漏洞可利用性与影响", "给出修复与防护建议"],
    'legal':     ["梳理适用法规与监管口径", "评估合规义务与牌照路径", "给出合规方案与风险提示"],
    'product':   ["明确用户与场景", "设计功能与体验路径", "评估价值、成本与风险"],
    # --- 通用/行业域（非金融专用）---
    'operation': ["梳理资源、流程与关键环节", "识别瓶颈与效率/体验提升点", "给出运营方案与量化目标"],
    'marketing': ["明确目标人群与竞争位置", "设计内容、渠道与投放组合", "设定预算、指标与效果归因"],
    'policy':    ["梳理政策依据与监管口径", "评估合规义务与落地约束", "给出合规路径与风险提示"],
    'culture':   ["挖掘文化内核与可体验要素", "转化为产品、内容与场景", "评估文化真实性与商业可持续性"],
    'planning':  ["开展资源普查与条件评估", "确立定位、结构与功能布局", "给出分期路径、投资测算与风险"],
    'service':   ["拆解服务触点与体验旅程", "建立标准、培训与质量管控", "设定满意度指标与改进闭环"],
    'safety':    ["识别风险源与高危场景", "评估发生概率与后果等级", "给出预案、演练与应急联动方案"],
    'investment':["明确投资逻辑与收益结构", "搭建现金流与回收期测算", "做情景与敏感性分析，给出退出路径"],
    'data':      ["确定口径、指标与数据来源", "建模分析并检验稳健性", "输出结论、看板与预警阈值"],
    'content':   ["明确受众与平台特性", "设计选题、脚本与呈现节奏", "设定发布策略与转化路径"],
}
DEFAULT_FW = FRAMEWORK['research']

DEFAULT_COLORS = [(35,120,180),(247,147,26),(98,126,234),(20,160,140),(120,60,200),(230,90,90),
                  (0,150,200),(150,120,40),(60,170,90),(190,80,160),(40,90,140),(210,130,30),
                  (70,70,180),(0,130,120),(160,60,60),(100,110,20),(30,150,170),(130,80,180),
                  (200,100,60),(60,140,200),(110,60,120),(0,110,90),(170,140,60),(80,120,60),
                  (200,70,120),(50,100,170),(140,100,40),(90,60,160),(0,140,110),(180,90,90)]

AUTHOR = {"name": "WorkBuddy User", "email": "user@workbuddy.local"}


def find_font():
    for f in FONT_CANDIDATES:
        if os.path.isfile(f):
            return f
    return None


def find_scripts_dir():
    cands = [
        'D:/workbuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts',
        os.path.expanduser('~/.workbuddy/plugins/workbuddy-builtin/skills/expert-manager/scripts'),
    ]
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


def member_md(t, m):
    steps = FRAMEWORK.get(m.get('ftype', 'research'), DEFAULT_FW)
    ab = "\n".join(f"{i+1}. **{a[0]}**：{a[1]}" for i, a in enumerate(m['ab']))
    fw = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
    return f'''---
name: {m['id']}
description: "{m['pen']}: delivers focused, structured analysis to the team lead."
displayName:
  en: "{m['en']}"
  zh: "{m['zh']}"
profession:
  en: "{m['pen']}"
  zh: "{m['pzh']}"
maxTurns: 60
---

# {t['zh']} - {m['zh']}（{m['pzh']}）

我是{m['zh']}，{t['zh']}的{m['pzh']}。{m['focus']}

## 核心能力
{ab}

## 分析框架
{fw}

## 输出规范
- 结论先行：先给判断与置信度（高/中/低），再给依据
- 数据支撑：列出关键数据、指标与口径，标注数据时点
- 结构化呈现：使用表格或分层要点，便于主理人汇编
- 明确风险：给出反面情景与结论失效条件

## 注意事项
- 只做研究与决策支持，不构成投资建议；提示数据时效与假设前提
- 结论需可被主理人直接引用与汇编

## SendMessage 回传
分析完成后，**必须通过 SendMessage 将完整分析结果回传给主理人**。
'''


def lead_md(t):
    rows = "\n".join(f"| {m['id']} | {m['zh']} | {m['pzh']}：{m['focus']} |" for m in t['members'])
    routing = "\n".join(f"| 涉及「{m['pzh']}」的问题 | `{m['id']}` |" for m in t['members'])
    ph = "\n".join(f"- `{m['id']}` → {m['pzh']}" for m in t['members'])
    return f'''---
name: {t['name']}-team-lead
description: "Team lead orchestrating the {t['en']}."
displayName:
  en: "{t['lead']['en']}"
  zh: "{t['lead']['zh']}"
profession:
  en: "{t['lead']['pen']}"
  zh: "{t['lead']['pzh']}"
maxTurns: 180
---

# {t['zh']} - 主理人

我是{t['lead']['zh']}，{t['zh']}的主理人（{t['lead']['pzh']}）。我负责编排团队，组织独立分析、交叉质询并汇总成可决策的结论。{t['desc_zh']}

## 团队成员

| 成员 ID | 名字 | 职责 |
|---------|------|------|
| {t['name']}-team-lead | {t['lead']['zh']} | 编排调度、交叉质询、最终汇编 |
{rows}

## 单 Agent 直调路由表

| 问法类型 | 直接调谁 |
|---------|---------|
{routing}
| 综合性问题 | 走下方预设 Workflow |

## 标准工作流程（SOP）

### Phase 1: 并行取证（并行）
同一消息内 spawn 三名成员，分别从各自维度独立分析，产出结构化结论：
{ph}

### Phase 2: 交叉质询与补证（串行）
汇总 Phase 1 结论，识别分歧与缺口，将争议点定向回传相应成员补充论证。

### Phase 3: 最终报告
综合所有成员结论，生成最终报告：结论与置信度、关键依据、情景与风险、可执行建议与失效条件。

## 团队协作机制（铁律）

1. **建立团队**：任务开始时由主理人亲自创建团队（TeamCreate）。**团队创建必须且只能由主理人执行，严禁委派任何成员创建团队**
2. **调度成员**：按 SOP 阶段将成员拉入协作、下发独立任务；成员作为独立协作方输出专业产出，不得由主理人代写
3. **消息中转**：成员产出回传给主理人，由主理人汇总、转交下一阶段；所有跨成员信息流必须经主理人中转，不得互相直连
4. **成员结论为准**：任何专业产出必须由对应成员输出后再采信，主理人只做编排与汇编

### 严禁行为
- ❌ 禁止跳过 TeamCreate，直接自己模拟成员发言或并行写出多角色内容
- ❌ 禁止自己代写任何团队成员的专业产出
- ❌ 禁止未完成前序阶段就跳到后续阶段
- ❌ 禁止让成员互相直连通信
- ❌ 禁止 spawn 主理人自己

## 协作规则
1. 所有成员调度必须经过"建立团队 → 调度成员 → 成员回传"流程
2. 每阶段结束后，将完整产出原文传递给下一阶段成员
3. 每完成一个阶段向用户简要通报
4. 所有输出使用与用户原始需求相同的语言
5. 调度成员时，Agent 工具的 `name` 参数传入成员的 **Agent ID**（MD 文件名，不含 .md），`subagent_type` 也传入相同值
'''


def readme_md(t):
    return f'''# {t['zh']}（{t['en']}）

{t['desc_zh']}

## 类型

Team 型（多角色协作专家团），含主理人 1 名 + 团员 {len(t['members'])} 名。

## 团队成员

| 成员 ID | 名字 | 职业 |
|---------|------|------|
| {t['name']}-team-lead | {t['lead']['zh']} | {t['lead']['pzh']} |
''' + "".join(f"| {m['id']} | {m['zh']} | {m['pzh']} |\n" for m in t['members']) + f'''
## 使用示例

- {t['prompts'][0][0]}
- {t['prompts'][1][0]}
- {t['prompts'][2][0]}

## 头像

头像已生成在 `avatars/` 目录下（团队徽标 + 各成员头像）。
'''


def plugin_json(t, category):
    members = [{
        "id": f"{t['name']}-team-lead",
        "name": {"en": t['lead']['en'], "zh": t['lead']['zh']},
        "profession": {"en": t['lead']['pen'], "zh": t['lead']['pzh']},
        "avatar": f"avatars/{t['name']}-team-lead.png", "role": "lead",
    }]
    for m in t['members']:
        members.append({
            "id": m['id'],
            "name": {"en": m['en'], "zh": m['zh']},
            "profession": {"en": m['pen'], "zh": m['pzh']},
            "avatar": f"avatars/{m['id']}.png", "role": "member",
        })
    return {
        "name": t['name'], "version": "1.0.0", "description": t['desc_en'],
        "author": AUTHOR,
        "agents": [f"./agents/{t['name']}-team-lead.md"] + [f"./agents/{m['id']}.md" for m in t['members']],
        "expertType": "team", "agentName": f"{t['name']}-team-lead",
        "teamInfo": {"leadAgent": f"{t['name']}-team-lead", "memberAgents": [m['id'] for m in t['members']]},
        "displayName": {"en": t['en'], "zh": t['zh']},
        "profession": {"en": t['en'], "zh": t['zh']},
        "displayDescription": {"en": t['desc_en'], "zh": t['desc_zh']},
        "avatar": "avatars/team.png", "categoryId": t.get('cat', category),
        "defaultInitPrompt": {"zh": t['prompts'][0][0], "en": t['prompts'][0][1]},
        "plugin": t['name'],
        "tags": [{"en": a, "zh": b} for a, b in t['tags']],
        "quickPrompts": [{"zh": p[0], "en": p[1]} for p in t['prompts']],
        "members": members,
    }


def build_avatars(font_path):
    from PIL import Image, ImageDraw, ImageFont
    cache = {}

    def F(sz):
        if sz not in cache:
            cache[sz] = ImageFont.truetype(font_path, sz)
        return cache[sz]

    def grad(c1, c2, size=(512, 512)):
        img = Image.new('RGB', size); px = img.load(); w, h = size
        for y in range(h):
            tt = y / (h - 1)
            r = int(c1[0] + (c2[0] - c1[0]) * tt); g = int(c1[1] + (c2[1] - c1[1]) * tt); b = int(c1[2] + (c2[2] - c1[2]) * tt)
            for x in range(w):
                px[x, y] = (r, g, b)
        return img

    def wrap(s, n):
        return [s[i:i + n] for i in range(0, len(s), n)] or [s]

    def team_png(path, color, name):
        img = grad(color, tuple(max(0, c - 50) for c in color)); d = ImageDraw.Draw(img)
        lines = wrap(name, 5); total = len(lines); sy = 256 - (total - 1) * 44
        for i, ln in enumerate(lines):
            d.text((256, sy + i * 88), ln, font=F(76), fill=(255, 255, 255), anchor='mm')
        img.save(path, 'PNG')

    def member_png(path, color, initial, role):
        img = grad(color, tuple(max(0, c - 50) for c in color)); d = ImageDraw.Draw(img)
        cx, cy, r = 256, 188, 118
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
        d.text((cx, cy), initial, font=F(120), fill=color, anchor='mm')
        d.text((256, 372), role[:9], font=F(34), fill=(255, 255, 255), anchor='mm')
        img.save(path, 'PNG')

    return team_png, member_png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spec')
    ap.add_argument('--category', default='08-FinanceInvestment')
    ap.add_argument('--plugins', default=os.path.expanduser('~/.workbuddy/plugins/marketplaces/my-experts/plugins'))
    ap.add_argument('--dist', default='./dist')
    ap.add_argument('--python', default=sys.executable)
    args = ap.parse_args()

    teams = json.load(open(args.spec, encoding='utf-8'))
    os.makedirs(args.dist, exist_ok=True)
    font_path = find_font()
    scripts = find_scripts_dir()
    if not font_path:
        print("WARN: no CJK font found; avatars may render without Chinese"); 
    team_png, member_png = build_avatars(font_path) if font_path else (None, None)
    colors = DEFAULT_COLORS

    built = []
    for i, t in enumerate(teams):
        d = os.path.join(args.plugins, t['name'])
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(os.path.join(d, '.codebuddy-plugin'))
        os.makedirs(os.path.join(d, 'agents'))
        os.makedirs(os.path.join(d, 'avatars'))
        json.dump(plugin_json(t, args.category),
                  open(os.path.join(d, '.codebuddy-plugin', 'plugin.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        open(os.path.join(d, 'settings.json'), 'w', encoding='utf-8').write(
            json.dumps({"agent": f"{t['name']}-team-lead"}, ensure_ascii=False) + "\n")
        open(os.path.join(d, 'agents', f"{t['name']}-team-lead.md"), 'w', encoding='utf-8').write(lead_md(t))
        for m in t['members']:
            open(os.path.join(d, 'agents', f"{m['id']}.md"), 'w', encoding='utf-8').write(member_md(t, m))
        open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(readme_md(t))
        if team_png:
            color = colors[i % len(colors)]
            av = os.path.join(d, 'avatars')
            team_png(os.path.join(av, 'team.png'), color, t['zh'].replace('团', '') or t['zh'])
            member_png(os.path.join(av, f"{t['name']}-team-lead.png"), color, t['lead']['zh'][0], t['lead']['pzh'])
            for m in t['members']:
                member_png(os.path.join(av, f"{m['id']}.png"), color, m['zh'][0], m['pzh'])
        built.append(t['name'])
    print(f"Built {len(built)} teams")

    # audit: the two hard rules
    bad = []
    for t in teams:
        d = os.path.join(args.plugins, t['name'])
        pj = json.load(open(os.path.join(d, '.codebuddy-plugin', 'plugin.json'), encoding='utf-8'))
        if not os.path.isfile(os.path.join(d, pj['avatar'])):
            bad.append((t['name'], 'team avatar missing'))
        for m in pj['members']:
            if not (m.get('name', {}).get('en') and m.get('name', {}).get('zh')):
                bad.append((t['name'], m['id'], 'name'))
            if not os.path.isfile(os.path.join(d, m['avatar'])):
                bad.append((t['name'], m['id'], 'avatar'))
    if bad:
        print("AUDIT FAILED:", bad)
        sys.exit(2)
    print("Audit OK: name/avatar all present")

    if not scripts:
        print("WARN: expert-manager scripts not found; skip validate/register/package")
        return
    ok, fail = [], []
    for name in built:
        d = os.path.join(args.plugins, name)
        for script, extra in (('validate_expert.py', []), ('register_expert.py', []),
                              ('package_expert.py', [args.dist])):
            r = subprocess.run([args.python, os.path.join(scripts, script), d] + extra,
                               capture_output=True, text=True)
            if r.returncode != 0:
                fail.append((name, script, (r.stdout + r.stderr)[-800:])); break
        else:
            ok.append(name)
    print(f"OK {len(ok)}/{len(built)}")
    for f in fail:
        print("FAIL:", f[0], f[1]); print(f[2])


if __name__ == '__main__':
    main()
