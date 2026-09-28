---
name: lenovo-skill-publish
display_name: 联想开放平台技能上传
display_name_en: Lenovo Open Platform Skill Publisher
description: "把本地 WorkBuddy 技能（C:\\Users\\<user>\\.workbuddy\\skills\\*）批量打包并上传提交审核到联想开放平台 open.lenovomm.com/developer/skillcreate。用官方 CLI @lenovo-open/skill-cli（lenovoskill）走 login/package/push，绕过浏览器文件上传权限问题。当用户说「把技能上传到联想开放平台」「上传 skill 到 lenovomm」「联想天禧 Skill Gallery 上架」「lenovoskill push」时使用。不适用于 WorkBuddy 自家开放平台 open.workbuddy.cn（用 wb-open-platform-skill-publish），也不负责写技能内容本身。"
description_zh: "把本地 WorkBuddy 技能批量打包并上传提交审核到联想开放平台（open.lenovomm.com/developer/skillcreate）。走官方 CLI @lenovo-open/skill-cli 的 login/push 流程，规避浏览器文件上传权限限制。含三大硬约束的修复脚本：SKILL.md 必须在 ZIP 根目录、frontmatter 未加引号的冒号空格会解析失败、每日部署上限 20 次。当用户要「上传技能到联想开放平台」「lenovomm 上架技能」「联想天禧 Skill Gallery 提交审核」时使用。"
description_en: "Batch-package local WorkBuddy skills and submit them for review on the Lenovo Open Platform (open.lenovomm.com/developer/skillcreate) using the official CLI @lenovo-open/skill-cli (login/push), which avoids browser file-upload permission blockers. Encodes three hard platform constraints with fix scripts: SKILL.md must sit at the ZIP root, unquoted colon-space in YAML frontmatter fails parsing, and there is a 20-deployments-per-day cap. Use when asked to upload or publish skills to the Lenovo open platform or Lenovo Tianxi Skill Gallery."
category: developer-tools
version: 1.0.0
agent_created: true
---

# 联想开放平台技能上传

把 `~/.workbuddy/skills/*` 下的技能批量推到联想开放平台并提交审核。

## 平台事实（实测，2026-09）

| 项 | 值 |
| --- | --- |
| 创建页 | `https://open.lenovomm.com/developer/skillcreate` |
| 官方 CLI | `@lenovo-open/skill-cli`（命令 `lenovoskill`） |
| 命令集 | `login` / `logout` / `whoami` / `init` / `package` / `push` / `search` / `install` |
| 上传 | `lenovoskill push -zap <zip绝对路径>`（`-zrp` 为相对路径） |
| 包规范 | ZIP 须含 `SKILL.md`，**总大小 ≤ 10MB** |
| 每日上限 | **20 次部署/天**，超限报 `今日部署次数已达上限(20次)` |
| 审核状态 | 管理中心 `https://open.lenovomm.com/developer/mgmt` → 侧栏「智能体」页签，状态显示「待审核」 |
| 上架后 | 通过后进入联想天禧 Skill Gallery |

## 三大硬约束（踩坑总结）

### 坑 1：SKILL.md 必须在 ZIP 根目录

嵌套成 `<skill-name>/SKILL.md` 会被拒：

```
{"status": -2, "message": "SKILL.md 必须位于 ZIP 包的根目录下，不能放在子目录中"}
```

打包要 zip **技能目录的内容**，不是目录本身（`arcname` 相对技能目录取）。

### 坑 2：frontmatter 未加引号的「冒号+空格」会解析失败

```
{"status": -2, "message": "SKILL.md文件失败，请检查语法格式，或检查冒号空格、缩进及特殊字符"}
```

YAML 里未加引号的标量含 `": "` 会被当成第二个 key。典型是英文
`description_en: "...from a single JSON spec: emits plugin.json..."`。
修复：把该值用双引号包起来。`scripts/sanitize_and_zip.py` 会自动检测并修复。

### 坑 3：每日 20 次上限

