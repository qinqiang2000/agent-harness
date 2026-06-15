---
name: bug-fix-developer
max_turns: 300
description: >-
  TDD 驱动的 bug 自动修复 skill。在拿到「根因 + 证据 + 修复计划 + 目标仓库 + 修复分支名」后，
  clone 仓库、写复现测试、改最小代码转绿、推分支并用 GitLab push options 建 MR。
  由修复流水线 coordinator 调起，不面向终端用户直接触发。
---

# Bug 修复开发（TDD 驱动）

**严格按步骤执行，全程只在 `/tmp/repair/<identifier>/` 修复分支写码。**

## ⚠️ 硬约束（违反即终止）

- 只在 `/tmp/repair/<identifier>/` 目录内操作，clone、改码、commit、push 都在此目录
- 修复分支名必须用 coordinator 传入的分支名（形如 `fix_<identifier>`）
- **禁止** push 到 main/master，**禁止** `git merge`，**禁止** 任何自动合并 MR 的 push option（如 `merge_request.merge_when_pipeline_succeeds`），**禁止** force push（`--force` / `-f` / `--force-with-lease`）
- 所有 git 写命令必须以 `cd /tmp/repair/<identifier> &&` 开头或用 `git -C /tmp/repair/<identifier>`（hook 据此放行）
- clone/pull 用只读 `GITLAB_TOKEN`；push + 建 MR 用写权限 `GITLAB_PUSH_TOKEN`
- 不读取 `.env`、密钥、证书文件；不输出源码到回复

## 输入（由 coordinator 拼进 prompt）

根因、证据、修复计划、目标仓库或服务名、修复分支名、是否重修模式（重修时附上一轮失败报告）。

> 目标仓库可能是**完整 project_id**（如 `piaozone/elc-integration/api-elc-invoice-imputation`），
> 也可能是**裸服务名**（如 `api-elc-invoice-imputation`，人工单常见）。后者须先查表解析（见 Step 1）。

## Step 1：解析仓库路径 + 准备工作目录与分支

**先把传入的目标仓库归一成完整 project_id。** 若传入值已是含 `/` 的多级路径，直接用；
若是裸服务名（不含 `/`），查
`{cwd}/.claude/skills/issue-diagnosis/references/service-repo-map.md`
的「日志服务名 → GitLab 仓库路径 (project_id)」表，把服务名映射成完整 project_id：

- 服务名与表中 key 可能有细微出入（如 `elcinvoice` ↔ `elc-invoice`、缺连字符），按语义就近匹配最合理的一项。
- 命中多个或都不像 → 不要猜，在输出里说明无法确定仓库，交由人工补充。

```bash
ID="<identifier>"          # coordinator 传入
REPO="<project_id>"        # 上面解析出的完整 project_id，形如 piaozone/elc-integration/api-elc-invoice-imputation
BRANCH="<branch>"          # coordinator 传入，形如 fix_<identifier>
WORK="/tmp/repair/$ID"
GITLAB_BASE="${GITLAB_BASE_URL:-http://123.207.158.7:5000/ai-agent/git}"

mkdir -p "$WORK"

# clone（只读 token），已存在则 pull；任一步失败立即停，不要掉进重新 clone
if [ -d "$WORK/.git" ]; then
  git -C "$WORK" pull || { echo "pull 失败，停止"; exit 1; }
else
  git clone "$(echo $GITLAB_BASE | sed 's|://|://token:'"$GITLAB_TOKEN"'@|')/$REPO.git" "$WORK" \
    || { echo "clone 失败，停止"; exit 1; }
fi

# 切到修复分支：已存在则直接 checkout（重修模式走这里），否则新建
cd "$WORK" || { echo "进入工作目录失败，停止"; exit 1; }
if git -C "$WORK" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$WORK" checkout "$BRANCH"
else
  git -C "$WORK" checkout -b "$BRANCH"
fi
```

重修模式：分支已存在，上面会直接 `checkout` 到该分支（不会新建），在已有改动上继续；动手前先读上一轮失败报告。

## Step 1.5：申请 repo 锁（改码前强制，违反即终止）

把本次要改动的**全部** project_id（Step 1 归一化后的；一个 issue 可能涉及多个服务）作为一组，调后端原子申请锁：

```bash
ISSUE_ID="<issue_id>"      # coordinator 传入的 Issue UUID（prompt 里「Issue UUID」一行）
IDENT="<identifier>"       # coordinator 传入单号，如 ENG-7
"$AGENTS_ROOT/.venv/bin/python" plugins/bundled/repair/cli.py acquire-lock \
  --issue "$ISSUE_ID" --identifier "$IDENT" --repos "<p1>,<p2>"
```

解析 stdout 单行 JSON：

- `{"ok": true}` → 已拿到这组 repo 的独占锁，继续 Step 2。
- `{"ok": false, "blocked_by": "ENG-N"}` 或含 `"error"` 字段 → **立即停止**：不写测试、不改码、不 push。按输出格式填 `【状态】阻塞`，`【说明】` 写明被哪个单（ENG-N）占用。coordinator 会据此退回该单并提示人工稍后重推。

> 为什么由后端做判断：并发下两个 agent 不能各自「查-判-写」，否则会双双判空、双双开修。后端用一次 SQLite 事务原子检查+占用，杜绝竞态。锁在本单走完（测试通过建 MR / 被拒 / 退回）后由 coordinator 自动释放。

