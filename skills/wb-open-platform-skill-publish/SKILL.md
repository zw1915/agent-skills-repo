---
name: wb-open-platform-skill-publish
display_name: 开放平台技能批量上传
display_name_en: WorkBuddy Open Platform Skill Publisher
description: "借助 BrowserSkill(bsk) 驱动用户已登录的浏览器，把一批技能 zip 逐个上传到 WorkBuddy 开放平台(open.workbuddy.cn)并提交审核。当用户要求「把技能上传/发布到开放平台」「批量提交 skill zip」「上架技能到 WorkBuddy 市场」「publish skills to open.workbuddy.cn」时使用。不适用于本地安装技能（用 marketplace-skill-installer/本地 skills 目录复制），也不负责写技能内容本身。"
description_zh: "借助 BrowserSkill(bsk) 驱动用户已登录的浏览器，把一批技能 zip 逐个上传到 WorkBuddy 开放平台(open.workbuddy.cn)并提交审核。当用户要求「把技能上传/发布到开放平台」「批量提交 skill zip」「上架技能到 WorkBuddy 市场」「publish skills to open.workbuddy.cn」时使用。"
description_en: "Publish skill zips to the WorkBuddy Open Platform (open.workbuddy.cn) in bulk by driving the user's logged-in browser via BrowserSkill (bsk). Use when asked to upload/publish/submit skills or zips to the open platform. Not for local skill installation."
category: writing
version: 1.0.0
author: 梁樱萍
agent_created: true
---

# 开放平台技能批量上传

用 BrowserSkill(`bsk`) 复用用户已登录的浏览器会话，逐个上传技能 zip 到
`https://open.workbuddy.cn/skill/all` 并提交审核。

## 前置：平台事实（已实测）

| 项 | 值 |
| --- | --- |
| 技能列表页 | `https://open.workbuddy.cn/skill/all` |
| 直接创建页 | `https://open.workbuddy.cn/skill/publish?action=create&step=1` |
| zip 规范 | 根目录 `{skill-name}/SKILL.md`；≤3MB；frontmatter 需含 `author`（合作方名称） |
| 三步流程 | ① 上传 zip（平台**自动开包**并生成技能ID `os_xxxxxxxx`）② 完善信息 ③ 提交审核 |
| 第2步必填 | **市场展示分类**（combobox，4 选 1）+ **服务类目**（button，两级 父→子） |
| 市场展示分类 | 选项仅 4 个：`办公协同 / 开发工具 / 效率工具 / 内容创作`。**均为个人账号可发**，无企业资质门槛。属**多选**控件，选完按 Escape 收起 |
| 服务类目 | 顶层含 `工具`，其**子项只有**：记账/日历/天气/办公/图片处理/计算器/报价·比价/信息查询/预约·报名/健康管理/备忘录。**没有「开发工具」子项**，所以通用解法是「工具 → 办公」 |
| 自动解析 | 市场展示名称 / 能力介绍 / 版本号 由 zip 解析，无需手填 |
| 成功提示 | 「已提交审核，预计 7 个工作日出结果」 |
| 列表分页 | 滚动/分页加载，每屏 20 条 |

> **关键坑**：每次用「点列表页『创建』按钮」进入表单，容易因 SPA 尚未 hydration 而点空
> （表现为找不到上传按钮）。**每轮直接 `navigate` 到创建页 URL 最稳**。

### 关键坑 2：向导会把你钉在上一个资产上（批量发布必读）

平台把「当前资产」存在 **sessionStorage** 的 `wb.open.publication.draft`
（含 `assetId` 与 `submitResult`）。**提交成功后它不会被清空**，于是下一轮无论
`navigate` 创建页、点列表「创建」还是 `reload`，向导都仍绑定在刚提交的资产上，
上传新包会被当成「改名」而失败：

```
解析失败：包内 name "X" 与当前资产的 name "Y" 不一致
```

解法 —— **每个资产开头必做**（先落创建页，再清 key，再重载）：

```sh
bsk navigate "<create-url>" --session <id>
bsk evaluate --session <id> "sessionStorage.removeItem('wb.open.publication.draft'); 'ok'"
bsk reload --session <id>
```

### 关键坑 3：不要用「专家ID / 技能ID」判断解析完成

创建页静态提示语本身就写着「…自动开包解析并生成专家ID/技能ID」，
所以「页面包含 专家ID」**在空表单上也恒成立**，会误判为已解析，
接着找「继续」按钮时它还是 `[disabled]`。

正确信号：等真正的 ID 正则 —— 专家 `oe_[0-9a-zA-Z]{8,}`，技能 `os_[0-9a-zA-Z]{8,}`。
同时检查是否出现「解析失败」并即时报错。