一个账号每天只能部署 20 次。超了只能等配额重置（次日）。
`push_all.py` 检测到报错含「已达上限」会**自动熔断**——当天立即停止，
不再对后续技能空跑重试。进度写进 `push_results.json`，重跑自动跳过已成功的，
**不要**对已成功项重复 push。

大批量（>20 个）时天然要做**每日规划**：待传数 ÷ 20 = 天数，每天跑一次脚本即可，
脚本自己会推进下一批。

## 前置：CLI 安装（不要全局安装）

按环境规范禁止 `npm install -g`，装进托管 workspace：

```sh
mkdir -p "C:/Users/zw/.workbuddy/binaries/node/workspace"
cd "C:/Users/zw/.workbuddy/binaries/node/workspace"
"/c/Users/zw/.workbuddy/binaries/node/versions/22.22.2-3/npm" install @lenovo-open/skill-cli
```

运行方式（每次都要带 `NODE_PATH`）：

```sh
cd "C:/Users/zw/.workbuddy/binaries/node/workspace"
export NODE_PATH="C:/Users/zw/.workbuddy/binaries/node/workspace/node_modules"
"C:/Users/zw/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" \
  node_modules/@lenovo-open/skill-cli/dist/index.js <command>
```

## 前置：登录

`lenovoskill login` 走 OAuth，会**打开浏览器**。浏览器必须已登录联想账号
（`open.lenovomm.com` 会跳 `passport.lenovo.com`）。未登录时用 BrowserSkill 的
`bsk request-help` 请用户完成登录，**绝不代填手机号/验证码**。

登录成功后：`lenovoskill whoami` 应返回账号与 User ID。

## push 是交互式的（关键）

`push` 会依次问两个问题：

1. `? Update Notes:` —— 更新说明（自由文本）
2. `? The <name>.zip will be pushed. Please confirm whether to continue? (y/N)` —— 确认

两个坑：
- 一次性管道输入（`printf 'a\ny\n' |`）会被拼成 `ay`，**必须**在两次输入之间留
  约 8 秒间隔。
- CLI 在 stdin 仍打开时**不会退出**，所以不能只靠 `proc.wait()`；要监听输出里出现
  `Push succeeded` / `Push failed`，然后关闭 stdin 再回收进程。
  `scripts/push_all.py` 已实现这套逻辑。

## 执行步骤

1. 打包（SKILL.md 置根）：

   ```sh
   python scripts/pack_skills.py
   ```

2. 若报 YAML 解析失败，用修复版（原始技能文件不会被改动，只改暂存副本）：

   ```sh
   python scripts/sanitize_and_zip.py
   ```

3. 批量上传（结果写入 `push_results.json`，可断点续跑，触发每日上限自动熔断）：

   ```sh
   python scripts/push_all.py                      # 全部（默认搜多目录）
   python scripts/push_all.py --only name1,name2   # 指定
   python scripts/push_all.py --skip a,b           # 跳过
   python scripts/push_all.py --zips "D:/a,D:/b"   # 自定义 zip 目录（按序去重）
   python scripts/push_all.py --max 10             # 本次最多成功 10 个就停
   ```

   默认 zip 目录在脚本头部 `DEFAULT_ZIP_DIRS` 配置（按优先级排序，先出现的
   同名 zip 生效）。待传数量超过 20 时按「每天跑一次」规划，配额重置后
   继续跑即可自动推进下一批。

4. 核验收货：打开 `https://open.lenovomm.com/developer/mgmt` → 侧栏「智能体」，
   确认出现对应技能且状态为「待审核」。

## 边界

- 只驱动**用户已登录**的浏览器完成 OAuth；不碰 cookie/token/验证码。
- 提交成功 ≠ 通过审核。审核由联想平台方判定，本技能无法保证过审；
  被驳回时要按平台反馈修改 SKILL.md 后重新 push（会消耗当天的部署次数）。
- 上传前确认技能内容不含隐私或未授权内容；批量上架是公开分发行为。
