---
name: batch-expert-team-builder
display_name: 批量专家团生成器
display_name_en: Batch Expert Team Builder
description: 批量生成 WorkBuddy Team 型专家包（多角色专家团），从一份 JSON 规格一次性产出目录、plugin.json、agents/*.md、settings.json、README 与头像，并自动跑 validate/register/package。内建两条上传校验硬约束（members[].name 必填 en/zh、members[].avatar 路径必须真实存在）。
description_zh: 批量生成 WorkBuddy Team 型专家包（多角色专家团），从一份 JSON 规格一次性产出目录、plugin.json、agents/*.md、settings.json、README 与头像，并自动跑 validate/register/package。内建两条上传校验硬约束（members[].name 必填 en/zh、members[].avatar 路径必须真实存在）。
description_en: Batch-generate WorkBuddy Team-type expert packages (multi-role teams) from a single JSON spec: emits plugin.json, agents/*.md, settings.json, README and avatars, then runs validate/register/package. Bakes in two upload-validation hard rules (members[].name required with en/zh, members[].avatar path must exist).
category: 02-Engineering
version: 1.0.0
agent_created: true
---

# 批量专家团生成器

把「一批多角色专家团」写成一份 JSON 规格，一条命令产出全部可直接上传的专家包。

## 何时使用

- 用户要一次创建/转化多个专家团（Team 型，主理人 + N 名团员）。
- 需要从主题（如某行业、某赛道、某业务方向）批量生成结构化专家团。
- 已有一批专家包，需要补全头像/修复上传校验错误并重新打包。

## 关键前置事实（务必遵守）

专家包必须生成到专家目录 `$WORKBUDDY_CONFIG_DIR/plugins/marketplaces/my-experts/plugins`（默认 `~/.workbuddy/plugins/marketplaces/my-experts/plugins`），否则不会被检测到。

### 两条上传校验硬约束（踩坑总结，最易失败）

1. **`members[].name` 必须是 `{en, zh}`**。规范文档与 `init_expert.py` 模板里写的是 `displayName`，但**上传端校验要求 `name`**。只写 `displayName` 会报错：`members[0].name 的 en/zh 均为必填`。
2. **`members[].avatar` 路径必须在包内真实存在**。只生成 `avatars/team.png` 不够——每个成员的 avatar 指向各自文件时，这些文件必须真实存在，否则报错：`members[].avatar 路径 "..." 在包内不存在`。

> 本地 `validate_expert.py` **不检查**这两条，它会“通过”但上传失败。生成器必须自行保证。

### 其它要点

- `profession`（Team 型）**必须与 `displayName` 完全一致**。
- `displayDescription.zh` **必须 40–50 字**（超出/不足会告警；建议一次写到位，避免二次返工）。
- `tags` 固定 3 个、`quickPrompts` 固定 3 个，`defaultInitPrompt` = `quickPrompts[0]`。
- 主理人文件名必须是 `{team}-team-lead.md`，不能用通用 `team-lead`。
- `teamInfo.memberAgents` **不含主理人**；`members[]` **含主理人**（role=lead）。
- `settings.json` 的 `agent` 必须等于 `plugin.json` 的 `agentName`。
- Agent MD frontmatter **禁止 `tools` 字段**。
- 每团可选用 `cat` 字段单独指定 `categoryId`（覆盖命令行 `--category`）。多主题批次应分类归档：营销类 → `05-MarketingGrowth`、内容创作 → `06-ContentCreative`、平台/销售 → `07-SalesCommerce`、投资财务 → `08-FinanceInvestment`、运营人力 → `09-OperationsHR`、数据智能 → `04-DataAI`、法务合规 → `11-SecurityCompliance`、其余行业研究/咨询 → `12-IndustryConsultant`。
- **`pzh` / `pen` / 主理人职业名长度上限 10 个字符**（`len()` 计字符：中文 1 字算 1，`AI` 算 2）。超长会破坏头像排版与命名一致性，务必在生成前断言校验；常见踩坑：`AI基建与能源投资主管`（11）、`真实世界数据与效果分析师`（12）。
- 团队 `zh` 以「团」结尾；引擎生成的「领域短语」= `zh` 去掉末尾「团」，会嵌入成员 `focus` 与能力描述，因此团队名要写成可独立成句的名词短语。

### 分析框架类型（ftype）

`ftype` 决定成员 MD 的「分析框架」段落。金融类可用
`research`/`macro`/`strategy`/`quant`/`valuation`/`risk`/`flow`/`execution`；
金融以外行业另有通用类型：
`operation`（运营）、`marketing`（营销）、`policy`（政策合规）、`culture`（文化）、
`planning`（规划）、`service`（服务）、`safety`（安全应急）、`investment`（投资）、
`data`（数据）、`content`（内容）、`product`、`legal`、`security`、`tech`。
未识别的 `ftype` 会回退为通用 research 框架（不报错，但框架不够贴切）。

## 流程

```
1. 写规格 JSON（teams.json）        → references/spec-schema.md
2. 运行引擎生成+头像+校验+注册+打包  → scripts/build_teams.py
3. 审计（name/avatar/zip 三项）      → tests 见 references/upload-validation.md
4. 交付 dist/*.zip
```

### 第 1 步：规格 JSON

见 `references/spec-schema.md`。每团含：`name`(kebab)、`zh`、`en`、`desc_zh`、`desc_en`、`tags`(3×{en,zh})、`prompts`(3×[zh,en])、`lead`、`members`(每个含 id/zh/en/pzh/pen/focus/ab/ftype)。

### 第 2 步：运行引擎

```bash
python build_teams.py teams.json
# 可选：--category 08-FinanceInvestment --plugins <dir> --dist <dir> --colors auto
```

引擎会：建目录 → 写 plugin.json/settings.json/agents/*.md/README.md → 用 Pillow 生成 team.png + 每成员头像 → 逐个 validate/register/package。

> 需 Pillow：`<managed-python> -m venv <env> && <env>/Scripts/pip install Pillow`。

### 第 3 步：审计

对每个包检查：`members[].name` 有 en/zh、`members[].avatar` 与顶层 `avatar` 文件存在、dist 下 zip 存在。脚本见 `references/upload-validation.md`。

## 超大规模批次（100+ 团）：用「规格编译器」而非手写全量规格

手写几百个团的完整 JSON（每团含 3 名成员 × 3 项能力）体积巨大且极易出错。**已验证可行**的模式是两层规格编译：

1. **方向层**：每个方向一个 JSON（`dir_dNN.json`），含 `prefix`/`zh`/`en`/`tag_zh`/`tag_en`/`lead{pzh,pen}`/`specifics[5]`/`subs[30]`。
   - `subs` 每项只写 `[slug, zh团队名, en团队名]`，**不写** slug 前缀（编译器拼 `prefix-`）。
   - `specifics` 是该方向独有的 5 个角色原型（id/pzh/pen/focus/ab/ftype）。
2. **编译器层**：代码内放 10 个跨方向通用的「视角」原型（市场规模/竞争格局/商业模式/估值/政策/技术路线/需求买方/风险尽调/产业生态/融资退出），与方向的 5 个专有原型合成 15 个角色的池子，再为每个子主题挑 3 个不重复角色（组合枚举后按步长取 30 个，保证 ≥1 专有、≤2 专有）。
   - 模板里的 `{d}` 占位符替换为团队领域短语，让同一原型在不同团队下读出不同内容——这是「量」与「质」兼顾的关键。
   - 花名用确定性随机（`random.Random(seed).sample(range(TOTAL), N)` 后按混合进制解码）批量生成，天然全局不重名。
   - `desc_zh` 用「开头 × 中段 × 结尾」片段交叉搜索，取长度落在 40–50 的首个组合，杜绝告警返工。
3. **性能**：头像渐变底图按配色缓存（48×48 生成后 `resize` 放大），不要每张重算 512² 像素；注册改为一次性读 `marketplace.json` → 内存批量 upsert → 一次写回（不要逐包调 `register_expert.py`）；校验用 `importlib` 加载 `validate_expert.py` 在进程内逐个调用（不要起 3×N 个子进程）。

实测：450 个团（1,800 角色 / 2,250 头像）全程约 25 秒完成生成+头像+校验+注册+打包，校验 0 错误 0 告警。

## 交付 100+ 包

`present_files` 逐个列几百个 zip 不现实。做法：生成一个 HTML 总览页（按方向分组、列出每团名称/描述/成员/首条推荐问法）+ 一个「合集 zip」（ZIP_STORED，内含全部单包，命名标明**仅供下载、勿直接上传**），再附少量代表性单包。同时说明：**上传仍须逐个提交 `dist/<slug>.zip`**。

## 头像

`gen_avatars.py` 用 Pillow 生成统一风格头像：团队徽标（团队名）+ 成员头像（白底圆 + 姓名首字 + 职业），每团一套配色，512×512 PNG。纯本地生成、零外部调用、100% 落地，避免 ImageGen 失败/命名不可控导致的上传失败。

如需 AI 人像风格，可改用 `ImageGen` 逐张生成并**核对文件名与路径确实存在**后再打包。

## References

- `references/spec-schema.md` — 规格 JSON 字段与示例
- `references/upload-validation.md` — 上传校验清单与两条硬约束
- `scripts/build_teams.py` — 批量生成引擎
- `scripts/gen_avatars.py` — 头像生成器
