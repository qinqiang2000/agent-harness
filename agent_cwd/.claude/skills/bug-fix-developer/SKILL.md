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

根因、证据、修复计划、目标仓库（如 `ai-agent/foo`）、修复分支名、是否重修模式（重修时附上一轮失败报告）。

## Step 1：准备工作目录与分支

```bash
ID="<identifier>"          # coordinator 传入
REPO="<namespace/repo>"    # coordinator 传入
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

## Step 2：RED — 写复现 bug 的失败测试

REQUIRED SUB-SKILL：用 superpowers:test-driven-development 的纪律。
- 按根因和证据，在仓库测试目录写一个**能复现该 bug 的失败测试**。
- 本地尽力跑该测试（仓库有构建/测试能力时）：跑出 FAIL 即证明复现成功。
- 仓库本地跑不动（缺依赖/需 Java 环境）→ 标注「测试待 Jenkins 验证」，记下测试文件路径，继续。

## Step 3：GREEN — 改最小代码转绿

- 按修复计划改**最小**代码使复现测试转绿（GREEN）。
- 不顺手重构无关代码（YAGNI / Surgical Changes）。

## Step 4：REFACTOR + 回归

- 必要的重构，跑相关测试确认无回归（本地能跑则跑）。

## Step 5：commit + push + 建 MR

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

## Step 6：代码自审

REQUIRED SUB-SKILL：用 superpowers:requesting-code-review 自审，产出结构化问题清单（CRITICAL/HIGH/MEDIUM）。

## 输出格式（coordinator 解析，必须严格遵守）

```
【分支】<branch>
【MR链接】<从 push 输出解析到的 MR URL，无则留空>
【复现测试】<测试文件路径>
【自审】
- [级别] 问题描述
【说明】<一句话总结这次修复做了什么>
```
