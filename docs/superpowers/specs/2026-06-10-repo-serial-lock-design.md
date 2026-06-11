# 同 repo 修复串行锁 + 流程顺序调整 设计

日期：2026-06-10
关联：`2026-06-02-auto-bug-repair-pipeline-design.md`（原流水线设计）

## 背景与问题

自动 bug 修复流水线是事件驱动的：每个 Linear issue 是一次独立 webhook 触发，开修天然并发（无全局并发上限）。

开发阶段已有三层隔离，彼此不会踩：
- **工作目录**：每单 clone 到 `/tmp/repair/<identifier>/`，identifier 唯一。
- **分支**：每单 `fix/<identifier>`，唯一。
- **store 主键**：`repair_runs` 主键 `linear_issue_id`，WAL 跨进程安全。

真空地带：**同一 repo 被多个修复单同时构建测试**时无串行控制。两个修复分支可能同时占用同一 repo 的构建/测试资源，且各自基于同一 base 改重叠代码，最终 MR 合并冲突。

本设计的目标：**同一 repo（project_id）同时只允许一个修复单处于「改码→构建→测试→判定」的活跃窗口；后来的单在改码前申请锁，被占则退回初始态、人工重推。**

## 关键决策（已与用户确认）

1. **锁粒度**：以**完整 project_id** 为键（如 `piaozone/elc-integration/api-elc-invoice-imputation`）。两单归一化后的 project_id 相同才互斥。
2. **多 repo**：一个 issue 可能改多个服务。锁键是一组 project_id，**任一被占则整组拿不到锁**（不部分占用，避免占了 A 又被 B 挡导致 A 白白焊死）。
3. **判断时机在 skill、判断动作在后端**：developer agent 触发「申请锁」，但原子检查+占用由后端 SQLite 事务完成。**绝不让 LLM 自己做锁判断**（LLM 的「查-判-写」无原子性，两 agent 会同时判空双放行；且 LLM 可能不照做）。
4. **流程顺序调整**：建 MR 从 developer 阶段**后移到测试通过之后**。developer 阶段只 push 分支不建 MR；用修复分支先构建测试，拿报告判定修复完成，才由 coordinator 建 MR。
5. **锁释放点**：建 MR 成功（RESOLVED）即释放。合并到 test 仍由**人工在 GitLab 点**，锁不等合并。
6. **重修持锁**：同分支重修（代码错回转）期间锁连续持有，不释放不重新申请。
7. **被挡处理（纯乙方案）**：被挡单 stage 退回 `PENDING_REVIEW`（**非终态**），Linear 单退回 backlog（诊断单与人工单都退 backlog），回写提示，**人工重推，不自动重来**。

## 架构

### 数据：新增 `repo_locks` 表

与 `repair_runs` 同库（SQLite，WAL）。

```
repo (project_id)  TEXT PRIMARY KEY   -- 一个 project_id 一行；被占即存在该行
holder_issue_id    TEXT NOT NULL      -- 持有者 linear_issue_id（UUID）
holder_identifier  TEXT NOT NULL      -- 持有者人类可读单号（如 ENG-7），用于回写提示
acquired_at        INTEGER
```

> **为什么存 identifier**：被挡单要在 `【说明】` 和 Linear 评论里写「被 ENG-7 占用」给人看，UUID 对人无意义。锁表只有 UUID 的话，CLI 还得反查一次 identifier。多存一列 `holder_identifier`，acquire 时一并写入，CLI 直接返回，避免反查。

### RepairStore 新增方法（原子）

- `acquire_repos(issue_id: str, identifier: str, repos: list[str]) -> tuple[bool, str]`
  - 单事务内：查这组 repo 是否有任一被**别的** holder 占用（同 holder 重入算成功，幂等）。
  - 全空 → 整组 `INSERT`（写入 issue_id + identifier），返回 `(True, "")`。
  - 任一被占 → 不占任何一个，返回 `(False, blocking_identifier)`（返回**占用方的人类可读单号**，非 UUID）。
  - 事务串行化保证两 agent 并发申请时第二个必看到第一个已占。
- `release_repos(issue_id: str) -> None`：`DELETE FROM repo_locks WHERE holder_issue_id = ?`，释放该单全部锁。
- `list_locks() -> list[Row]`：供 poller reconcile。

### CLI 新增 `acquire-lock` 子命令

`plugins/bundled/repair/cli.py`：

```
cli.py acquire-lock --issue <issue_id> --identifier <ENG-N> --repos <p1,p2,...>
```

复用现有 `_make_store()`，调 `store.acquire_repos`，stdout 输出单行 JSON：
- 成功：`{"ok": true}`
- 被占：`{"ok": false, "blocked_by": "ENG-N"}`（`blocked_by` 是占用方人类可读单号）

### bug-fix-developer SKILL.md 调整

在 **Step 1（归一化 project_id）之后、Step 3（写复现测试）之前**插入「申请锁」步骤：

- agent 用 Step 1 解析出的完整 project_id 集合，调 `cli.py acquire-lock --issue <issue_id> --identifier <ENG-N> --repos <...>`。
- `ok: true` → 继续写测试改码。
- `ok: false` → **立即停止**，不写测试不改码不 push，按输出格式填 `【状态】阻塞`，`【说明】` 写明被 `blocked_by` 单占用。

