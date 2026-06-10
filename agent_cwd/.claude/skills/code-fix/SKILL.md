---
name: code-fix
description: >-
  仅在 issue-diagnosis 已输出【根因分析】且结论明确为代码问题之后触发，可由 issue-diagnosis 自动调用或用户主动要求。
  触发的必要前提：当前对话中已存在 issue-diagnosis 输出的【根因分析】块，且根因指向代码问题。
  触发词：用户说"帮我修复"、"自动修复"、"fix一下"、"修代码"、"提PR"、"帮我改"、"修一下"；或由 issue-diagnosis 在诊断结论为代码问题时自动调用。
  禁止触发的场景：用户只提供了 traceId、报错信息、或描述了问题但尚未经过 issue-diagnosis 诊断——这些场景应由 issue-diagnosis 处理。
---

# 代码自动修复

**执行前提**：issue-diagnosis 已完成诊断，根因明确为代码问题。

**⚠️ 全程步骤静默执行，禁止在输出中暴露步骤标题（如"Step 1"等）。只在最后一步输出修复结论。**

---

## Step 1：前提检查 + 提取诊断上下文

**⚠️ 硬性前提检查（第一步必须执行，不满足则立即终止）**：

检查当前对话中是否存在 issue-diagnosis 输出的【根因分析】块。判断标准：
- 对话历史中有包含「【根因分析】」字样的消息
- 且根因内容指向代码问题（含"代码"、"Feign"、"未传"、"逻辑"、"注入"、"参数"、"服务名"等字样）

**不满足时**：立即用 `AskUserQuestion` 反问，禁止继续执行后续任何步骤：
> 未找到 issue-diagnosis 的诊断结论。请先描述报错信息或 traceId，由诊断流程定位根因后，再执行代码修复。

**满足后**，从【根因分析】和【证据】中提取：

- `repoName`：需修复的服务仓库名（从根因描述中的服务名推断，查 `references/service-repo-map.md` 映射）
- `projectId`：GitLab 仓库路径（如 `piaozone/input/api-invoice-recognition`）
- `sessionSuffix`：取当前时间戳 `$(date +%H%M%S)`
- `localDir`：`/tmp/gitlab/fix/{repoName}_{sessionSuffix}`（**注意：路径前缀是 `/tmp/gitlab/fix/` 而不是 `/tmp/gitlab/src/`**，与 issue-diagnosis 的源码查阅目录完全隔离，避免并发修改冲突）
- `targetFile`：需修复的源码文件路径（若【证据】中有 `源码: {ClassName}.java:{行号}` 则直接使用；否则进入 Step 1.5 定位）
- `rootCause`：根因描述
- `fixSuggestion`：解决建议

**禁止重新查询 ELK 日志或重走诊断流程**，所有信息只从对话历史提取或在本地 clone 目录中查找。

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
