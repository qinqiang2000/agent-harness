# 自动化 Bug 修复流水线设计方案（Linear 中枢版）

> 日期：2026-06-02（v2，参照 ai-cc 全链路工作流重构）
> 状态：方案设计（待评审，开发时可再调整）
> 参照系统：`ai-cc.md` —— 已验证的 Linear 中枢 + Claude Code superpowers + Jenkins 全链路开发流水线（GitHub 版）

## 1. 背景与目标

现有 `issue-diagnosis` skill 已能对服务问题做根因定位，输出结构化的【根因分析】/【证据】/【解决建议】，并已能判定「根因是否指向代码逻辑」（见 `agent_cwd/.claude/skills/issue-diagnosis/SKILL.md:148`）。

本方案在其之上，打通一条 **以 Linear 为中枢、从「发现代码bug」到「自动修复并验证」** 的长流程：

```
诊断(代码bug) → Linear MCP 提 bug 单 → 用户在 Linear 审核确认
   → Linear webhook 通知后端 → agent 改 Linear 状态为「开发中」
   → 新建开发 skill 指导 TDD 改码（复现测试→修→转绿）→ 推分支 + 建 MR
   → 调 Jenkins 构建 + 自动化测试 → agent 分析报告（三类归因）
   → 已解决：回写 Linear「已解决」+ 通知用户（分支/MR/代码位置）
   → 未解决：按归因回转（同分支修 / 回诊断 / 拆子单），重试至上限
```

### 设计原则（对齐 ai-cc）

1. **Linear 是中枢**：所有状态流转、审核、进度回填都以 Linear 为中心，agent 通过 Linear MCP 主动回写状态。
2. **TDD 驱动修复**：先写一个能复现 bug 的失败测试 → 修复 → 测试转绿。失败测试是 bug 的可复现证明，转绿是「已解决」的硬证据。
3. **Git 是唯一存档**：修复计划、测试、代码全部进 Git，可追溯、可回滚。
4. **全程自动，关键决策保留确认**：人工审核（Linear 上确认 bug 单）和 MR approve 是仅有的两个确认点。
5. **聚焦 bug 修复（精简版）**：只走 ai-cc 的 `fix` 分支，不引入 PRD/需求评审/本体审查/e2e 回归补齐等全链路环节（YAGNI）。

### 成功标准

- 诊断判定为代码bug后，自动提 Linear 单；用户确认即启动全自动修复。
- 全程状态以 Linear 为准，可观测（当前卡在哪、重试了几次）。
- 不可逆动作（合并到主干）保留人工，agent 只推独立分支 + 建 MR。
- 流程可跨天挂起，由 Linear webhook / GitLab webhook 唤醒续接。
- 失败按三类归因回转，各类循环有次数上限，由代码兜底，不死循环。

## 2. 关键决策

| # | 决策项 | 选定方案 |
|---|--------|----------|
| 1 | 状态中枢 | **Linear**（状态字段 + 评论 + label 承载业务状态）；PG 仅存运行时细节 |
| 2 | 流水线入口 | issue-diagnosis 判定代码bug → 自动提 Linear 单；**用户在 Linear 确认才进入开发** |
| 3 | 审核结果感知 | **Linear webhook 推送** → 后端 → agent 通过 Linear MCP 改状态 |
| 4 | 后续状态联动 | **后端胶水层**：GitLab webhook（MR/构建/测试事件）→ 后端 → agent 通过 MCP 回写 Linear（不依赖 Linear↔GitLab 原生集成） |
| 5 | 审核内容 | **根因 + 修复计划**（不含具体代码） |
| 6 | 代码修改自主度 | agent 自动 clone→建分支→TDD改码→commit→push→建 MR，**合并留人工** |
| 7 | 开发驱动方式 | **TDD**：新建开发 skill，先写复现 bug 的失败测试 → 修 → 转绿 |
| 8 | Jenkins 触发 | **后端调 Jenkins build API 主动触发** |
| 9 | 报告形态 | **Jenkins 跑的自动化测试报告**，agent 据此判断 bug 是否解决 |
| 10 | 失败回转 | **三类归因**（代码错 / 根因错 / 漏依赖），各走不同回转路径 |
| 11 | 流程范围 | **精简版**：只做 bug 修复（ai-cc 的 fix 分支），不做 PRD/本体/e2e 回归 |

