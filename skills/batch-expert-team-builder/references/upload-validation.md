# 上传校验清单与两条硬约束

本地 `validate_expert.py` 通过 ≠ 上传通过。上传端还有额外校验，以下两条最容易失败。

## 硬约束 1：`members[].name` 必须是 `{en, zh}`

错误信息：
```
解析失败：members[0].name 的 en/zh 均为必填
```

原因：规范文档与 `init_expert.py` 的 Team 模板里成员用的是 `displayName`，
但**上传端要求 `name`**。只写 `displayName` 会失败。

正确写法：
```json
"members": [
  { "id": "xxx-team-lead",
    "name": { "en": "Xie Ceheng", "zh": "解策衡" },
    "profession": { "en": "Chief ...", "zh": "首席..." },
    "avatar": "avatars/xxx-team-lead.png", "role": "lead" }
]
```

## 硬约束 2：`members[].avatar` 路径必须在包内真实存在

错误信息：
```
解析失败：members[].avatar 路径 "avatars/credit-rating-refinancing-team-lead.png" 在包内不存在
```

原因：只生成了 `avatars/team.png`，但每个成员的 avatar 指向各自的
`avatars/<member-id>.png`，这些文件从未生成。

解决：用 `scripts/gen_avatars.py`（或 `build_teams.py` 内置）为
**每个成员**生成头像，确保所有路径落地。

## 上传前自检脚本

```python
import os, json
base = os.path.expanduser('~/.workbuddy/plugins/marketplaces/my-experts/plugins')
dist = './dist'
bad = []
for d in sorted(os.listdir(base)):
    pj = os.path.join(base, d, '.codebuddy-plugin', 'plugin.json')
    if not os.path.isfile(pj):
        continue
    data = json.load(open(pj, encoding='utf-8'))
    if not os.path.isfile(os.path.join(base, d, data.get('avatar', ''))):
        bad.append((d, 'team avatar missing'))
    for m in data.get('members', []):
        if not (m.get('name', {}).get('en') and m.get('name', {}).get('zh')):
            bad.append((d, m.get('id'), 'name 缺 en/zh'))
        if not os.path.isfile(os.path.join(base, d, m.get('avatar', ''))):
            bad.append((d, m.get('id'), 'avatar 文件缺失'))
print('issues:', bad or 'NONE')
```

## 其它常见问题

| 症状 | 原因 | 处理 |
|------|------|------|
| `profession` 与 `displayName` 不一致（Team 报错） | 两者不相等 | 引擎自动保证一致 |
| tags / quickPrompts 数量不为 3 | 多写或少写 | 严格 3 个 |
| `settings.json` agent ≠ agentName | 不一致 | 都设为 `{team}-team-lead` |
| Agent MD frontmatter 含 `tools` | 违规字段 | 禁止声明 tools |
| 专家不在专家目录 | 生成到别处 | 必须在 `my-experts/plugins/` 下 |