## Step 2：理解代码（改码前必做，禁止跳过）

**先读懂现有逻辑，再动手。** 修复计划（尤其人工提单）可能只给出业务层面的修复方向（如「任务作废逻辑改为不作废」），并不直接指向具体代码位置。改码前必须：

- 按根因/证据/修复计划里的关键词（类名、方法名、表名、业务概念），用 Grep/Glob 在 `$WORK` 内定位相关代码。
- 通读涉及的类与方法，弄清现有逻辑**为什么**会产生该 bug，以及修复点的上下游影响（调用方、被调用方、相关配置）。
- 把修复方向**翻译成具体的代码改动落点**：改哪个文件、哪个方法、加/改什么逻辑。落点不清晰时，继续读代码，不要凭修复计划字面猜测。
- 若读完代码发现修复计划与实际代码逻辑矛盾、或根因站不住，**不要硬改**：在输出里如实说明，交由 coordinator 走「根因错」回转。

理解清楚后再进入 Step 3 写复现测试。

## Step 3：RED — 写复现 bug 的失败测试

TDD 纪律：先写测试、确认它因 bug 而失败（RED），再改代码让它通过（GREEN，见 Step 4），最后重构（REFACTOR，见 Step 5）。不要先改代码再补测试。
- 按根因和证据，在仓库测试目录写一个**能复现该 bug 的失败测试**。
- 本地尽力跑该测试（仓库有构建/测试能力时）：跑出 FAIL 即证明复现成功。
- 仓库本地跑不动（缺依赖/需 Java 环境）→ 标注「测试待 Jenkins 验证」，记下测试文件路径，继续。

## Step 4：GREEN — 改最小代码转绿

- 按修复计划改**最小**代码使复现测试转绿（GREEN）。
- 不顺手重构无关代码（YAGNI / Surgical Changes）。

## Step 5：REFACTOR + 回归

- 必要的重构，跑相关测试确认无回归（本地能跑则跑）。

## Step 6：代码自审（push 前的质量闸门）

**先自审，再 push。** 对照修复目标自审本次改动，产出结构化问题清单，按 CRITICAL / HIGH / MEDIUM 三级标注。重点核对：
- 改动是否真正覆盖根因，复现测试是否确实因本次改动转绿；
- 是否引入回归（上下游调用方、相关配置、边界条件）；
- 是否有超出修复范围的多余改动（YAGNI / Surgical Changes）。

**发现 CRITICAL / HIGH 问题先回到 Step 4 修，修完重新自审，不带病 push。** 自审清单连同结果一并在最终输出里报告。

## Step 7：commit + push 修复分支（不建 MR）

push 用**写权限** `GITLAB_PUSH_TOKEN`（与 clone 的只读 `GITLAB_TOKEN` 分离）。
**只推分支，不要建 MR**——MR 由流水线在构建+测试通过后自动创建（你建了反而会重复）。

```bash
cd "$WORK"
git add -A
git commit -m "fix($ID): <一句话修复说明>"

# push 用写权限 token（未单独配则回退到 GITLAB_TOKEN，需其本身有写权限）
PUSH_TOKEN="${GITLAB_PUSH_TOKEN:-$GITLAB_TOKEN}"
PUSH_URL="$(echo $GITLAB_BASE | sed 's|://|://token:'"$PUSH_TOKEN"'@|')/$REPO.git"
git remote set-url --push origin "$PUSH_URL"

# 只推分支，禁止任何 merge_request.* push option
git push origin "$BRANCH"
```

push 成功即视为开发完成，【MR链接】留空（由 coordinator 在测试通过后回填）。

## 输出格式（coordinator 解析，必须严格遵守）

**最后必须输出【状态】**，三选一：
- 「完成」：代码已改、已 commit 并成功 `git push` 分支。
- 「阻塞」：Step 1.5 申请 repo 锁被挡（被别的单占用）；此时不得改码，在【说明】写明占用方单号。
- 「失败」：任何中途卡住（改不动、push 失败、缺 token、被权限拦、放弃）。

coordinator 仅在【状态】完成且有【分支】时才触发构建；「阻塞」→ 退回该单等人工重推；「失败」→ 转人工。**不要为了凑格式谎报完成。**

```
【状态】完成 / 阻塞 / 失败
【仓库】<实际使用的完整 project_id；单服务如 piaozone/elc-integration/api-elc-invoice-imputation；多服务时输出 JSON 数组，如 ["piaozone/base/api-auth","piaozone/base/api-company"]>
【分支】<branch，push 成功才填>
【MR链接】<留空，MR 由 coordinator 在测试通过后创建>
【复现测试】<测试文件路径>
【自审】
- [级别] 问题描述
【说明】<一句话总结这次修复做了什么；若【状态】失败/阻塞则说明卡在哪/被谁占用>
```

## 构建+测试重跑

若用户在 Linear 评论要求重跑构建测试（如「帮我重跑」「重新构建」「retry」），调：

```bash
"$AGENTS_ROOT/.venv/bin/python" plugins/bundled/repair/cli.py retrigger-build \
  --issue "<linear_issue_id>"
```

解析 stdout JSON：
- `{"ok": true, "build_id": "...", "branch": "..."}` → 回复用户「已重新触发构建+测试，等待报告」
- `{"ok": false, "error": "..."}` → 回复用户错误原因