## 3. 与 ai-cc 的关系

ai-cc 是一套**已验证的全链路开发流水线**（需求→PRD→评审→编码→PR→构建→回归→发布）。本方案是其 **`fix(缺陷修复)` 分支的专用化、并适配内网 GitLab**：

| 维度 | 本方案（bug 修复） | ai-cc（全链路，参照） |
|---|---|---|
| 触发 | issue-diagnosis 发现 bug | 需求工单 + 内部规划 |
| 范围 | 只做 bug 修复 | 全链路 feat 为主 |
| 中枢 | **Linear**（与 ai-cc 一致） | Linear |
| 平台 | **内网 GitLab + MR** | GitHub + PR |
| 状态联动 | **后端胶水层主动回写** | Linear↔GitHub 原生集成 |
| 开发 | **TDD（复用 superpowers）** | TDD（superpowers） |
| 审核点 | Linear 确认 + MR approve | PRD 评审 + PR approve |
| 失败归因 | 三类（见 §6） | 三类（代码错/PRD错/PRD漏场景） |

## 4. 平台差异：GitHub → 内网 GitLab 映射

这是不能照抄 ai-cc 的核心原因，开发前需重点验证：

| ai-cc（GitHub） | 本方案（内网 GitLab） | 处理 |
|---|---|---|
| GitHub Actions（claude-ontology-review.yml / jenkins-deploy.yml） | GitLab 无 Actions | 用 **GitLab webhook → 后端** 或 GitLab CI；触发 Jenkins 走后端 API |
| Pull Request + PR review | **Merge Request + MR approve** | 概念对应，MCP 工具已有 `create_merge_request` / `approve_merge_request` |
| Linear↔GitHub 原生集成（PR 提交自动流转 Linear） | Linear↔GitLab 原生集成弱/不可达 | **后端胶水层**：监听 GitLab webhook，agent 主动调 Linear MCP 回写状态 |
| GitHub OAuth App | GitLab token | 凭证体系不同 |
| 部署后 autotest job 自动触发 | 后端调 Jenkins build API | 已选主动触发 |

> **开发前必须验证项**：Linear webhook 能否回调到内网后端、内网后端能否访问 Linear API（出网）、GitLab webhook 配置权限。

## 5. 状态机主流程（Linear 状态驱动）

Linear Issue 的状态字段是流程的真相来源。agent 在每个阶段完成后通过 Linear MCP 改状态，webhook 事件触发下一阶段。

