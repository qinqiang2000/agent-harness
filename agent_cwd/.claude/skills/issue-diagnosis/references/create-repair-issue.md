# 自动修复提单流程

issue-diagnosis 诊断到代码 bug 且用户同意提单后，按以下步骤执行。

---

## ① 查询可用团队列表

```bash
$AGENTS_ROOT/.venv/bin/python plugins/bundled/repair/cli.py list-teams
```

（`$AGENTS_ROOT` 为仓库根目录；若环境变量未设置，用绝对路径 `/Users/jinfan/code/git-agent/agent-harness`。）

解析 stdout 的 JSON 数组，格式为 `[{"key": "ARALGO", "name": "团队名称", "id": "..."}]`。

若命令失败，跳过团队选择，直接进入步骤③（`team_key` 留空，提单时会报错提示用户手动填写）。

---

## ② 让用户选择归属团队

用 `AskUserQuestion` 展示团队列表，格式：

> 请选择该 bug 单归属的团队：
> {列表，每行一条，如：1. ARALGO - 算法团队  2. QUASAF - 质量团队}

- 用户选择后，记录对应的 `key` 作为 `team_key`。
- 用户输入"取消"或选项不在列表中 → 终止提单流程，进入 Step 7。

---

## ③ 写 payload 文件

生成唯一文件名（避免并发冲突）：`PAYLOAD_FILE=/tmp/repair/payload-$(date +%s%3N)-$RANDOM.json`

用 Write 写该路径（避开多行 shell 转义）：

```json
{
  "team_key": "<用户选择的团队 key，如 ARALGO>",
  "title": "fix: <一句话 bug 标题>",
  "root_cause": "<Step 6 的根因结论>",
  "evidence": "<日志/数据库/源码证据，多行>",
  "repair_plan": "<修复方向，基于源码定位给出>",
  "repo": "<主仓库 namespace/repo，如 ai-agent/foo>",
  "affected_services": ["<服务1 namespace/repo>", "<服务2 namespace/repo>"]
}
```

`affected_services` 填所有受影响服务的仓库路径（从日志的 `project` 字段和源码定位中收集），至少包含 `repo` 本身。`repair_plan` 只写修复**方向**（哪个类/方法、加什么校验），不写完整代码。

---

## ④ 执行提单

```bash
$AGENTS_ROOT/.venv/bin/python plugins/bundled/repair/cli.py create-issue --input $PAYLOAD_FILE
```

---

## ⑤ 回复用户

解析 stdout 单行 JSON：

- `{"ok": true, ...}` → 回复：
  > 已创建 Linear bug 单 {identifier}，归属团队 {team_key}。请在 Linear 确认，没有问题后可以@agent ,即可启动自动修复。

- `{"ok": false, ...}` → 如实告知提单失败原因，不影响 Step 6 已输出的诊断结论。

---

**约束**：本流程只提单，不改任何代码；提单失败不阻塞诊断流程。
