---
name: code-fix
description: >-
  代码自动修复 skill。接收诊断结论（含根因描述和服务名）后，自动完成源码定位、分支创建、代码修复和 push。
  触发方式：1）issue-diagnosis 诊断为代码问题后自动调用；2）用户说"帮我修复"、"fix"、"修代码"、"提PR"等。
  输入格式："{服务名}:{根因一句话摘要}" 或直接传入 issue-diagnosis 的完整诊断结论文本。
  禁止触发的场景：用户只提供 traceId 或报错信息但尚未经过诊断——这些场景应由 issue-diagnosis 处理。
---

# 代码自动修复

**⚠️ 全程步骤静默执行，禁止在输出中暴露步骤标题（如"Step 1"等）。只在最后一步输出修复结论。**

---

## Step 1：提取诊断上下文

从以下两个来源之一提取根因信息（优先级从高到低）：

**来源A：直接传入的诊断摘要**（由 issue-diagnosis 或 handler 层直接传入）
- 格式为 `{服务名}:{根因描述}` 或完整的诊断结论文本
- 直接从中提取 `repoName`、`rootCause`、`fixSuggestion`

**来源B：对话历史中的诊断结论**（用户在 Chat UI 多轮对话时）
- 从对话历史中找包含「【根因分析】」的消息
- 从【根因分析】和【证据】中提取信息

**两个来源都没有根因信息时**：用 `AskUserQuestion` 反问：
> 请提供诊断结论或根因描述，以便执行代码修复。

**提取后构建以下变量**：

- `repoName`：需修复的服务仓库名（从根因描述中的服务名推断，查 `references/service-repo-map.md` 映射）
- `projectId`：GitLab 仓库路径（如 `piaozone/input/api-invoice-recognition`）
- `sessionSuffix`：取当前时间戳 `$(date +%H%M%S)`
- `localDir`：`/tmp/gitlab/fix/{repoName}_{sessionSuffix}`（前缀 `/tmp/gitlab/fix/`，与 issue-diagnosis 的 `/tmp/gitlab/src/` 完全隔离）
- `targetFile`：需修复的源码文件路径（若有 `源码: {ClassName}.java:{行号}` 则直接使用；否则进入 Step 1.5 定位）
- `rootCause`：根因描述
- `fixSuggestion`：解决建议

**禁止重新查询 ELK 日志或重走诊断流程**。

---

## Step 1.5：补全缺失上下文

若 `localDir` 不存在，按 `references/gitlab-lookup.md` 中的 clone 模板 clone 到 `localDir`：

```bash
LOCAL_DIR="{localDir}" && GITLAB_BASE="${GITLAB_BASE_URL:-http://123.207.158.7:5000/ai-agent/git}" && \
([ -d "$LOCAL_DIR/.git" ] && git -C "$LOCAL_DIR" pull || \
git clone "$(echo $GITLAB_BASE | sed 's|://|://token:'"$GITLAB_TOKEN"'@|')/{projectId}.git" "$LOCAL_DIR")
```

若 `targetFile` 未知，根据根因描述中的类名在本地目录 Grep 定位：

```bash
grep -r "class {ClassName}" {localDir} --include="*.java" -l
```

仍无法定位时，用 `AskUserQuestion` 询问用户提供具体文件路径或类名。

---

## Step 2：确认修复方案

读取 `targetFile` 完整内容，结合根因和修复建议，推导出具体的代码改动方案：

- 精确定位需修改的方法和行号
- 确定修改内容（补判空、修正逻辑、修枚举映射、补 catch 等）
- 评估改动范围：**单文件单方法为优先**，避免连锁修改

**修复原则**：
- 最小改动原则：只改根因直接相关的代码，不重构无关逻辑
- 保持原有代码风格（命名、缩进、注释语言）
- Java 代码修复后方法级注释必须同步更新，说明修复了什么问题

若根因描述不足以确定具体改法，用 `AskUserQuestion` 反问：
> 根因已定位到 `{ClassName}.java:{行号}`，请确认修复方向：
> 1. {方案A}
> 2. {方案B}

---

## Step 3：检出修复分支

在本地 clone 目录创建新分支，分支名格式 `fixbug_yyyyMMddhhmmss`（使用当前时间）：

```bash
BRANCH_NAME="fixbug_$(date +%Y%m%d%H%M%S)" && \
git -C {localDir} checkout -b "$BRANCH_NAME"
```

记录 `BRANCH_NAME` 供后续步骤使用。

---

## Step 4：写入代码修复

使用 Edit 工具修改 `targetFile`，精确替换需要修改的代码片段。

修改要求：
- 只修改根因直接相关的代码行
- 同步更新该方法的 JavaDoc 注释，在 `@param`/`@return` 之前补充一行说明修复内容，例如：
  ```java
  // fix: 修复 xxx 为 null 时未做判空导致 NPE，增加空值保护
  ```
- 不修改测试文件、配置文件、其他无关类

---

## Step 5：验证修改

执行基础语法校验，确认修改未引入明显错误：

```bash
grep -n "TODO\|FIXME\|<<<\|>>>" {localDir}/{targetFile相对路径}
```

若存在冲突标记或明显语法问题，回到 Step 4 重新修改。

---

## Step 6：提交并推送

```bash
cd {localDir} && \
git add {targetFile相对路径} && \
git commit -m "fix: {一句话描述修复内容，不超过72字符}" && \
GITLAB_BASE="${GITLAB_BASE_URL:-http://123.207.158.7:5000/ai-agent/git}" && \
git push "$(echo $GITLAB_BASE | sed 's|://|://token:'"$GITLAB_TOKEN"'@|')/{projectId}.git" "$BRANCH_NAME"
```

push 失败时：
- 权限不足 → 用 `AskUserQuestion` 告知用户，提供本地修改文件路径和 diff，让用户自行 push
- 网络问题 → 重试一次；仍失败则同上告知用户

---

## Step 7：输出修复结论

以纯文本输出，总字数不超过 300 字：

```
【修复完成】
仓库：{projectId}
分支：{BRANCH_NAME}
文件：{targetFile相对路径}:{修改行号}

【改动说明】
{简述修改了什么，为什么这样改，一到两句话}

【下一步】
- 请在 GitLab 上从 {BRANCH_NAME} 向主干分支发起 Merge Request
- 建议补充对应单元测试后合并
```

若 push 失败，改为：

```
【修复已完成，待手动推送】
本地修改路径：{localDir}/{targetFile相对路径}

【改动说明】
{简述修改内容}

【diff 摘要】
{git diff 输出的关键行}

请手动执行 push 或将上述改动应用到您的本地仓库。
```