```
            issue-diagnosis 判定「根因指向代码逻辑」(SKILL.md:148)
                              │
                              ▼ agent 调 Linear MCP 提 bug 单（根因+证据+修复计划）
                    ┌───────────────────┐
                    │ Linear: 待审核     │  ⏸ 挂起，等用户在 Linear 确认
                    │ (Backlog/Triage)  │
                    └─────────┬─────────┘
                              │ 〔Linear webhook: 用户 approve〕
                              │ → 后端 → agent 调 MCP 改状态
                              ▼
                    ┌───────────────────┐
        ┌──────────▶│ Linear: 开发中     │  ◀── 新建「开发 skill」TDD 驱动
        │           │ (In Progress)     │      ① 写复现 bug 的失败测试
        │           │                   │      ② 改码使其转绿 ③ 重构
        │           │                   │      clone→分支→commit→push→建 MR
        │           └─────────┬─────────┘
        │                     │ MR 已建 → 后端调 Jenkins build API
        │                     ▼
        │           ┌───────────────────┐
        │           │ Linear: 构建测试中 │  ⏸ 挂起，等 GitLab/Jenkins 事件
        │           │ (In Review)       │  (webhook 回调 或 定时轮询报告)
        │           └─────────┬─────────┘
        │                     │ 〔报告就绪〕→ 后端 → agent 分析报告
        │                     ▼
        │           ┌───────────────────┐
        │           │ agent 分析测试报告 │  本地 TDD 测试 + Jenkins 报告
        │           │ → 三类归因判定     │
        │           └─────────┬─────────┘
        │      ┌──────────────┼───────────────────┐
        │      │ bug已解决     │ ①代码错           │ ②根因错/③漏依赖
        │      ▼              ▼                    ▼
        │  ┌─────────┐   重试次数<N?          回转处理（见 §6）
        │  │Linear:  │   ┌──是──┘ └─否─┐       ②回诊断 / ③拆子单
        │  │已解决 ✅ │   ▼            ▼
        │  │通知用户  │  同分支重修   ┌──────────┐
        │  └─────────┘  (回开发中)   │Linear:   │
        │                            │产研退回   │
        └─ ②根因错：回 issue-diagnosis 重新诊断    │转人工接手 │
           ③漏依赖：拆子 Linear 单 + blockedBy    └──────────┘
```

### Linear 状态映射（开发时按团队实际工作流定）

| 阶段 | Linear 状态（示例） | 进入动作 | 离开条件 |
|------|--------------------|----------|----------|
| 待审核 | Triage / Backlog | agent 提单（根因+计划） | 用户 approve → 开发中 |
| 开发中 | In Progress | 开发 skill TDD 改码 | MR 已建 → 构建测试中 |
| 构建测试中 | In Review | 后端触发 Jenkins | 报告就绪 → 分析 |
| 已解决 | Done | 回写 + 通知用户 | 终态 |
| 产研退回 | Canceled / 自定义 | 重试超限或根因错 | 转人工 |

## 6. 三类失败归因（借鉴 ai-cc）

agent 分析测试报告后，不只判「解决/未解决」，而是按归因走不同回转：

| 归因 | 判定标准 | 回转路径 | 计数 |
|------|----------|----------|------|
| **① 代码错** | 修复计划正确，但实现有偏差/引入新错 | 回「开发中」，**同分支** TDD 重修 | `fix_retry_count`（上限 N，超限 → 产研退回转人工） |
| **② 根因错** | 测试证明原诊断的根因判错了 | 回 `issue-diagnosis` 重新诊断，作废当前 bug 单或重开 | 重诊断计数（上限 M） |
| **③ 漏依赖** | 修复正确但牵出范围外的依赖问题（需改别的服务/前置数据） | 拆子 Linear 单走独立流程，父单 `blockedBy` 子单，子单合后 rebase 接力 | — |

> **打回重做走 rebase**（借鉴 ai-cc 节点3）：同分支重修前 `rebase` 最新基线，避免基线漂移。

## 7. 新建「开发 skill」（TDD 驱动）

核心新增物。指导 agent 在拿到「根因+修复计划」后完成 TDD 修复。复用 superpowers 的 `test-driven-development` 与 `requesting-code-review`。

**输入**：Linear 单上的根因 + 证据 + 修复计划 + 目标仓库信息
**流程**：
1. clone 目标仓库（复用 issue-diagnosis 已有的 GitLab clone 模板），新建修复分支
2. **写一个能复现该 bug 的失败测试**（RED）——这是 bug 的可复现证明
3. 改最小代码使测试转绿（GREEN）
4. 重构（REFACTOR），跑全量相关测试确认无回归
5. commit → push 到修复分支 → 建 MR
6. 代码自审（`requesting-code-review`），产出问题清单

**输出**：分支名 + MR 链接 + 复现测试 + 自审报告（结构化，回写 Linear 评论）
**约束**：只在独立分支写码并 push，禁止 push 主干、禁止自动 merge MR。

## 8. 后端职责与组件

