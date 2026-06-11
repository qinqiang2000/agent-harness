# Jenkins 构建+测试集成与报告解读 设计

日期：2026-06-11
范围：把修复流水线里 Jenkins 构建+自动化测试的 mock 占位替换为真实实现，并打通报告解读 + 超时兜底 + 评论重跑。

## 背景与目标

修复流水线（`plugins/bundled/repair/`）当前 `JenkinsClient` 是 mock 占位：`trigger_build` 返回随机 id、`get_report` 直接返回固定的「mock pass」。本期落地真实 Jenkins 集成。

两份接口文档（`docs/cicd.md`、`docs/autotest.md`）揭示真实环境是**两个独立的 Jenkins job，按顺序跑**：

1. **cicd-pipeline**（构建+部署，约 2 分钟）：参数 `SERVICE` / `BRANCH` / `DEPLOY=true`，把修复分支部署到 at 测试环境。
2. **at-automated-test**（自动化测试，30 分钟以上）：参数 `RUN_MODE` / `THREADS` / `ISSUE_ID` 等，对该环境跑测试出报告。

每个 job 的调用都是三步：**触发（POST，从 Location 头取 queue_id）→ 轮询队列拿构建号 → 轮询构建状态看 `building`/`result`**。

### 成功标准

- 修复分支推上去后，自动经 cicd 构建 → 成功则跑 autotest → 报告交 analyzer 归因，全程不阻塞事件循环。
- cicd 构建失败 → 短路，不跑测试，直接把构建失败日志交给 analyzer 归因。
- 进程崩溃/服务异常中断 → 重启后自动从断点接管轮询，无需人工。
- 构建+测试超过 24h（可配置）无报告 → 判超时，直接转人工（不归因、不计重试），反写 Linear。
- 人工在 Linear 评论要求重跑 → 经对话由 agent 调 CLI 重新触发构建+测试。

### 用户决策（brainstorming 已确认）

1. 流程形态：先 cicd 构建部署到 at 环境，再跑 at-automated-test。
2. cicd 构建失败：短路，直接归因（不跑测试）。
3. SERVICE 推导：取 project_id 最后一段（`repo.split('/')[-1]`）。
4. 测试模式默认：smoke 冒烟（可配置）。
5. 整体方案：**方案 C** —— 两任务状态机藏在 JenkinsClient 内、对 coordinator 接口语义不变，但**进度落库 + 后台自驱动**。
6. 超时兜底：超 24h（可配）判失败、反写 Linear。
7. 超时处理：直接转人工，不归因、不计重试。
8. 重跑信号：评论口令 → 走**对话重跑**（agent 调 CLI），不在 handler 硬编码关键词。
9. 重跑能力描述：加进 bug-fix-developer skill。
10. 多服务支持：一个 repair run 可涉及多个 repo，`repair_runs` 新增 `repos` TEXT 字段（JSON 数组），`trigger_build` 签名改为接受 `repos: list[str]`，并行触发多个 cicd 构建，全部 SUCCESS 后触发 autotest。developer skill `【仓库】` 多服务时输出 JSON 数组。

## 架构总览

```
[CLI 短进程]  trigger_build → 落 cicd_queued 记录 → 退出（不轮询）
                                  │
[主服务进程]  JenkinsClient 后台驱动 ──> 轮询 Jenkins、推进 phase、最终把 report 落库
   （on_start/poller 扫表，对没驱动在跑的非 done 记录抢占并拉起驱动）
                                  │
[主服务进程]  coordinator 60s poller → get_report(只读库) → done? → 交 analyzer
```

两个角色严格分离：

- **后台驱动**：主服务进程里、由 JenkinsClient 拉起的 per-build asyncio 任务。**唯一真正访问 Jenkins** 的角色，按节奏轮询、推进 phase、把最终报告 json 落库。
- **`get_report(build_token)`**：coordinator 的 poller 调用，**只查库不碰 Jenkins**，phase=`done` 返回 report_json，否则返回 `None`。

coordinator 与 `JenkinsClient` 的接口契约调整：

- `trigger_build(repos: list[str], branch: str) -> str`（原单 repo 改为列表，支持多服务）
- `get_report(token) -> dict|None`（不变，只读库）

