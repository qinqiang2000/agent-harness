---
name: bug-fix-developer
description: >-
  TDD 驱动的 bug 自动修复 skill。在拿到「根因 + 证据 + 修复计划 + 目标仓库 + 修复分支名」后，
  clone 仓库、写复现测试、改最小代码转绿、推分支并用 GitLab push options 建 MR。
  由修复流水线 coordinator 调起，不面向终端用户直接触发。
---

# Bug 修复开发（TDD 驱动）

**严格按步骤执行，全程只在 `/tmp/repair/<identifier>/` 修复分支写码。**

## ⚠️ 硬约束（违反即终止）

- 只在 `/tmp/repair/<identifier>/` 目录内操作，clone、改码、commit、push 都在此目录
- 修复分支名必须用 coordinator 传入的分支名（形如 `fix/<identifier>`）
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
BRANCH="<branch>"          # coordinator 传入，形如 fix/<identifier>
WORK="/tmp/repair/$ID"
GITLAB_BASE="${GITLAB_BASE_URL:-http://123.207.158.7:5000/ai-agent/git}"

mkdir -p "$WORK"
# clone（只读 token），已存在则 pull
[ -d "$WORK/.git" ] && git -C "$WORK" pull || \
  git clone "$(echo $GITLAB_BASE | sed 's|://|://token:'"$GITLAB_TOKEN"'@|')/$REPO.git" "$WORK"

cd "$WORK" && git checkout -b "$BRANCH" 2>/dev/null || git -C "$WORK" checkout "$BRANCH"
```

重修模式：跳过 `checkout -b`，直接在已有分支上继续，先读上一轮失败报告再改。

## Step 2：理解代码（改码前必做，禁止跳过）

**先读懂现有逻辑，再动手。** 修复计划（尤其人工提单）可能只给出业务层面的修复方向（如「任务作废逻辑改为不作废」），并不直接指向具体代码位置。改码前必须：

- 按根因/证据/修复计划里的关键词（类名、方法名、表名、业务概念），用 Grep/Glob 在 `$WORK` 内定位相关代码。
- 通读涉及的类与方法，弄清现有逻辑**为什么**会产生该 bug，以及修复点的上下游影响（调用方、被调用方、相关配置）。
- 把修复方向**翻译成具体的代码改动落点**：改哪个文件、哪个方法、加/改什么逻辑。落点不清晰时，继续读代码，不要凭修复计划字面猜测。
- 若读完代码发现修复计划与实际代码逻辑矛盾、或根因站不住，**不要硬改**：在输出里如实说明，交由 coordinator 走「根因错」回转。

理解清楚后再进入 Step 3 写复现测试。

## Step 3：RED — 写复现 bug 的失败测试

REQUIRED SUB-SKILL：用 superpowers:test-driven-development 的纪律。
- 按根因和证据，在仓库测试目录写一个**能复现该 bug 的失败测试**。
- 本地尽力跑该测试（仓库有构建/测试能力时）：跑出 FAIL 即证明复现成功。
- 仓库本地跑不动（缺依赖/需 Java 环境）→ 标注「测试待 Jenkins 验证」，记下测试文件路径，继续。

## Step 4：GREEN — 改最小代码转绿

- 按修复计划改**最小**代码使复现测试转绿（GREEN）。
- 不顺手重构无关代码（YAGNI / Surgical Changes）。

## Step 5：REFACTOR + 回归

- 必要的重构，跑相关测试确认无回归（本地能跑则跑）。

## Step 6：commit + push + 建 MR

push 用**写权限** `GITLAB_PUSH_TOKEN`（与 clone 的只读 `GITLAB_TOKEN` 分离）。push 前把 remote 切成带写 token 的 URL：

```bash
cd "$WORK"
git add -A
git commit -m "fix($ID): <一句话修复说明>"

# push 用写权限 token（未单独配则回退到 GITLAB_TOKEN，需其本身有写权限）
PUSH_TOKEN="${GITLAB_PUSH_TOKEN:-$GITLAB_TOKEN}"
PUSH_URL="$(echo $GITLAB_BASE | sed 's|://|://token:'"$PUSH_TOKEN"'@|')/$REPO.git"
git remote set-url --push origin "$PUSH_URL"

# 用 GitLab push options 建 MR（禁止自动合并）
git push -o merge_request.create \
         -o merge_request.target=master \
         -o merge_request.title="fix($ID): <标题>" \
         origin "$BRANCH"
```

从 push 的 remote 输出解析 MR 链接（形如 `remote: View merge request ... <url>`）。

## Step 7：代码自审

REQUIRED SUB-SKILL：用 superpowers:requesting-code-review 自审，产出结构化问题清单（CRITICAL/HIGH/MEDIUM）。

## 输出格式（coordinator 解析，必须严格遵守）

```
【仓库】<实际使用的完整 project_id，如 piaozone/elc-integration/api-elc-invoice-imputation>
【分支】<branch>
【MR链接】<从 push 输出解析到的 MR URL，无则留空>
【复现测试】<测试文件路径>
【自审】
- [级别] 问题描述
【说明】<一句话总结这次修复做了什么>
```