| 组件 | 职责 |
|------|------|
| Linear webhook 路由 | 接收用户审核事件 → 触发 agent 改状态 + 启动开发 |
| GitLab webhook 路由 | 接收 MR/构建/测试事件 → 触发 agent 回写 Linear + 推进流程 |
| Jenkins client | 调 build API 触发构建（带分支参数）、拉取测试报告 |
| Repair 协调（轻量） | 串联各阶段、管重试计数；状态以 Linear 为准，PG 仅存运行时细节 |
| PG 运行时表（轻量） | `linear_issue_id, repo, branch, mr_url, jenkins_build_id, fix_retry_count, rediagnose_count, last_report`（Linear 表达不了的细节） |
| APScheduler 轮询任务 | 构建报告轮询（webhook 兜底） |
| agent 子能力 | ① 提 bug 单（含修复计划） ② 开发 skill（TDD） ③ 分析报告（三类归因） |

> 与 v1 的差别：状态机不再是后端 PG 的强逻辑，而是 **Linear 状态 + agent 通过 MCP 回写**；PG 退化为运行时细节存储。

## 9. 安全边界

- agent 只允许在独立修复分支写码并 push，**禁止 push 主干、禁止自动 merge MR**。
- GitLab 写权限按操作粒度收敛（create_branch / create_or_update_file / push_files / create_merge_request），**不放开 merge**。当前 `agent_cwd/.claude/settings.json` 明确 deny git 写操作，需为本流程定向放开（限修复分支）。
- 沿用现有脱敏与敏感文件保护（禁读 .env/密钥、禁输出凭证）。
- 合并到主干始终由人工在 GitLab/Linear 上完成。

## 10. 待开发时确认的细节

- Linear 团队/项目/状态工作流字段映射；bug 单模板字段。
- N（修复重试上限）、M（重诊断上限）取值。
- Linear webhook 能否回调内网后端；后端能否出网访问 Linear API。
- GitLab webhook 事件配置（MR、pipeline、push）。
- Jenkins job 名/凭证/分支参数；测试报告接口与格式（JUnit/自定义）。
- 终态通知渠道（云之家/智齿/其他）。
- 开发 skill 跑测试的环境依赖（仓库本地构建/测试能力）。

---

# 附：落地设计（v3，2026-06-04 评审定稿）

> §1–§10 是概念设计。本附章是评审后**与本仓库代码现状对齐**的可落地设计，已解决 §10 的开放问题，作为实现依据。

## 11. 与代码现状的关键校准

设计文档 §4/§6 假设"agent 通过 Linear MCP / GitLab MCP 工具读写"，但本仓库现状并非如此，校准如下：

| 文档假设 | 代码现状 | 落地决策 |
|---|---|---|
| agent 用 Linear MCP 回写 | Linear 是「插件 + 后端胶水层」：webhook → `plugins/bundled/linear/handler.py` → `AgentService` → 自建 `LinearClient`(GraphQL) | 沿用插件 + 胶水层，不引入 MCP |
| MCP 已有 create_merge_request | GitLab 无 MCP、无任何写工具；issue-diagnosis 仅 `git clone/pull` 只读 | 全程 git CLI；建 MR 用 **GitLab push options**（`git push -o merge_request.create`），不需 REST 客户端 |
| —— | `agent_cwd/.claude/settings.json` deny 所有 git 写操作 | 为修复目录 `/tmp/repair/**` 定向放开，仍禁 merge / push 主干 |
| 自动提 Linear 单 | `LinearClient` 无 `create_issue` | 新增 `LinearClient.create_issue()` |
| PG 存运行时细节 | 仅 asyncpg 池 + FAQ 表；Linear token 用 SQLite | 运行时表用 **SQLite**（与 token_store 一致） |
| Jenkins 主动触发 | 无任何 Jenkins 代码 | 本期做**占位接口 + mock**，待联调 |

### 已定决策（评审确认）