### 关键坑 4：上传失败不要盲目重试

包名（plugin.json 的 `name`）**提交一次就被服务端占用**。若首传其实成功、
只是 UI 回显慢，重试会撞上：

```
解析失败：专家名称 "X" 已被占用
```

此时把 `name` 与 `plugin` 两个字段一起改成新的唯一 slug 再重新打包即可
（展示名 `displayName`/`profession` 保持不变，用户无感）。
**不要**对同一个包连续 upload 两次。

### 关键坑 5：上传必须用 `--mode drop`

该上传器是**拖拽式**（「点击或拖拽上传代码包」），不是原生 `input[type=file]`。
用默认 `--mode input` 会报：

```
upload trigger did not activate an input[type=file]
```

即使 ref 找对了、按钮也点了，照样失败。正确写法：

```sh
bsk upload @e18 --file <zip绝对路径> --mode drop --session <id>
```

**成功判定的坑**：`input` 模式成功回 `upload ok ...`；`drop` 模式成功回的是
JSON `{"tab_id":...,"used_ref":"e18","file_names":["xxx.zip"]}`，**不含** `upload ok`。
所以判定要写 `'"file_names"' in out or 'upload ok' in out`，只认 `upload ok` 会误判全失败。

### 关键坑 6：observe 出的元素文本常带 `[has-submenu]` 后缀

下拉类元素在 observe 里长这样，引号内**不是**纯文本：

```
@e20 combobox "请选择 [has-submenu]" ="请选择"
@e23 button   "请选择 [has-submenu]"
```

所以按 `combobox "请选择"` 这种「带闭合引号」的精确匹配会**匹配不到**。
必须用子串/前缀匹配（本技能脚本的 `find_ref(..., exact=False)` 正确；
自己写 bash 时要用 `grep -E "@e[0-9]+ ${role} \"${text}"`，**不要**加结尾引号）。

### 关键坑 7：每日上传上限 100 次

平台限制**每个账号每天最多 100 次上传**，超出报：

```
解析失败： 您今日的上传次数已达到 100 次上限，请明日再来
```

大批量时给失败重传留余量；**草稿续提不算上传**（见坑 8），限额用完后仍可救回已上传未提交的资产。

### 关键坑 8：上传中断的资产变「草稿」，可从列表续提（不需重传）

第 1 步上传成功但第 2/3 步失败的包，会以「草稿」状态留在列表页
（列表 → 筛选 → 草稿 → 点「编辑」回到向导续提）。要点：

- **草稿不保留已填类目**，重新打开时两个类目常常都是空的，需重填。
- 草稿编辑态（URL 带 `entry=2`）UI 会**降级**：市场展示分类 combobox、服务类目
  「请选择」按钮常常 observe 不到，只剩 LabelText。此时用 JS 派发完整事件序列
  （React 不认裸 `.click()`，必须 pointer+mouse 全套）：

  ```js
  const t=[...document.querySelectorAll('div.flex.min-h-10')]
    .filter(e=>e.offsetParent&&e.textContent.trim()==='请选择')[0];
  ['pointerover','pointerdown','mousedown','pointerup','mouseup','click']
    .forEach(ty=>{const E=ty.startsWith('pointer')?PointerEvent:MouseEvent;
      t.dispatchEvent(new E(ty,{bubbles:true,cancelable:true,view:window,button:0}))});
  ```

  唤出下拉后选项是正常 button、可回到 ref 点击流程。注意分清市场/服务两个
  下拉（市场在此模式下会显示**全部 13 个选项**，含投资理财等疑似需资质类目——
  别误选）。残留浮层会挡住后续点击，Escape 关不掉时直接用 JS 派发（不受遮挡影响）。

- 同理，任何「元素在 DOM 里但 observe 不显示/点击被浮层挡住」的情况，
  都可以用上面的事件序列模板点 `<button>`。

### 关键坑 9：`browser did not become ready for native input` 是瞬时抖动

bsk 偶发报此错误（尤其连续快速操作时），**不是页面坏了**。处理：sleep 2~3s →
重新 observe → 重试 click，一般 1~2 次即过。批量脚本里每个 click 都应带重试。

## 进阶：发布专家（expert）

与技能同构，端点与分类不同：

| 项 | 值 |
| --- | --- |
| 创建页 | `https://open.workbuddy.cn/expert/publish?action=create&step=1` |
| 列表页 | `https://open.workbuddy.cn/expert/all` |
| ID 前缀 | `oe_xxxxxxxx` |
| zip 结构 | `plugin.json` + `agents/*.md` + `avatars/expert.png`(512×512, ≤500KB) + `skills/*/SKILL.md` |
| 市场展示分类 | combobox，按 `categoryId` 选：09→运营人力、12→行业顾问、08→金融投资、06→内容创作、11→法务安全 |
| 服务类目 | button「请选择」→ 工具 → 办公（得到「工具 - 办公」） |