coordinator 调用处改为传 `json.loads(run.repos) or [run.repo]`（兼容旧单 repo 数据）。其余 coordinator 逻辑基本不动，仅新增超时旁路一条分支。

## 第 1 节：JenkinsClient 两任务自驱动状态机

### phase 流转

```
进行中 phase：
  cicd_queued → cicd_building（并行轮询所有 repo 的 cicd 构建）
    ├─ 任一 FAILURE/ABORTED → done_cicd_failure      ← 短路，不跑测试
    └─ 全部 SUCCESS → autotest_queued → autotest_building
         ├─ 用例全绿  → done_success
         ├─ 有用例失败 → done_test_failure
         └─ 未正常跑完（ABORTED/异常）→ done_test_aborted

任意非终态 phase 停留超 build_timeout_seconds → done_timeout
```

终态 phase 一览：

| phase | 含义 |
|---|---|
| done_success | autotest 跑完，全绿 |
| done_cicd_failure | cicd 构建失败（FAILURE/ABORTED），已短路 |
| done_test_failure | autotest 跑完但有用例失败 |
| done_test_aborted | autotest 未正常跑完（ABORTED/调度异常） |
| done_timeout | 整体超时兜底 |

### jenkins_builds 表（归 JenkinsClient 自管）

| 字段 | 说明 |
|---|---|
| build_token | 主键，trigger_build 返回的不透明 id |
| repos_json | 本次构建涉及的 repo 列表（JSON 数组，如 `["piaozone/base/api-auth","piaozone/base/api-company"]`） |
| branch | 修复分支 |
| phase | cicd_queued / cicd_building / autotest_queued / autotest_building / done_success / done_cicd_failure / done_test_failure / done_test_aborted / done_timeout |
| autotest_queue_id | autotest 触发后的队列 id |
| autotest_build_no | autotest 构建号 |
| jenkins_result | 原始 Jenkins result 值（辅助调试用） |
| report_json | 最终报告 summary 字符串（终态时填，failures 列表序列化后也存此字段） |
| started_at | trigger_build 落库时间，超时判定起点 |
| driver_owner | 当前驱动进程标记（抢占用，可空） |
| driver_heartbeat | 驱动心跳时间戳（陈旧可被接管） |
| created_at / updated_at | 时间戳 |

**关联表 `jenkins_cicd_builds`**（每个 repo 的每次 cicd 构建对应一行，通过 `build_token` 与主表关联）：

| 字段 | 说明 |
|---|---|
| id | 自增主键 |
| build_token | 外键，关联 jenkins_builds.build_token |
| repo | 完整 project_id |
| service | SERVICE 参数值（`repo.split('/')[-1]`） |
| queue_id | cicd 触发后的队列 id |
| build_no | cicd 构建号（排队中为空） |
| result | PENDING / SUCCESS / FAILURE / ABORTED |
| console_snippet | consoleText 关键片段（失败时截取，辅助归因） |
| created_at / updated_at | 时间戳 |

两表均放 `data/repair/jenkins_builds.db`，由 `JenkinsBuildStore` 统一管理。

### trigger_build(repos: list[str], branch: str) -> build_token

1. 对每个 repo 并行 POST `{JENKINS_BASE_URL}/job/{JENKINS_CICD_JOB}/buildWithParameters`，params：`token=JENKINS_CICD_TOKEN`、`SERVICE=repo.split('/')[-1]`、`BRANCH=branch`、`DEPLOY=jenkins_deploy`（basic auth）。
2. 从每个 201 响应的 Location 头正则提取 queue_id。
3. 在主表落一条 `phase=cicd_queued`、`repos_json=json.dumps(repos)`、`started_at=now` 记录。
4. 在关联表 `jenkins_cicd_builds` 为每个 repo 插入一行（`result=PENDING`，`queue_id=...`）。
5. 返回 build_token，**立即返回，不等待**。

> CLI 进程只触发+落库即退出；主服务进程扫表统一接管驱动（见第 3 节）。

### 后台驱动：单步推进函数 `_advance(build_token)`