| # | 项 | 决策 |
|---|---|---|
| 1 | 改码与回写 | 后端胶水 + git CLI（定向放开），建 MR 用 GitLab push options，不引入 MCP / REST 客户端 |
| 2 | 本期范围 | 先做不依赖外部未验证基建的闭环；Jenkins 触发/报告做占位，待联调 |
| 3 | 本地测试 | 按「本地尽力跑 + Jenkins 为准」设计，不强依赖 agent 主机跑 Java 测试 |
| 4 | 运行时存储 | SQLite（`data/repair/repair_runs.db`，WAL 模式） |
| 5 | 提单入口 | 改 `issue-diagnosis/SKILL.md`：判代码bug → AskUserQuestion 问是否修复 → 同意则 agent 跑 CLI 提单 |
| 6 | 状态承载 | Linear team workflow 原生状态字段（名→stateId 可配置映射） |
| 7 | 审核确认信号 | 用户在 Linear 改状态/分配 → webhook → 后端识别为"审核通过" |
| 8 | 重试上限 | N=3（代码错同分支重修，env 可调）、M=2（根因错重诊断）。超限→产研退回转人工 |
| 9 | session 策略 | 混合：开发开新 session 记 `develop_session_id`；同分支重修(①代码错) resume 该 session；报告分析/重诊断开新 agent |
| 10 | agent→后端动作 | 提单走本地 CLI 脚本（`repair/cli.py create-issue`）；建 MR 走 git push options，不需后端介入 |

## 12. 组件与目录结构

```
plugins/bundled/repair/                 # 新增插件（可独立启停）
├── plugin.json                         # 插件清单
├── plugin.py                           # RepairChannelPlugin：注册 GitLab webhook 路由 + 启动轮询
├── coordinator.py                      # RepairCoordinator：状态机 + 阶段编排 + 重试计数（纯编排）
├── store.py                            # SQLite 运行时表 repair_runs（WAL）
├── jenkins_client.py                   # Jenkins 客户端（本期占位接口 + mock）
├── cli.py                              # agent 调用入口：create-issue 子命令（建 Linear 单）
└── prompts.py                          # 各阶段 prompt 模板 + 名→stateId 状态映射配置

plugins/bundled/linear/
├── linear_client.py                    # 补 create_issue()
└── handler.py                          # webhook 加 Issue 状态变更分支 → 委派 RepairCoordinator

agent_cwd/.claude/skills/bug-fix-developer/        # 新增"开发 skill"（TDD 驱动）
│   └── SKILL.md
agent_cwd/.claude/skills/repair-report-analyzer/   # 新增"报告分析 skill"（三类归因）
│   └── SKILL.md
agent_cwd/.claude/skills/issue-diagnosis/SKILL.md  # 改：加"判bug→问用户→提单"一步

api/services/agent_service.py           # 为修复目录 /tmp/repair/** 定向放开 git 写
```

数据流：
```
issue-diagnosis 判bug + 用户同意 → agent 跑 cli.py create-issue
  → LinearClient.create_issue() 建单 + repair_runs(stage=pending_review)
  → 用户在 Linear 审核（拖到"开发中"）→ Linear webhook
  → RepairCoordinator.start_development() → AgentService(skill=bug-fix-developer)
     TDD 改码 → git push -o merge_request.create 建 MR → coordinator 解析 MR URL 写表 → stage=building → JenkinsClient.trigger(占位)
  → APScheduler 轮询 JenkinsClient.get_report()（本期 mock）→ 就绪
  → RepairCoordinator.analyze_report() → AgentService(skill=repair-report-analyzer)
  → 解析【判定】四选一 → 回转：已解决回写+通知 / 代码错 resume 重修(N) / 根因错回诊断(M) / 漏依赖拆子单
```

## 13. 状态机 + SQLite 运行时表

完整状态机（含提单入口）：

