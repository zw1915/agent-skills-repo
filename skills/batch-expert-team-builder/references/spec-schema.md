# 规格 JSON 字段说明

`build_teams.py` 接受一个 JSON 数组，每个元素描述一个专家团。

## 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | kebab-case 唯一标识，也是目录名，如 `layer1-chains` |
| `zh` | string | 团队中文名（建议以「团」结尾） |
| `en` | string | 团队英文名 |
| `desc_zh` | string | 团队中文描述（**40–50 字**，不足会被校验告警） |
| `desc_en` | string | 团队英文一句话描述 |
| `cat` | string | 可选。团队级 `categoryId`，覆盖命令行 `--category` |
| `tags` | `[ [en, zh], [en, zh], [en, zh] ]` | 固定 3 个 |
| `prompts` | `[ [zh, en], [zh, en], [zh, en] ]` | 固定 3 条；第一条即 defaultInitPrompt |
| `lead` | object | 主理人 `{zh, en, pzh, pen}` |
| `members` | array | 3 名团员（可增减） |

## lead / member 字段

| 字段 | 说明 |
|------|------|
| `zh` | 中文花名（2–3 字，谐音巧思，像人名，不重复于职业） |
| `en` | 英文名（拼音姓氏） |
| `pzh` | 中文职业头衔（主理人避免「团长/主理人」通用词） |
| `pen` | 英文职业头衔 |
| `id` | 仅 member：kebab-case Agent ID，= MD 文件名 |
| `focus` | 一句话擅长（写进 MD 正文） |
| `ab` | `[ [能力名, 说明] × 3 ]` |
| `ftype` | 分析框架类型：`research`/`macro`/`strategy`/`quant`/`valuation`/`risk`/`flow`/`execution`/`tech`/`token`/`defi`/`dev`/`security`/`legal`/`product`；非金融行业可用 `operation`/`marketing`/`policy`/`culture`/`planning`/`service`/`safety`/`investment`/`data`/`content` |

## 示例

```json
[
  {
    "name": "layer1-chains",
    "zh": "L1公链研究团",
    "en": "Layer-1 Chains Research Desk",
    "desc_zh": "研究主流L1公链的共识机制、经济模型、性能与生态，评估其长期价值与竞争格局。",
    "desc_en": "Researches consensus, economics, performance and ecosystems of major L1 chains.",
    "tags": [["L1","L1"],["Chains","公链"],["Consensus","共识"]],
    "prompts": [
      ["对比以太坊、Solana等主流公链的长期价值","Compare the long-term value of major L1s."],
      ["分析某条公链的代币经济与通胀模型","Analyze a chain's token economics."],
      ["评估L1赛道的竞争格局与风险","Assess the L1 sector's competitive landscape."]
    ],
    "lead": {"zh":"童链远","en":"Tong","pzh":"公链研究主编","pen":"L1 Research Editor"},
    "members": [
      {"id":"consensus-analyst","zh":"龚识严","en":"Gong","pzh":"共识机制分析师","pen":"Consensus Analyst",
       "focus":"剖析共识机制的安全性、去中心化与性能取舍。",
       "ab":[["共识机制比较","..."],["去中心化与安全","..."],["性能与最终性","..."]],"ftype":"tech"}
    ]
  }
]
```

## 约束提醒

- `profession`（Team）自动等于 `displayName`（引擎已保证）。
- `members[].name` 由引擎写成 `{en, zh}`，**不要**改成 `displayName`。
- 每名成员的头像文件由引擎生成，路径必须是 `avatars/{id}.png`。