第 2 步中「市场展示分类」**不会自动填充**，必须手填；职称/花名/能力介绍/示例问题/
擅长领域/版本号均由包解析。市场展示分类是 combobox、服务类目是 button，
两者初始都显示「请选择」，靠 role 区分；选完分类按 Escape 收起下拉再点下一个。

### 进阶：发布专家团（team）——两个文档没写的必填项

团队与单专家的端点相同，plugin.json 在单专家基础上改为：

```json
{
  "expertType": "team",
  "agentName": "<lead>",                       // 主理人
  "teamInfo": { "leadAgent": "<lead>",
                "memberAgents": ["成员A", "成员B"] },   // 不含 lead
  "members": [                                  // ★ 必填数组，文档未写！
    { "id": "<lead>",   "name": {"en","zh"}, "profession": {"en","zh"},
      "avatar": "avatars/<lead>.png", "role": "lead" },
    { "id": "<成员A>",  "name": {"en","zh"}, "profession": {"en","zh"},
      "avatar": "avatars/<成员A>.png", "role": "member" }
  ]
}
```

- **插件根目录必须提供 `settings.json`**，内容 `{"agent": "<lead>"}`
  （平台校验报错原文：「Team 型专家必须在 plugin root 下提供 settings.json」）。
- **每个成员都要有独立头像文件** `avatars/<agent名>.png`；团队头像 `avatars/expert.png` 仍是 `avatar` 字段入口。
- 其余校验与单专家一致：displayDescription.zh 40–50 字、tags=3、quickPrompts=3、
  defaultInitPrompt==quickPrompts[0]、name 全局唯一（小写+连字符）。
- 成员 agent md 需要 frontmatter：name/description/displayName{en,zh}/profession{en,zh}/maxTurns。

## 前置：BrowserSkill 环境

1. 守护进程常驻：`bsk daemon start --foreground`（放进持久后台任务；Windows 亦如此）。
2. **每条**沙箱命令都带 `BSK_AUTO_START=0`（环境不跨命令保留）。
3. `bsk status --json` 确认 `browsers` 里有扩展已连接的浏览器。
4. 多浏览器在线时必须 `bsk session start --browser <instance_id> --json` 指定；记下 `session_id`。

## 执行：批量脚本

本技能自带脚本 `scripts/upload_skills.py`（用法 `python upload_skills.py <start> <count>`）。
它按 ref 解析 `bsk observe` 输出、动态找元素，逐个 zip 走完三步；进度写入 `upload_progress.txt`。

核心动作序列（每轮）：

```sh
bsk navigate "https://open.workbuddy.cn/skill/publish?action=create&step=1" --session <id>
# 找到「点击或拖拽上传代码包」按钮 → 上传
bsk upload @eX --file <zip绝对路径> --mode drop --session <id>   # 等 4s（必须 drop，见关键坑 5）
# 「继续」→ 第2步
#   市场展示分类: 点 combobox "请选择" → 点选项「内容创作」
#   服务类目:     点 button "请选择" → 点「工具」→ 点「办公」
# 「继续」→ 第3步 → 点「提交」→ 校验出现「已提交审核」
```

要点：
- `bsk observe` 的 ref(`@eN`) 每次渲染都会变，**永远先 observe 再 click**，不要跨步骤复用 ref。
- 用文本匹配 ref：按 `@e(\d+)\s+(\w+)\s+"(文本)"` 解析，再区分 role（combobox=市场展示分类，button=服务类目/选项）。
- `bsk click` 也接受 **CSS 选择器**（`--selector`），必要时可比 ref 更稳。
- 上传前先 `bsk` 确认 zip 已通过导入端校验（`skill-package-guard/scripts/check_skill_package.py`）。

## 收尾与核验

1. `bsk navigate https://open.workbuddy.cn/skill/all`，滚动到底加载全部。
2. 核验：`bsk evaluate --session <id> "document.body.innerText"` 存文本，
   用本批技能的 `display_name` 逐一 `in page` 比对，命中数==总数即全部到位。
3. `bsk session stop <id>`（务必关闭自有会话；不要停共享守护进程）。

## 边界

- 只驱动**用户已登录**的浏览器；**绝不**提取 cookie/token/密码，也不代登录。
- 需登录/验证码/扫码时用 `bsk request-help` 请用户协助，不要绕过。
- 不上传含隐私或未授权的内容；上传前与用户确认 zip 清单。