```
入口：issue-diagnosis 诊断（任意 channel）
  判定「根因指向代码逻辑」(SKILL.md:148)
        │ AskUserQuestion：是否自动修复？
   ┌────┴────┐
 用户否     用户同意 → agent 跑 cli.py create-issue（根因+证据+修复计划+目标仓库）
   │           │
 仅诊断结论     ▼ LinearClient.create_issue() + repair_runs(stage=pending_review)
            ┌─────────────┐
            │ 待审核        │ ⏸ 等用户审核
            └──────┬──────┘
                   │ 用户改状态/分配 webhook
                   ▼
       ┌──▶┌─────────────┐ 开发 skill：clone→分支→TDD→push→建MR
       │   │ 开发中        │
       │   └──────┬──────┘
       │          ▼ 触发 Jenkins(占位) → stage=building
       │   ┌─────────────┐
       │   │ 构建测试中     │ ⏸ 等报告（轮询兜底）
       │   └──────┬──────┘
       │          ▼ 报告分析 skill：三类归因
       │   ┌──────┼─────────────┐
       │ ①代码错  解决       ②根因错 / ③漏依赖
       │ resume   ▼            ▼
       │ 重修   ┌────────┐   ②回 issue-diagnosis 重诊断(M)
       └─<N─────┤已解决✅ │   ③拆子单 + 父单 blockedBy
         超N    │+通知    │        │
          │     └────────┘   超M ─┘
          ▼
       ┌────────┐
       │产研退回  │ 转人工
       └────────┘
```

SQLite 表 `repair_runs`（`store.py`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `linear_issue_id` | TEXT PK | Linear Issue UUID |
| `linear_identifier` | TEXT | 如 ENG-123 |
| `workspace_id` | TEXT | 取 token 用 |
| `stage` | TEXT | 内部阶段：pending_review/developing/building/analyzing/resolved/rejected |
| `repo` / `branch` | TEXT | 目标仓库 / 修复分支 |
| `mr_url` | TEXT | MR 链接 |
| `jenkins_build_id` | TEXT | 占位，本期 mock |
| `develop_session_id` | TEXT | 开发阶段 claude_session_id，同分支重修时 resume |
| `fix_retry_count` | INT | 代码错重修计数，上限 N |
| `rediagnose_count` | INT | 根因错重诊断计数，上限 M |
| `root_cause` / `repair_plan` | TEXT | 提单时落档 |
| `last_report` | TEXT | 最近测试报告摘要 |
| `created_at` / `updated_at` | TEXT | 时间戳 |

`stage` 为内部真相游标，Linear 状态为用户可见真相，coordinator 每次推进同步两者。webhook 到来时用 `linear_issue_id` 查表拿 `stage` 判分支，保证幂等。

## 14. 两个新 skill 的契约

### skill A：`bug-fix-developer`（TDD 驱动修复）

- **输入**（coordinator 拼进 prompt）：根因、证据、修复计划、目标仓库、修复分支名、是否重修模式（重修时 resume 开发 session + 附上轮失败报告）
- **流程**（复用 superpowers `test-driven-development` + `requesting-code-review`）：
  1. clone 目标仓库到 `/tmp/repair/<identifier>/`（复用 issue-diagnosis 的 GitLab clone 模板，带 `GITLAB_TOKEN`）
  2. `git checkout -b fix/<identifier>`
  3. **RED**：写复现 bug 的失败测试（本地尽力跑，跑不动则标注交 Jenkins）
  4. **GREEN**：改最小代码转绿
  5. **REFACTOR**：重构 + 跑相关测试
  6. `git add/commit/push` 到修复分支；push 时带 **GitLab push options** 建 MR：
     `git push -o merge_request.create -o merge_request.target=<base> -o merge_request.title="fix: ..." origin fix/<identifier>`
  7. 从 push 的 remote 输出解析 MR 链接（`remote: View merge request ... <url>`）
  8. 代码自审，产出结构化问题清单
- **输出**：分支名、MR 链接、复现测试路径、自审报告（结构化输出 → coordinator 解析后写表 `mr_url` + Linear 评论）
- **约束**：只在 `/tmp/repair/<identifier>/` 修复分支写码并 push，禁 push 主干、禁 merge、禁用 `merge_when_pipeline_succeeds` 等自动合并 push option