> issue_id 与 identifier 需由 coordinator 通过 prompt 传给 developer（现有 `build_developer_prompt` 只传 identifier，需补传 issue UUID）。

**建 MR 后移**：Step 7 拆分——developer 阶段只 `git push origin <branch>`（不带 `merge_request.create` push option），建 MR 动作移交 coordinator 在测试通过后执行。SKILL.md「禁止 merge / 禁止自动合并」约束保持不变。

### 输出状态新增「阻塞」

`prompts.parse_developer_output` / `_parse_dev_status` 增加第三种状态：
- 识别 `阻塞` / `被占用` → 返回 `"blocked"`（区别于 `completed` / `failed`）。
- 保持现有保守语义：否定词优先，缺失/不明 → `failed`。

### coordinator 流程调整

`_develop_and_build`（developer 阶段，持锁中）：
- developer 返回后解析 status：
  - `blocked` → 不构建；stage 退回 `PENDING_REVIEW`；Linear 单退回 backlog；释放锁（防御性，理论上 agent 被挡时未占到锁，但同 holder 重入语义下 release 幂等无害）；回写 `🔒 涉及服务 <X> 正被 <ENG-N> 修复中，已退回，请待其完成后重新触发`。
  - `failed` → 现有逻辑（落 REJECTED / 退回，回写 agent 输出），并释放锁。
  - `completed` 且有 branch → 触发 Jenkins 构建（用修复分支），落 BUILDING。**此时不建 MR**。

`analyze_report` → 判定回转（持锁中）：
- `resolved` → coordinator 在该单 `/tmp/repair/<identifier>/` 工作目录跑 `git push -o merge_request.create -o merge_request.target=test ...` 建 MR；解析 MR URL；**释放锁**；回写「修复完成 + MR 链接」；落 RESOLVED。
- `code_error` → 同分支重修（`_handle_code_error`），**不释放锁**，重修后再构建。
- `root_cause_error` → **释放锁**；退回 `PENDING_REVIEW` 重诊断。
- `missing_dependency` → **释放锁**；建子单；落 BLOCKED。
- 各类 `_reject`（超限）→ **释放锁**；落 REJECTED。

> coordinator 建 MR 依赖 `/tmp/repair/<identifier>/` 工作目录仍在。已确认无任何清理逻辑，developer 会话结束后目录保留，coordinator 可复用。

### Stranding 兜底

`poll_building_runs` 每轮顺带 reconcile：
- 扫 `store.list_locks()`，对每个锁查 holder 的当前 stage。
- 若 holder run 不存在，或 stage 不在活跃态（`developing` / `building` / `analyzing`）→ 自动 `release_repos(holder)`。
- 防 run 崩溃把 repo 永久焊死。轻量，复用现有 poller，无需新定时器。

> **为什么不会误杀正在跑的锁**：锁是 developer 在 agent 会话内、改码前申请的。而 coordinator 在调 developer agent **之前**就已把 stage 推到 `DEVELOPING`（`coordinator.py:184`，先于申请锁发生）。因此锁存在的整个 happy path 窗口内，holder 的 stage 恒为活跃态（DEVELOPING/BUILDING/ANALYZING），reconcile 只会回收 holder 已崩溃/已落终态却残留的锁，不会误伤进行中的单。`PENDING_REVIEW` 不在活跃态列表，正好覆盖「被挡退回后若残留锁」的清理（双保险）。

## 锁生命周期总表

| 事件 | 锁动作 |
|------|--------|
| developer 申请（改码前） | acquire（整组，任一被占则整组失败） |
| 被占退回 PENDING_REVIEW | release（幂等防御） |
| developer failed | release |
| developer completed → 构建 | 持有 |
| 代码错同分支重修 | 持有（不释放不重申请） |
| 建 MR 成功 → RESOLVED | release |
| 根因错退回 / 漏依赖 BLOCKED / 超限 REJECTED | release |
| holder 崩溃卡死 | poller reconcile 自动 release |

## 错误处理

- 所有 Linear 回写 try/except 吞异常，不影响修复主流程（沿用现有约定）。
- acquire-lock CLI 失败（DB 异常）：CLI 返回 `{"ok": false, "error": ...}`，agent 视同被挡停止（保守，绝不在锁不确定时改码）。
- release 幂等：DELETE 不存在的 holder 无副作用。

## 测试

- `store`：acquire 全空成功 / 任一被占整组失败（返回占用方 identifier）/ 同 holder 重入 / 并发两申请只一个成功（事务串行）/ release 幂等 / list_locks 含 identifier。
- `cli`：acquire-lock 成功与被占两种 stdout（被占返回 `blocked_by` 为 identifier）。
- `prompts`：`_parse_dev_status` 识别「阻塞」；parse_developer_output status=blocked。
- `coordinator`：blocked 退回 PENDING_REVIEW + backlog + release；resolved 才建 MR + release；code_error 重修持锁；root_cause/missing_dep/reject 均 release；poll reconcile 释放陈旧锁。
- 沿用现有 mock Jenkins（恒 ready+pass）跑 happy path。

## 不做（YAGNI）

- 不做自动 rebase / 自动解冲突。
- 不做自动合并到 test（人工点）。
- 不做被挡单自动重来（人工重推）。
- 不引入 asyncio 内存锁（构建测试异步跨进程，必须落库）。
- 不引入 GitLab REST 客户端（建 MR 仍走 git push options）。