每轮按当前 phase 做一次对应 REST 调用，整轮包 try/except：

- `cicd_queued`：对 `jenkins_cicd_builds` 里所有 `result=PENDING` 且 `build_no` 为空的行，各 GET 一次队列项；拿到构建号则更新该行 `build_no`；所有行都有 `build_no` 后 phase→`cicd_building`。
- `cicd_building`：对所有 `result=PENDING` 的行各 GET 一次构建状态；`building=true` → 不变；完成则更新该行 `result`：
  - 任一行 `result∈{FAILURE,ABORTED}` → 拉该 repo 的 consoleText 关键片段存 `console_snippet`，主表 phase→`done_cicd_failure`，`report_json` 汇总各失败 repo 的摘要（短路，停止驱动）。
  - 全部行 `result=SUCCESS` → 触发 autotest（POST `at-automated-test`，params `token=JENKINS_AUTOTEST_TOKEN`、`RUN_MODE=autotest_run_mode`、`THREADS=autotest_threads`），落 `autotest_queue_id`，phase→`autotest_queued`。
- `autotest_queued`：GET autotest 队列项；拿到构建号 → `autotest_build_no=...`，phase→`autotest_building`。
- `autotest_building`：GET autotest 构建状态；`building=true` → 不变；完成后按 Jenkins result 分三路：
  - `result=SUCCESS` → 解析 testReport（pass/fail 统计），phase→`done_success`。
  - `result=FAILURE` → 解析失败用例列表，phase→`done_test_failure`，`report_json` 存失败摘要。
  - `result=ABORTED` 或其他异常 → phase→`done_test_aborted`，`report_json` 存「autotest 未正常完成」说明。
- 每轮先判超时：`now - started_at > build_timeout_seconds` → phase→`done_timeout`，`report_json` 存超时说明，停止驱动。

驱动循环：调 `_advance` → 未 done 则 sleep（queue_poll_seconds / cicd_poll_seconds / autotest_poll_seconds 按当前 phase 选）→ 再 advance，直到 done。每轮刷新 driver_heartbeat。

### 报告字典契约与 get_report 映射

`get_report(build_token)` 查库，phase 不以 `done_` 开头则返回 `None`；否则按 phase 组装报告字典：

| phase | status | summary 内容 |
|---|---|---|
| done_success | `"success"` | pass/fail 统计 |
| done_cicd_failure | `"failure"` | `[构建失败] ` + consoleText 关键片段 |
| done_test_failure | `"failure"` | 失败用例列表摘要 |
| done_test_aborted | `"failure"` | `[测试任务未正常完成] ` + Jenkins result 说明 |
| done_timeout | `"timeout"` | 「构建+测试超过配置时限未完成，判定超时」 |

```python
{"status": "success" | "failure" | "timeout", "summary": "...", "failures": [...]}
```

summary 里的前缀标注（`[构建失败]`、`[测试任务未正常完成]`）让 analyzer LLM 能区分「代码问题」和「基础设施问题」，做更准确的三类归因。coordinator 现有归因路径不动，仅超时旁路（status=timeout）走新分支（见第 5 节）。

## 第 2 节：配置与认证

### 新增 env（不写死进代码，值待填）

```
JENKINS_BASE_URL=http://jump-test.piaozone.com:8080
JENKINS_USER=chuang_li
JENKINS_API_TOKEN=<basic auth 密码>
JENKINS_CICD_JOB=cicd-pipeline
JENKINS_CICD_TOKEN=<cicd 触发 token>
JENKINS_AUTOTEST_JOB=at-automated-test
JENKINS_AUTOTEST_TOKEN=<autotest 触发 token>
```

cicd 与 autotest 共用同一组 basic auth（`chuang_li`），但**触发 token 不同**（`410xCyjlF88nE63t` vs `JAaZnYeyAeHXN5eN`），故分两个 env。

### config.json 的 repair 段新增

```json
"jenkins_deploy": true,
"autotest_run_mode": "smoke",
"autotest_threads": 4,
"build_timeout_seconds": 86400,
"cicd_poll_seconds": 15,
"autotest_poll_seconds": 30,
"queue_poll_seconds": 5
```