### skill B：`repair-report-analyzer`（三类归因）

- **输入**：本地 TDD 结果 + Jenkins 报告（本期 mock）+ 修复 diff 摘要 + 原根因/修复计划
- **强约束结构化输出**（coordinator 据此回转）：
  ```
  【判定】已解决 | 代码错 | 根因错 | 漏依赖
  【依据】<引用报告中支撑判定的具体条目>
  【后续动作】
    - 已解决：无
    - 代码错：<同分支重修要点>
    - 根因错：<为何原根因站不住>
    - 漏依赖：<牵出的外部依赖，建议子单标题>
  ```
- coordinator 解析【判定】：已解决→回写 Linear + 通知；代码错→`fix_retry_count+1`，<N 则 resume 开发 session 重修，超 N→产研退回；根因错→`rediagnose_count+1`，<M 则回 issue-diagnosis，超 M→产研退回；漏依赖→建子单 + 父单 blockedBy。

### 安全边界落地（`agent_service.py` 定向放开）

为修复目录定向放开：`Bash(git checkout -b*)`、`Bash(git add*)`、`Bash(git commit*)`、`Bash(git push*)`，用 PreToolUse hook 限制工作目录在 `/tmp/repair/**`。**仍 deny**：`git merge`、`git push` 主干、`git reset --hard`、`git rebase`（重修的 rebase 由 coordinator 控制或后续单独放开）；developer skill 禁用 `merge_when_pipeline_succeeds` 等自动合并 push option。沿用现有脱敏与敏感文件保护。合并到主干始终人工完成。

> **凭证依赖（联调前验证）**：clone/pull 用现有 `GITLAB_TOKEN`（可能只读）；push + push options 建 MR 用**独立的 `GITLAB_PUSH_TOKEN`**（写权限 + api scope），设计上分开配置、互不混权限，值留空待填。push options 需 GitLab ≥11.10 / git ≥2.10，本期手动验证一次确认可用。

## 15. 后端编排与 agent→后端动作

### agent→后端：本地 CLI（非 HTTP、非 MCP）

`plugins/bundled/repair/cli.py`，复用仓库 `LinearClient` / `store`。**只有 create-issue 一个子命令**（建 Linear 单必须走 GraphQL+token，非 git 操作）；建 MR 由 developer skill 直接用 git push options 完成，不经后端。

```bash
# create-issue：issue-diagnosis agent 提单
$AGENTS_ROOT/.venv/bin/python plugins/bundled/repair/cli.py create-issue --input /tmp/repair/payload.json
# stdout: {"ok": true, "identifier": "ENG-123", "issue_id": "..."}
```

要点：
1. **payload 经临时 JSON 文件传**（agent 用 Write 写文件），避开多行文本的 shell 转义。
2. CLI 用 `PYTHONPATH=$AGENTS_ROOT` 引仓库模块（与现有 hooks 调用同源）。
3. SQLite 跨进程（FastAPI coordinator + CLI）并发：WAL 模式 + 短事务 + locked 重试。写频极低。
4. CLI 仅暴露 create-issue 一个子命令，内部校验输入。

> MR 不经后端：developer skill push 时用 push options 直接建 MR，把分支名 + MR URL 放进结构化输出 → coordinator 解析写表。报告分析 agent 同样由 coordinator 调起，【判定】输出直接由 coordinator 解析，无需 agent 回调后端。

### webhook 编排（两入口 + 轮询兜底）

1. **Linear webhook**（复用 `/linear/webhook`，`handler.py` 加分支）：Issue 状态变更/分配事件 → 查 `repair_runs`，`pending_review` 且新状态=开发中 → `RepairCoordinator.start_development()`：置 `stage=developing`，调 `AgentService(skill=bug-fix-developer)`，记 `develop_session_id`；产出 MR 后置 `stage=building` 并触发 Jenkins（占位）。
2. **GitLab webhook**（repair 新增 `/repair/gitlab/webhook`）：本期做**骨架 + 验签占位**（连通性未验证），不作主驱动。
3. **APScheduler 轮询兜底**（复用现有 scheduler）：`stage=building` 的 run 定时轮询 `JenkinsClient.get_report()`（本期 mock）→ 就绪则 `RepairCoordinator.analyze_report()` 调 `AgentService(skill=repair-report-analyzer)`，解析回转。env `REPAIR_POLL_ENABLED` 控制，默认关。

### Jenkins 占位（`jenkins_client.py`）

```python
class JenkinsClient:
    def trigger_build(self, repo, branch) -> str:    # 返回 build_id；本期 mock 假 id
    def get_report(self, build_id) -> dict | None:    # 返回报告或 None(未就绪)；本期 mock 可控
```
签名按真实 Jenkins build API 设计，body 留 TODO 标明待联调字段（job 名/凭证/分支参数/报告格式）。联调时只改本文件实现，不动编排。

**RepairCoordinator 是纯编排**：每方法 = 读 `repair_runs` → 调 agent 或 Linear → 写新状态。N/M 重试计数用代码硬兜底，不靠 agent 自觉。

## 16. 测试策略

遵循全局规则（pytest、80% 覆盖、AAA、TDD）。纯逻辑可单测、外部依赖全 mock。

**单元测试**
- `store.py`：增删查改、WAL 并发、locked 重试、幂等 upsert
- `coordinator.py`（最关键）：状态机每条转移 + 三类归因回转 + N/M 计数兜底。用 fake LinearClient/JenkinsClient + 内存 SQLite，断言：代码错×N→产研退回；根因错×M→产研退回；漏依赖建子单+父单 blockedBy；已解决回写+终态；重复 webhook 幂等；从 developer 输出解析 MR URL 写表。
- `cli.py`：create-issue 参数解析、payload 读文件、stdout JSON 格式
- `linear_client.create_issue()`：GraphQL mutation 构造（mock）
- `jenkins_client.py`：占位 mock 契约（trigger 返 id、get_report 可控就绪）

**集成测试（端到端全 mock 外部）**
- happy path：create-issue → 模拟状态变更 webhook → coordinator 调 stub developer（返回分支+MR URL）→ 解析写表 → 轮询 mock 报告就绪 → coordinator 调 stub analyzer 返"已解决" → 断言 Linear 终态 + stage=resolved
- 失败回转：analyzer 返"代码错" → 断言 fix_retry_count+1 且 resume 同一 develop_session_id

`AgentService.process_query` 在集成测试中 stub（不真起 Claude SDK）——验编排与状态机，非 agent 修复能力。

**本期手动验证（非自动化测试，需你提供凭证）**：拿一个真实 piaozone 仓库 + 写权限 `GITLAB_PUSH_TOKEN`，手动跑通 clone → `checkout -b` → 改一行 → commit → `git push -o merge_request.create` → 确认 GitLab 上生成 MR 且 push 输出回带 URL。验证 push options 可用性与 token 权限，作为 developer skill 真实落地的前置。

**不在本期测试范围**（依赖未验证基建，标注 TODO）：真实 Linear webhook 连通、真实 Jenkins、agent 真在 Java 仓库跑 TDD（编译+测试）。待提供凭证/连通性后联调。

## 17. 本期边界小结

**做**：repair 插件（store/coordinator/jenkins_client 占位/cli(仅 create-issue)/plugin）、`LinearClient.create_issue`、linear handler 委派分支、两个新 skill（developer 用 git push options 建 MR）、issue-diagnosis 提单步、agent_service 定向放开 git 写、轮询兜底、全套单测 + 集成测试。

**占位待联调**：Jenkins client 实现、GitLab webhook 主驱动、agent 主机 Java 构建/测试能力。

**本期手动验证一次**：真实 Java 仓库 clone+建分支+`push -o merge_request.create` 链路（需写权限 `GITLAB_PUSH_TOKEN` + 可用仓库）。

**始终人工**：合并 MR 到主干。