## 第 3 节：对话重跑

### 触发路径

用户在卡住的单子上发评论 → Linear 推 `prompted` 事件 → `handle_prompted` 走**现有 resume 对话**（不加关键词拦截，handler 不动）→ agent 理解「重跑」意图 → agent 调 `cli.py retrigger-build --issue <id>` → 回写会话。

### 新增 `cli.py retrigger-build --issue <linear_issue_id>`

独立短进程，自建 `JenkinsClient` + `RepairStore`（同 acquire-lock 子命令做法，不碰 coordinator 单例）：

1. 读 run。**门禁**：仅 `stage ∈ {BUILDING, REJECTED}` 且 `branch` 非空才允许；否则打印「不可重跑」原因并退出。
2. 重新申请 repo 锁（REJECTED 时锁已释放需重拿；被占 → 提示退出）。
3. 取 `json.loads(run.repos) or [run.repo]` 得到 repos 列表，调 `jenkins.trigger_build(repos, branch)` 拿新 token，`store.update(stage=BUILDING, jenkins_build_id=新token)`。
4. 打印结果（agent 据此回写 Linear 会话）。
5. **不清零** fix_retry_count / rediagnose_count。

### repair_runs 表新增字段

`RepairRun` dataclass 和 `repair_runs` 表新增 `repos` TEXT 字段（JSON 数组，如 `["piaozone/base/api-auth","piaozone/base/api-company"]`）。单服务时与原 `repo` 字段值一致（`["piaozone/base/api-auth"]`），原 `repo` 字段保留做展示用（存第一个 repo 或由 developer 解析后回填）。

coordinator 调用 `trigger_build` 处改为：
```python
repos = json.loads(run.repos) if run.repos else ([run.repo] if run.repo else [])
self.jenkins.trigger_build(repos=repos, branch=branch)
```

developer skill `【仓库】` 字段：
- 单服务：`【仓库】piaozone/base/api-auth`
- 多服务：`【仓库】["piaozone/base/api-auth","piaozone/base/api-company"]`

`parse_developer_output` 解析时：值以 `[` 开头则 `json.loads`，否则包成单元素列表，统一得到 `list[str]`，存入 `run.repos`。

CLI 触发只落库 + 退出，不跑驱动。真正轮询由**主服务进程的 JenkinsClient** 统一接管：`on_start` 与 poller 周期性扫 `jenkins_builds` 表，对「无 driver_owner 或 heartbeat 陈旧（>5min）」的非 done 记录，用一次 UPDATE 抢占后拉起驱动。这同时也是崩溃自愈机制——无论记录由主服务自身、CLI、还是崩溃前遗留产生，都走同一条「扫表拉起」路径。

### bug-fix-developer skill 补充

加一段说明：当用户要求重跑构建测试时，调 `cli.py retrigger-build --issue <id>`，再把结果回写会话。

## 第 4 节：错误处理

### 后台驱动容错

- 单次 Jenkins 请求失败（网络抖动 / 5xx / 超时）→ 记 warning，**不改 phase**，下一轮重试。一次抖动不判失败。
- 触发 cicd 拿不到 201 / Location 解析不出 queue_id → 触发失败，置 `done` + `result=FAILURE`，summary 写触发失败原因（走归因路径）。
- 队列项 `executable=null` → 正常排队，继续等。
- 最终兜底是超时：任何卡死超 24h → `result=TIMEOUT` → coordinator 转人工旁路。

### 驱动接管幂等

`driver_owner` + `driver_heartbeat` 字段。扫表拉起时只接管「无 owner 或 heartbeat 陈旧（>5min）」的非 done 记录，用一次 UPDATE（BEGIN IMMEDIATE 抢占）占用。避免单进程内重复拉起及未来多进程竞态。

### phase 落库事务

每步推进是一次短 UPDATE，沿用 store 的 WAL + busy_timeout。

## 第 5 节：coordinator 超时旁路

`analyze_report` 拿到报告后，**先判** `report["status"] == "timeout"`：

- 不调 analyzer、不计 fix_retry / rediagnose。
- 落可见终态 REJECTED，释放 repo 锁。
- issue 推到 canceled 状态。
- 反写 Linear：`⚠️ 构建+测试超时（超过 24h 未完成），已转人工。请检查 Jenkins/部署环境后，在本单评论「重跑」重新触发。`

其余 status（success/failure）走现有归因路径不变。

## 第 6 节：测试策略

全程不打真实 Jenkins，用 httpx mock transport 模拟 REST。

### test_jenkins_client.py（重写扩展）

- `trigger_build`：mock 201 + Location → 断言落 `cicd_queued` 记录、返回 token、SERVICE=project_id 最后一段。
- `_advance` 单步推进（不跑真 asyncio 循环）：
  - cicd_queued + executable=null → 仍 cicd_queued
  - cicd_queued + 有构建号 → cicd_building
  - cicd_building + SUCCESS → autotest_queued（触发了第二个 job）
  - cicd_building + FAILURE → phase=done_cicd_failure，report status=failure，summary 含 `[构建失败]` 前缀，未触发 autotest
  - cicd_building + ABORTED → phase=done_cicd_failure（同上）
  - autotest_building + SUCCESS → phase=done_success，report status=success
  - autotest_building + FAILURE → phase=done_test_failure，report status=failure，summary 含失败用例
  - autotest_building + ABORTED → phase=done_test_aborted，report status=failure，summary 含 `[测试任务未正常完成]` 前缀
  - 超时（started_at 注入 25h 前）→ phase=done_timeout，report status=timeout
- 单次请求抛异常 → phase 不变。
- `get_report`：phase 以 `done_` 开头返回报告（按上表映射 status/summary）、否则 None（只读库）。
- driver_owner 抢占：陈旧 heartbeat 可被接管、新鲜的不被接管。

### JenkinsBuildStore 单测

CRUD + 抢占并发测试（threading + Barrier，沿用 test_store.py 模式）。

### test_cli.py（扩展）

`retrigger-build` 门禁：stage 不符 / branch 空 → 拒绝；合规 → 触发并 update。

### coordinator 测试

新增「超时报告 status=timeout → 直接 REJECTED、不调 analyzer、不计重试、反写 Linear」。`FakeJenkins` 加 `timeout` 模式返回超时报告。

### 集成测试

现有 happy path 不变（FakeJenkins ready=True 即时返回）。新增超时旁路一条。

### 不在本期范围

- `test_cli.py` 预存的 `_resolve_team_id` mock 失败（见记忆 preexisting-test-cli-failure）与本期无关，保持现状不顺手修。
- GitLab webhook 仍为骨架占位，本期不动（APScheduler 轮询为主驱动）。

## 受影响文件

- `plugins/bundled/repair/jenkins_client.py`（重写：真实 httpx + 自驱动状态机，`trigger_build` 接受 `repos: list[str]`）
- `plugins/bundled/repair/jenkins_build_store.py`（新增：`JenkinsBuildStore`，管理 `jenkins_builds` + `jenkins_cicd_builds` 两张表）
- `plugins/bundled/repair/store.py`（`RepairRun` + `repair_runs` 表新增 `repos` TEXT 字段）
- `plugins/bundled/repair/prompts.py`（`parse_developer_output` 解析 `【仓库】` 兼容单值和 JSON 数组）
- `plugins/bundled/repair/cli.py`（新增 `retrigger-build` 子命令；`trigger_build` 调用改传 repos 列表）
- `plugins/bundled/repair/coordinator.py`（`analyze_report` 加超时旁路；`trigger_build` 调用改传 repos 列表）
- `plugins/bundled/repair/plugin.py`（`on_start` 扫表拉起驱动；构造真实 `JenkinsClient`）
- `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md`（重跑能力说明；`【仓库】` 多服务输出格式）
- `plugins/config.json`（repair 段新增配置项）
- `.env.example`（新增 Jenkins env）
- 对应测试：`test_jenkins_client.py`（重写）、`test_jenkins_build_store.py`（新增）、`test_cli.py`（扩展）、`test_coordinator.py`（扩展）、`test_integration.py`（扩展）、`test_store.py`（扩展）、`test_prompts.py`（扩展）、`conftest.py`（`FakeJenkins` 扩展）
