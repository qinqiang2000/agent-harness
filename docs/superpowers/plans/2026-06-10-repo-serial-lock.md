# 同 repo 修复串行锁 + 流程顺序调整 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给自动 bug 修复流水线加「同 project_id 串行锁」（developer 改码前原子申请、任一被占整组拒绝、人工重推），并把建 MR 从 developer 阶段后移到测试通过之后。

**Architecture:** 锁落 SQLite `repo_locks` 表，`RepairStore` 提供原子 acquire/release；developer skill 改码前调 `cli.py acquire-lock` 触发后端原子检查；coordinator 在测试通过（resolved）时才用 git push options 建 MR 并释放锁；poller 每轮 reconcile 回收崩溃残留锁。

**Tech Stack:** Python 3 / SQLite (WAL) / pytest / git CLI (push options) / 现有 repair 插件（plugins/bundled/repair/）。

**关联 spec:** `docs/superpowers/specs/2026-06-10-repo-serial-lock-design.md`

---

## 文件结构

| 文件 | 职责 | 改动 |
|------|------|------|
| `plugins/bundled/repair/store.py` | repair_runs + repo_locks 持久化 | 加 `repo_locks` 建表 + `acquire_repos`/`release_repos`/`list_locks` |
| `plugins/bundled/repair/cli.py` | agent 调用入口 | 加 `acquire-lock` 子命令 |
| `plugins/bundled/repair/prompts.py` | prompt 拼装 + 输出解析 | `_parse_dev_status` 识别「阻塞」；`build_developer_prompt` 加 `issue_id` 参数 |
| `plugins/bundled/repair/mr_builder.py` | **新建**：测试通过后用 git push options 建 MR | 新文件，可注入便于测试 |
| `plugins/bundled/repair/coordinator.py` | 状态机编排 | dev 阶段不建 MR；blocked 处理；resolved 建 MR；各回转释放锁；poll reconcile |
| `plugins/bundled/repair/plugin.py` | 插件装配 | 构造并注入 `MRBuilder` |
| `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md` | developer skill | 加申请锁步骤；Step 7 改为只 push 不建 MR |
| `tests/repair/test_store.py` 等 | 测试 | 对应新增用例 |

---

## Task 0：基线确认

- [ ] **Step 1: 跑现有 repair 测试，确认全绿基线**

Run: `source .venv/bin/activate && python -m pytest tests/repair/ -q`
Expected: PASS（全绿，约 68 passed）。若有失败先停下排查，不要在红的基线上改。

---

## Task 1：repo_locks 表 + 原子 acquire/release/list

**Files:**
- Modify: `plugins/bundled/repair/store.py`（`_init_db` 加建表；类尾部加三个方法）
- Test: `tests/repair/test_store.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_store.py` 末尾：

```python
@pytest.mark.unit
def test_acquire_repos_empty_succeeds(store):
    ok, blocker = store.acquire_repos("issue-1", "ENG-1", ["repo/a", "repo/b"])
    assert ok is True
    assert blocker == ""
    locks = {r["repo"]: r["holder_issue_id"] for r in store.list_locks()}
    assert locks == {"repo/a": "issue-1", "repo/b": "issue-1"}


@pytest.mark.unit
def test_acquire_repos_any_held_fails_whole_group(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/b"])
    # issue-2 想要 a+b，b 已被 issue-1 占 → 整组失败，a 也不占
    ok, blocker = store.acquire_repos("issue-2", "ENG-2", ["repo/a", "repo/b"])
    assert ok is False
    assert blocker == "ENG-1"  # 返回占用方人类可读单号
    repos_held = {r["repo"] for r in store.list_locks()}
    assert repos_held == {"repo/b"}  # repo/a 没被 issue-2 占


@pytest.mark.unit
def test_acquire_repos_same_holder_reentrant(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/a"])
    ok, blocker = store.acquire_repos("issue-1", "ENG-1", ["repo/a", "repo/c"])
    assert ok is True
    assert blocker == ""
    repos_held = {r["repo"] for r in store.list_locks()}
    assert repos_held == {"repo/a", "repo/c"}


@pytest.mark.unit
def test_release_repos_is_idempotent(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/a", "repo/b"])
    store.release_repos("issue-1")
    assert store.list_locks() == []
    store.release_repos("issue-1")  # 再次释放不抛错
    assert store.list_locks() == []


@pytest.mark.unit
def test_release_repos_only_own_holder(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/a"])
    store.acquire_repos("issue-2", "ENG-2", ["repo/b"])
    store.release_repos("issue-1")
    repos_held = {r["repo"]: r["holder_issue_id"] for r in store.list_locks()}
    assert repos_held == {"repo/b": "issue-2"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_store.py -k acquire_repos -q`
Expected: FAIL — `AttributeError: 'RepairStore' object has no attribute 'acquire_repos'`

- [ ] **Step 3: 加建表语句**

在 `store.py` 的 `_init_db` 方法里，现有 `CREATE TABLE IF NOT EXISTS repair_runs (...)` 之后、`with self._conn() as conn:` 块内追加第二条建表（与第一条同一个 `conn.execute` 风格，分两次 execute）：

```python
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repo_locks (
                    repo              TEXT PRIMARY KEY,
                    holder_issue_id   TEXT NOT NULL,
                    holder_identifier TEXT NOT NULL,
                    acquired_at       INTEGER NOT NULL
                )
                """
            )
```

- [ ] **Step 4: 加三个方法**

在 `store.py` 的 `RepairStore` 类内、`_increment` 方法之后、`@staticmethod _row_to_run` 之前，加：

```python
    def acquire_repos(
        self, issue_id: str, identifier: str, repos: list
    ) -> tuple:
        """原子申请一组 repo 锁。任一被别的 holder 占用则整组失败，不占任何一个。

        同一 holder 重入算成功（幂等）。返回 (ok, blocking_identifier)：
        成功 (True, "")；被占 (False, 占用方人类可读单号)。
        """
        now = int(time.time())
        with self._conn() as conn:
            # 单事务内先全查：有无被别的 holder 占用
            for repo in repos:
                row = conn.execute(
                    "SELECT holder_issue_id, holder_identifier FROM repo_locks WHERE repo = ?",
                    (repo,),
                ).fetchone()
                if row is not None and row["holder_issue_id"] != issue_id:
                    return (False, row["holder_identifier"])
            # 全空（或同 holder 重入）→ 整组占用（INSERT OR REPLACE 处理重入）
            for repo in repos:
                conn.execute(
                    "INSERT OR REPLACE INTO repo_locks "
                    "(repo, holder_issue_id, holder_identifier, acquired_at) "
                    "VALUES (?, ?, ?, ?)",
                    (repo, issue_id, identifier, now),
                )
        return (True, "")

    def release_repos(self, issue_id: str) -> None:
        """释放某单持有的全部 repo 锁，幂等。"""
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM repo_locks WHERE holder_issue_id = ?", (issue_id,)
            )

    def list_locks(self) -> List[sqlite3.Row]:
        """列出所有持有中的 repo 锁，供 poller reconcile。"""
        with self._conn() as conn:
            return conn.execute("SELECT * FROM repo_locks").fetchall()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_store.py -q`
Expected: PASS（含原有用例 + 5 个新用例）

- [ ] **Step 6: 提交**

> 注意：用户全局约定「本地代码改动一律不主动 git commit，由用户自己提交」。**本计划所有 commit 步骤仅为逻辑边界标记，实际是否提交由用户决定。** 执行时若用户未明确要求提交，跳过 git commit，仅作为「该任务完成」的检查点。

---

## Task 2：cli.py acquire-lock 子命令

**Files:**
- Modify: `plugins/bundled/repair/cli.py`（加 `acquire_lock_cmd` + main 里加 subparser）
- Test: `tests/repair/test_cli.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_cli.py` 末尾：

```python
@pytest.mark.unit
def test_acquire_lock_success_prints_ok(tmp_path, capsys):
    from unittest.mock import MagicMock
    store = MagicMock()
    store.acquire_repos.return_value = (True, "")
    with patch.object(cli, "_make_store", return_value=store):
        cli.acquire_lock_cmd(
            issue_id="issue-uuid", identifier="ENG-7", repos_csv="repo/a,repo/b"
        )
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out == {"ok": True}
    store.acquire_repos.assert_called_once_with(
        "issue-uuid", "ENG-7", ["repo/a", "repo/b"]
    )


@pytest.mark.unit
def test_acquire_lock_blocked_prints_blocked_by(tmp_path, capsys):
    from unittest.mock import MagicMock
    store = MagicMock()
    store.acquire_repos.return_value = (False, "ENG-3")
    with patch.object(cli, "_make_store", return_value=store):
        cli.acquire_lock_cmd(
            issue_id="issue-uuid", identifier="ENG-7", repos_csv="repo/a"
        )
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out == {"ok": False, "blocked_by": "ENG-3"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_cli.py -k acquire_lock -q`
Expected: FAIL — `AttributeError: module 'plugins.bundled.repair.cli' has no attribute 'acquire_lock_cmd'`

- [ ] **Step 3: 加 acquire_lock_cmd 函数**

在 `cli.py` 的 `create_issue_cmd` 之后、`main()` 之前加：

```python
def acquire_lock_cmd(issue_id: str, identifier: str, repos_csv: str) -> None:
    """原子申请一组 repo 锁，结果打到 stdout（供 developer skill 解析）。

    成功：{"ok": true}；被占：{"ok": false, "blocked_by": "<占用方单号>"}。
    DB 异常：{"ok": false, "error": "..."}（agent 视同被挡，保守停止）。
    """
    repos = [r.strip() for r in repos_csv.split(",") if r.strip()]
    store = _make_store()
    ok, blocker = store.acquire_repos(issue_id, identifier, repos)
    if ok:
        print(json.dumps({"ok": True}, ensure_ascii=False))
    else:
        print(json.dumps({"ok": False, "blocked_by": blocker}, ensure_ascii=False))
```

- [ ] **Step 4: main() 加 subparser**

在 `cli.py` 的 `main()` 里，现有 `p_create = sub.add_parser("create-issue", ...)` 那段之后、`args = parser.parse_args()` 之前加：

```python
    p_lock = sub.add_parser("acquire-lock", help="原子申请一组 repo 锁")
    p_lock.add_argument("--issue", required=True, help="Linear issue UUID")
    p_lock.add_argument("--identifier", required=True, help="人类可读单号，如 ENG-7")
    p_lock.add_argument("--repos", required=True, help="逗号分隔的 project_id 列表")
```

并在 `main()` 的命令分发处，现有 `if args.cmd == "create-issue":` 块之后加：

```python
    elif args.cmd == "acquire-lock":
        try:
            acquire_lock_cmd(args.issue, args.identifier, args.repos)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_cli.py -q`
Expected: PASS

- [ ] **Step 6: 检查点**（见 Task 1 Step 6 提交约定）

---

## Task 3：prompts._parse_dev_status 识别「阻塞」

**Files:**
- Modify: `plugins/bundled/repair/prompts.py`（`_parse_dev_status` + `parse_developer_output`）
- Test: `tests/repair/test_prompts.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_prompts.py` 末尾（若文件无 import，按其现有头部风格加 `from plugins.bundled.repair import prompts`）：

```python
@pytest.mark.unit
def test_parse_dev_status_recognizes_blocked():
    text = "【状态】阻塞\n【说明】涉及服务被 ENG-3 占用"
    assert prompts.parse_developer_output(text)["status"] == "blocked"


@pytest.mark.unit
def test_parse_dev_status_blocked_by_keyword_beizhanyong():
    text = "【状态】被占用\n【说明】repo 正被其他单修复"
    assert prompts.parse_developer_output(text)["status"] == "blocked"


@pytest.mark.unit
def test_parse_dev_status_completed_still_works():
    text = "【状态】完成\n【分支】fix/ENG-1"
    assert prompts.parse_developer_output(text)["status"] == "completed"


@pytest.mark.unit
def test_parse_dev_status_missing_is_failed():
    assert prompts.parse_developer_output("无状态字段")["status"] == "failed"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_prompts.py -k dev_status -q`
Expected: FAIL — blocked 用例返回 "failed" 而非 "blocked"

- [ ] **Step 3: 改 _parse_dev_status**

把 `prompts.py` 的 `_parse_dev_status` 函数体替换为（在否定词判断**之前**先判阻塞，因为「阻塞」不含完成/成功字样，但要明确返回独立状态）：

```python
def _parse_dev_status(text: str) -> str:
    """解析 developer【状态】。

    优先级：阻塞（锁冲突）→ 否定/失败信号 → 完成/成功 → 其余(含缺失)=failed。
    「未完成」含「完成」二字，故否定词须先于完成判断。
    """
    line = _extract(r"【状态】\s*([^\n]+)", text)
    if not line:
        return "failed"
    if "阻塞" in line or "被占用" in line:
        return "blocked"
    for neg in ("未完成", "没完成", "未成功", "失败", "待批准", "未通过", "中止", "放弃"):
        if neg in line:
            return "failed"
    return "completed" if ("完成" in line or "成功" in line) else "failed"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_prompts.py -q`
Expected: PASS

- [ ] **Step 5: 检查点**

---

## Task 4：build_developer_prompt 补传 issue_id

**Files:**
- Modify: `plugins/bundled/repair/prompts.py`（`build_developer_prompt` 签名 + 模板）
- Test: `tests/repair/test_prompts.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_prompts.py`：

```python
@pytest.mark.unit
def test_build_developer_prompt_includes_issue_id():
    p = prompts.build_developer_prompt(
        issue_id="issue-uuid-xyz",
        identifier="ENG-1",
        root_cause="空指针",
        evidence="日志",
        repair_plan="判空",
        repo="ai-agent/foo",
        branch="fix/ENG-1",
        is_retry=False,
        last_report="",
    )
    assert "issue-uuid-xyz" in p
    assert "ENG-1" in p
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_prompts.py -k issue_id -q`
Expected: FAIL — `TypeError: build_developer_prompt() got an unexpected keyword argument 'issue_id'`

- [ ] **Step 3: 改函数签名与模板**

把 `prompts.py` 的 `build_developer_prompt` 改为（新增首参 `issue_id`，并在 parts 里加一行明确 UUID，供 skill 申请锁时使用）：

```python
def build_developer_prompt(
    issue_id: str,
    identifier: str,
    root_cause: str,
    evidence: str,
    repair_plan: str,
    repo: str,
    branch: str,
    is_retry: bool,
    last_report: str,
) -> str:
    """拼出调用 bug-fix-developer skill 的 prompt。"""
    repo_line = (
        f"目标仓库: {repo}"
        if repo
        else "目标仓库: （未指定，请从下方修复计划/描述中识别服务名，"
        "再查 service-repo-map.md 解析成完整 project_id）"
    )
    parts = [
        f"严格按 skill: bug-fix-developer 执行 TDD 修复任务。",
        f"\n# 修复任务 {identifier}",
        f"Issue UUID（申请 repo 锁时用）: {issue_id}",
        repo_line,
        f"修复分支名（必须用此分支名）: {branch}",
        f"\n## 根因\n{root_cause}",
        f"\n## 证据\n{evidence}",
        f"\n## 修复计划\n{repair_plan}",
    ]
    if is_retry:
        parts.append(
            "\n## ⚠️ 这是同分支重修（上一轮修复未通过）\n"
            "在已有修复分支基础上继续修，先分析下方失败报告再改码。\n"
            f"\n### 上一轮失败报告\n{last_report}"
        )
    return "\n".join(parts)
```

- [ ] **Step 4: 跑测试确认通过（含发现的调用点报错）**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_prompts.py -q`
Expected: PASS。注意：coordinator.py 有两处调用 `build_developer_prompt`（约 `coordinator.py:191` 和 `:336`）尚未传 `issue_id`，下一个任务会改。此处先确保 prompts 单测通过。

- [ ] **Step 5: 检查点**

---

## Task 5：MRBuilder（测试通过后建 MR）

**Files:**
- Create: `plugins/bundled/repair/mr_builder.py`
- Test: `tests/repair/test_mr_builder.py`

> coordinator 在 resolved 时需要建 MR。建 MR 走 `git push -o merge_request.create`，在该单 `/tmp/repair/<identifier>/` 工作目录内执行。把它封成可注入的 `MRBuilder`（类比 `JenkinsClient`），真实实现 shell 出 git，测试用 fake 替身。

- [ ] **Step 1: 写失败测试**

新建 `tests/repair/test_mr_builder.py`：

```python
"""MRBuilder：测试通过后用 git push options 建 MR。

Run: python -m pytest tests/repair/test_mr_builder.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.mr_builder import MRBuilder, parse_mr_url


@pytest.mark.unit
def test_parse_mr_url_from_git_remote_output():
    out = (
        "remote:\n"
        "remote: View merge request for fix/ENG-1:\n"
        "remote:   http://gitlab.example/ai-agent/foo/-/merge_requests/42\n"
        "remote:\n"
    )
    assert parse_mr_url(out) == "http://gitlab.example/ai-agent/foo/-/merge_requests/42"


@pytest.mark.unit
def test_parse_mr_url_returns_empty_when_absent():
    assert parse_mr_url("everything up-to-date") == ""


@pytest.mark.unit
def test_build_mr_invokes_git_push_with_options():
    captured = {}

    def fake_run(cmd, cwd, capture):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return "remote:   http://gitlab.example/foo/-/merge_requests/7\n"

    builder = MRBuilder(runner=fake_run)
    url = builder.build_mr(
        identifier="ENG-1", branch="fix/ENG-1", title="fix(ENG-1): 修复空指针"
    )

    assert url == "http://gitlab.example/foo/-/merge_requests/7"
    assert captured["cwd"] == "/tmp/repair/ENG-1"
    joined = " ".join(captured["cmd"])
    assert "merge_request.create" in joined
    assert "merge_request.target=test" in joined
    assert "fix/ENG-1" in captured["cmd"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_mr_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'plugins.bundled.repair.mr_builder'`

- [ ] **Step 3: 写 mr_builder.py**

新建 `plugins/bundled/repair/mr_builder.py`：

```python
"""测试通过后由 coordinator 调用，在修复单工作目录内用 git push options 建 MR。

不引入 GitLab REST 客户端（沿用现有 push options 方案）。push 用写权限
GITLAB_PUSH_TOKEN（回退 GITLAB_TOKEN）。runner 可注入便于测试。
"""

import logging
import os
import re
import subprocess
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MR_URL_RE = re.compile(r"(https?://\S*/-/merge_requests/\d+)")


def parse_mr_url(git_output: str) -> str:
    """从 git push 的 remote 输出里解析 MR URL，无则返回空串。"""
    m = _MR_URL_RE.search(git_output)
    return m.group(1) if m else ""


def _default_runner(cmd: list, cwd: str, capture: bool = True) -> str:
    """实跑 git，返回合并后的 stdout+stderr（push 的 remote 行在 stderr）。"""
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=120
    )
    return (proc.stdout or "") + (proc.stderr or "")


class MRBuilder:
    """在 /tmp/repair/<identifier>/ 内 git push -o merge_request.create 建 MR。"""

    def __init__(self, runner: Optional[Callable] = None):
        self._run = runner or _default_runner

    def build_mr(self, identifier: str, branch: str, title: str) -> str:
        """push 修复分支并建 MR（target=test），返回解析到的 MR URL（失败返回空串）。"""
        work = f"/tmp/repair/{identifier}"
        cmd = [
            "git", "push",
            "-o", "merge_request.create",
            "-o", "merge_request.target=test",
            "-o", f"merge_request.title={title}",
            "origin", branch,
        ]
        try:
            output = self._run(cmd, work, True)
        except Exception:
            logger.error("[Repair] build_mr git push failed: %s", identifier, exc_info=True)
            return ""
        return parse_mr_url(output)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_mr_builder.py -q`
Expected: PASS

- [ ] **Step 5: 检查点**

---

## Task 6：coordinator dev 阶段——blocked 处理 + 不再建 MR

**Files:**
- Modify: `plugins/bundled/repair/coordinator.py`（`RepairCoordinator.__init__` 注入 mr_builder；`_develop_and_build`）
- Test: `tests/repair/test_coordinator.py`

> 本任务改 `_develop_and_build`：(1) 调 `build_developer_prompt` 补传 `issue_id`；(2) developer 返回 `status=="blocked"` → 不构建、release 锁、退回 PENDING_REVIEW、Linear 退 backlog、回写提示；(3) developer `completed` → 触发构建后**不再写 MR 链接评论**，改为「分支已推送，构建测试中」（MR 由 resolved 阶段建）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_coordinator.py`（`_make_coordinator` 需支持注入 fake mr_builder，先扩展它）。把文件顶部的 `_make_coordinator` 替换为：

```python
def _make_coordinator(store, fake_linear, agent_results, jenkins_ready=True, mr_builder=None):
    jenkins = FakeJenkins(ready=jenkins_ready)
    agent = FakeAgentService(agent_results)
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=jenkins,
        linear_client_factory=lambda ws: fake_linear,
        fix_retry_limit=3,
        rediagnose_limit=2,
        mr_builder=mr_builder or _FakeMRBuilder(),
    )
    return coord, agent, jenkins


class _FakeMRBuilder:
    def __init__(self, url="http://mr/built"):
        self.url = url
        self.calls = []

    def build_mr(self, identifier, branch, title):
        self.calls.append((identifier, branch, title))
        return self.url
```

新增用例：

```python
@pytest.mark.unit
async def test_develop_blocked_releases_lock_and_returns_to_pending(store, fake_linear):
    _seed_pending(store)
    # 模拟 repo 已被别的单占（developer 申请锁失败后输出阻塞）
    store.acquire_repos("other-issue", "ENG-9", ["ai-agent/foo"])
    blocked_output = "【状态】阻塞\n【说明】涉及服务 ai-agent/foo 正被 ENG-9 占用"
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [blocked_output])

    await coord.start_development("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.PENDING_REVIEW       # 退回初始态，非终态
    assert jenkins.triggered == []                  # 不构建
    assert any(kw["state_id"] == "s-backlog" for _, kw in fake_linear.updated)  # 退 backlog
    bodies = [b for _, b in fake_linear.comments]
    assert any("ENG-9" in b for b in bodies)        # 提示占用方
    # issue-1 自己未占到任何锁（仍只有 other-issue 持锁）
    holders = {r["holder_issue_id"] for r in store.list_locks()}
    assert holders == {"other-issue"}


@pytest.mark.unit
async def test_develop_completed_does_not_build_mr_in_dev_phase(store, fake_linear):
    _seed_pending(store)
    # 新流程：developer 只 push 分支，不返回 MR 链接
    dev_output = "【状态】完成\n【分支】fix/ENG-1\n【复现测试】FooTest.java"
    fake_mr = _FakeMRBuilder()
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output], mr_builder=fake_mr)

    await coord.start_development("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.BUILDING
    assert jenkins.triggered == [("ai-agent/foo", "fix/ENG-1")]
    assert fake_mr.calls == []                       # dev 阶段不建 MR
    bodies = [b for _, b in fake_linear.comments]
    assert not any("merge_request" in b.lower() for b in bodies)
```

注意：`test_start_development_happy_path` / `test_develop_completed_status_triggers_build` 等旧用例里 dev_output 带【MR链接】并断言 `run.mr_url`。新流程 dev 阶段不再产出 MR，这些断言需调整——把它们对 `mr_url` 的断言移除或改为空串。在本 Step 一并改：

- `test_start_development_happy_path`：删去 `assert run.mr_url == "http://mr/1"` 这一行。
- `test_develop_comment_includes_summary`：保留（断言【说明】仍回写），不依赖 MR。
- `test_start_manual_repair_happy_path` / `test_start_manual_repair_with_session_streams_to_session`：把对 `http://mr/m1` 的断言改为断言「分支已推送/构建测试中」的提示文案（见 Step 3 文案）。

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'mr_builder'` 及新用例失败。

- [ ] **Step 3: 改 coordinator.__init__ 与 _develop_and_build**

(a) `RepairCoordinator.__init__` 加 `mr_builder` 参数与存储。把 `__init__` 签名与体改为：

```python
    def __init__(
        self,
        agent_service,
        store: RepairStore,
        jenkins: JenkinsClient,
        linear_client_factory: Callable,
        fix_retry_limit: int = 3,
        rediagnose_limit: int = 2,
        mr_builder=None,
    ):
        self.agent_service = agent_service
        self.store = store
        self.jenkins = jenkins
        self._linear_factory = linear_client_factory
        self.N = fix_retry_limit
        self.M = rediagnose_limit
        if mr_builder is None:
            from plugins.bundled.repair.mr_builder import MRBuilder
            mr_builder = MRBuilder()
        self.mr_builder = mr_builder
```

(b) 在 `_develop_and_build` 里，把 `build_developer_prompt(` 调用补传 `issue_id=run.linear_issue_id`（现有调用约 `coordinator.py:191`）：

```python
        prompt = prompts.build_developer_prompt(
            issue_id=run.linear_issue_id,
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence=run.evidence or run.last_report or "（见 Linear 单描述）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=branch,
            is_retry=False,
            last_report="",
        )
```

(c) 在 `_develop_and_build` 解析 `parsed = prompts.parse_developer_output(result_text)` 之后、现有 `if parsed["status"] != "completed" ...` 之前，插入 blocked 分支：

```python
        # 锁冲突：developer 申请 repo 锁被挡 → 不构建，退回初始态，人工重推。
        if parsed["status"] == "blocked":
            logger.info("[Repair] developer blocked by repo lock: %s", linear_issue_id)
            self.store.release_repos(linear_issue_id)  # 防御：被挡时本单未占到锁，幂等
            self.store.update(linear_issue_id, stage=Stage.PENDING_REVIEW)
            await self._set_issue_linear_state(client, linear_issue_id, "backlog")
            await notify(
                "🔒 涉及的服务正被其他修复单占用，已退回。请待其完成后重新触发。\n\n"
                f"{result_text}",
                final=True,
            )
            return
```

(d) 把现有 `completed` 成功段的 MR 文案改掉。现有（约 `coordinator.py:255-273`）触发构建 + 写「已自动开发并建 MR：...」。新流程 dev 阶段无 MR，改为：

```python
        build_id = self.jenkins.trigger_build(repo=resolved_repo, branch=new_branch)

        self.store.update(
            linear_issue_id,
            stage=Stage.BUILDING,
            repo=resolved_repo,
            branch=new_branch,
            develop_session_id=session_id_for_store or "",
            jenkins_build_id=build_id,
        )

        result_msg = (
            f"已完成代码修复并推送分支：{new_branch}\n"
            f"构建+测试已触发，等待测试报告。MR 将在测试通过后自动创建。"
        )
        if summary:
            result_msg += f"\n\n修复摘要：{summary}"
        await notify(result_msg, final=True)
```

> 注意：移除了对 `parsed["mr_url"]` / `mr_url` 的写入（dev 阶段不再有 MR）。`failed` 分支（现有 `if parsed["status"] != "completed" or not parsed["branch"]:`）保持不变，但因 blocked 已在前面 return，此处 `!= "completed"` 仍能正确兜住 failed。

(e) `failed` 分支末尾补释放锁（developer 跑起来后可能已占锁，失败要还）。在现有 `failed` 段 `self.store.update(linear_issue_id, stage=Stage.REJECTED)` 之后加一行 `self.store.release_repos(linear_issue_id)`。同样在开头 agent 抛异常的 `except` 段（`on_agent_failure` 落库后）加 `self.store.release_repos(linear_issue_id)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -q`
Expected: PASS（新用例 + 调整后的旧用例）

- [ ] **Step 5: 检查点**

---

## Task 7：coordinator resolved 阶段建 MR + 释放锁

**Files:**
- Modify: `plugins/bundled/repair/coordinator.py`（`_handle_resolved`）
- Test: `tests/repair/test_coordinator.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_coordinator.py`：

```python
@pytest.mark.unit
async def test_resolved_builds_mr_and_releases_lock(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", jenkins_build_id="build-xyz", branch="fix/ENG-1")
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])  # dev 阶段已占锁
    fake_mr = _FakeMRBuilder(url="http://mr/final/1")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】已解决\n【依据】全绿\n【后续动作】无"], mr_builder=fake_mr
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    assert run.mr_url == "http://mr/final/1"            # MR 在 resolved 才建
    assert fake_mr.calls == [("ENG-1", "fix/ENG-1", fake_mr.calls[0][2])]
    assert "fix(ENG-1)" in fake_mr.calls[0][2]          # title 带单号
    assert store.list_locks() == []                     # 锁已释放
    bodies = [b for _, b in fake_linear.comments]
    assert any("http://mr/final/1" in b for b in bodies)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -k resolved_builds_mr -q`
Expected: FAIL — 当前 `_handle_resolved` 不建 MR、不释放锁，`run.mr_url` 为空且 `list_locks()` 非空。

- [ ] **Step 3: 改 _handle_resolved**

把 `coordinator.py` 的 `_handle_resolved` 替换为：

```python
    async def _handle_resolved(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        # 测试通过，现在才建 MR（git push -o merge_request.create）
        title = f"fix({run.linear_identifier}): 自动修复"
        mr_url = self.mr_builder.build_mr(
            identifier=run.linear_identifier, branch=run.branch, title=title
        )
        self.store.update(run.linear_issue_id, mr_url=mr_url)

        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        done_id = await self._state_id_by_type(client, team_id, "completed") if team_id else None
        if done_id:
            await client.update_issue(run.linear_issue_id, state_id=done_id)
        await client.create_comment(
            run.linear_issue_id,
            f"✅ Bug 已修复并通过测试。\n分支：{run.branch}\n"
            f"MR（待人工合并到 test）：{mr_url or '(建 MR 失败，请人工检查工作目录)'}\n\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.RESOLVED)
        self.store.release_repos(run.linear_issue_id)  # 建完 MR 即释放锁
```

- [ ] **Step 4: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -q`
Expected: PASS

- [ ] **Step 5: 检查点**

---

## Task 8：回转路径释放锁（root_cause / missing_dep / reject）+ 重修持锁 + 重修补 issue_id

**Files:**
- Modify: `plugins/bundled/repair/coordinator.py`（`_handle_code_error`、`_handle_root_cause_error`、`_handle_missing_dependency`、`_reject`）
- Test: `tests/repair/test_coordinator.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_coordinator.py`：

```python
@pytest.mark.unit
async def test_code_error_retry_keeps_lock(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", develop_session_id="claude-sess-1", branch="fix/ENG-1")
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])
    coord, agent, _ = _make_coordinator(
        store, fake_linear,
        [
            "【判定】代码错\n【依据】NPE 仍在\n【后续动作】补判空",
            "【状态】完成\n【分支】fix/ENG-1",
        ],
    )

    await coord.analyze_report("issue-1")

    # 重修期间锁持续持有（仍是 issue-1）
    holders = {r["holder_issue_id"] for r in store.list_locks()}
    assert holders == {"issue-1"}


@pytest.mark.unit
async def test_root_cause_error_releases_lock(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】根因错\n【依据】根因站不住\n【后续动作】回诊断"]
    )

    await coord.analyze_report("issue-1")

    assert store.list_locks() == []


@pytest.mark.unit
async def test_missing_dependency_releases_lock(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】漏依赖\n【依据】需改上游\n【后续动作】建子单：修上游 X"]
    )

    await coord.analyze_report("issue-1")

    assert store.list_locks() == []


@pytest.mark.unit
async def test_reject_releases_lock(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", rediagnose_count=1)
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】根因错\n【依据】x\n【后续动作】y"]  # 第 2 次 → 超 M=2 → reject
    )

    await coord.analyze_report("issue-1")

    assert store.get("issue-1").stage == Stage.REJECTED
    assert store.list_locks() == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -k "releases_lock or retry_keeps_lock" -q`
Expected: FAIL — 释放类用例 `list_locks()` 仍非空。

- [ ] **Step 3: 改四个 handler**

(a) `_handle_code_error`：重修走同分支，**不释放锁**。仅补 `build_developer_prompt` 的 `issue_id`（现有约 `coordinator.py:336`），其余不变：

```python
        prompt = prompts.build_developer_prompt(
            issue_id=run.linear_issue_id,
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence="（见上一轮失败报告）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=run.branch,
            is_retry=True,
            last_report=run.last_report,
        )
```

(b) `_handle_root_cause_error`：在现有 `self.store.update(run.linear_issue_id, stage=Stage.PENDING_REVIEW)` 之后加：

```python
        self.store.release_repos(run.linear_issue_id)
```

(c) `_handle_missing_dependency`：在现有 `self.store.update(run.linear_issue_id, stage=Stage.BLOCKED)` 之后加：

```python
        self.store.release_repos(run.linear_issue_id)
```

(d) `_reject`：在现有 `self.store.update(run.linear_issue_id, stage=Stage.REJECTED)` 之后加：

```python
        self.store.release_repos(run.linear_issue_id)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -q`
Expected: PASS

- [ ] **Step 5: 检查点**

---

## Task 9：poll_building_runs reconcile 陈旧锁

**Files:**
- Modify: `plugins/bundled/repair/coordinator.py`（`poll_building_runs`）
- Test: `tests/repair/test_coordinator.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/repair/test_coordinator.py`：

```python
@pytest.mark.unit
async def test_poll_reconciles_stale_lock_when_holder_terminal(store, fake_linear):
    # holder 已落终态（RESOLVED），但锁残留 → poll 应回收
    _seed_pending(store, stage=Stage.RESOLVED)
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])
    coord, agent, _ = _make_coordinator(store, fake_linear, [])

    await coord.poll_building_runs()

    assert store.list_locks() == []


@pytest.mark.unit
async def test_poll_reconciles_lock_when_holder_run_missing(store, fake_linear):
    # holder run 不存在（崩溃丢失）→ poll 回收
    store.acquire_repos("ghost-issue", "ENG-X", ["ai-agent/bar"])
    coord, agent, _ = _make_coordinator(store, fake_linear, [])

    await coord.poll_building_runs()

    assert store.list_locks() == []


@pytest.mark.unit
async def test_poll_keeps_lock_when_holder_active(store, fake_linear):
    # holder 仍在活跃态（DEVELOPING）→ 锁保留，不误杀
    _seed_pending(store, stage=Stage.DEVELOPING)
    store.acquire_repos("issue-1", "ENG-1", ["ai-agent/foo"])
    coord, agent, _ = _make_coordinator(store, fake_linear, [])

    await coord.poll_building_runs()

    holders = {r["holder_issue_id"] for r in store.list_locks()}
    assert holders == {"issue-1"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -k poll_recon -q`
Expected: FAIL — reconcile 未实现，陈旧锁仍在。

- [ ] **Step 3: 改 poll_building_runs**

把 `coordinator.py` 的 `poll_building_runs` 替换为（先推进 building，再 reconcile 锁）：

```python
    async def poll_building_runs(self) -> None:
        """扫所有 building 的 run 尝试分析报告；并 reconcile 陈旧 repo 锁。"""
        for run in self.store.list_by_stage(Stage.BUILDING):
            try:
                await self.analyze_report(run.linear_issue_id)
            except Exception:
                logger.error(
                    "[Repair] poll analyze failed: %s",
                    run.linear_issue_id,
                    exc_info=True,
                )
        self._reconcile_locks()

    _ACTIVE_STAGES = (Stage.DEVELOPING, Stage.BUILDING, Stage.ANALYZING)

    def _reconcile_locks(self) -> None:
        """回收 holder 已不存在或已不在活跃态的陈旧锁，防 run 崩溃焊死 repo。"""
        for lock in self.store.list_locks():
            holder = lock["holder_issue_id"]
            run = self.store.get(holder)
            if run is None or run.stage not in self._ACTIVE_STAGES:
                logger.info(
                    "[Repair] reconcile: releasing stale lock repo=%s holder=%s",
                    lock["repo"], holder,
                )
                self.store.release_repos(holder)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -q`
Expected: PASS

- [ ] **Step 5: 检查点**

---

## Task 10：bug-fix-developer SKILL.md——申请锁步骤 + Step 7 只 push 不建 MR

**Files:**
- Modify: `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md`

> 纯文档/prompt 改动，无单测。改完用真实 agent 联调验证（本计划范围外）。改动要点：Step 1 之后插「申请锁」；Step 7 拆为只 push 分支、不带 merge_request.create；输出格式加【状态】阻塞说明。

- [ ] **Step 1: Step 1 之后插入申请锁步骤**

在 SKILL.md 的「## Step 1：解析仓库路径...」整段之后、「## Step 2：理解代码」之前，插入：

```markdown
## Step 1.5：申请 repo 锁（改码前强制，违反即终止）

把本次要改动的**全部** project_id（Step 1 归一化后的；可能多个服务）作为一组，调后端原子申请锁：

\`\`\`bash
ISSUE_ID="<issue_id>"      # coordinator 传入的 Issue UUID（prompt 里「Issue UUID」一行）
IDENT="<identifier>"       # coordinator 传入单号，如 ENG-7
"$AGENTS_ROOT/.venv/bin/python" plugins/bundled/repair/cli.py acquire-lock \
  --issue "$ISSUE_ID" --identifier "$IDENT" --repos "<p1>,<p2>"
\`\`\`

解析 stdout 单行 JSON：

- `{"ok": true}` → 已拿到这组 repo 的独占锁，继续 Step 2。
- `{"ok": false, "blocked_by": "ENG-N"}` 或含 `"error"` → **立即停止**：不写测试、不改码、不 push。按输出格式填 `【状态】阻塞`，`【说明】` 写明被哪个单（ENG-N）占用。coordinator 会据此退回该单并提示人工稍后重推。

> 为什么由后端做判断：并发下两个 agent 不能各自「查-判-写」，否则会双双判空、双双开修。后端用一次 SQLite 事务原子检查+占用，杜绝竞态。锁在本单走完（测试通过建 MR / 被拒 / 退回）后由 coordinator 自动释放。
```

- [ ] **Step 2: 改 Step 7 为只 push 不建 MR**

把 SKILL.md「## Step 7：commit + push + 建 MR」整段标题与正文改为只推分支（删去 `merge_request.create` 等 push options），并说明 MR 由流水线在测试通过后创建：

```markdown
## Step 7：commit + push 修复分支（不建 MR）

push 用**写权限** `GITLAB_PUSH_TOKEN`（与 clone 的只读 `GITLAB_TOKEN` 分离）。
**只推分支，不要建 MR**——MR 由流水线在构建+测试通过后自动创建（你建了反而会重复）。

\`\`\`bash
cd "$WORK"
git add -A
git commit -m "fix($ID): <一句话修复说明>"

PUSH_TOKEN="${GITLAB_PUSH_TOKEN:-$GITLAB_TOKEN}"
PUSH_URL="$(echo $GITLAB_BASE | sed 's|://|://token:'"$PUSH_TOKEN"'@|')/$REPO.git"
git remote set-url --push origin "$PUSH_URL"

# 只推分支，禁止任何 merge_request.* push option
git push origin "$BRANCH"
\`\`\`

push 成功即视为开发完成，【MR链接】留空（由 coordinator 在测试通过后回填）。
```

- [ ] **Step 3: 更新输出格式说明，加入「阻塞」状态**

把 SKILL.md「## 输出格式」段里【状态】的说明补上第三种取值。将「**最后必须输出【状态】**」那段说明改为：

```markdown
**最后必须输出【状态】**，三选一：
- 「完成」：代码已改、已 commit 并成功 `git push` 分支。
- 「阻塞」：Step 1.5 申请 repo 锁被挡（被别的单占用）；此时不得改码，在【说明】写明占用方单号。
- 「失败」：任何中途卡住（改不动、push 失败、缺 token、被权限拦、放弃）。

coordinator 仅在【状态】完成且有【分支】时才触发构建；「阻塞」→ 退回该单等人工重推；「失败」→ 转人工。**不要为了凑格式谎报完成。**
```

并把示例块里 `【状态】完成 或 失败` 改为 `【状态】完成 / 阻塞 / 失败`。

- [ ] **Step 4: 自查文档无残留「建 MR」旧表述**

Run: `grep -n "merge_request.create" agent_cwd/.claude/skills/bug-fix-developer/SKILL.md`
Expected: 无输出（旧的 push options 建 MR 块已删干净）。

- [ ] **Step 5: 检查点**

---

## Task 11：装配 MRBuilder + 全量回归

**Files:**
- Modify: `plugins/bundled/repair/plugin.py`（构造 MRBuilder 注入 coordinator）
- Test: `tests/repair/test_plugin.py`、全量 `tests/repair/`

- [ ] **Step 1: 改 plugin.py 注入 mr_builder**

在 `plugin.py` 的 `RepairChannelPlugin.__init__` 里，现有构造 `RepairCoordinator(...)` 处补传 `mr_builder`。先在文件顶部 import 区加 `from plugins.bundled.repair.mr_builder import MRBuilder`，再把 coordinator 构造改为：

```python
        coord = RepairCoordinator(
            agent_service=api.agent_service,
            store=store,
            jenkins=jenkins,
            linear_client_factory=self._linear_client_factory,
            fix_retry_limit=int(self.config.get("fix_retry_limit", 3)),
            rediagnose_limit=int(self.config.get("rediagnose_limit", 2)),
            mr_builder=MRBuilder(),
        )
```

- [ ] **Step 2: 跑 plugin 测试**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_plugin.py -q`
Expected: PASS（若 test_plugin 构造 coordinator，确认未因新参数报错；mr_builder 有默认值，理论上向后兼容）。

- [ ] **Step 3: 全量回归**

Run: `source .venv/bin/activate && python -m pytest tests/repair/ -q`
Expected: PASS（全绿）。重点确认 `test_integration.py`、`test_manual_repair.py` 未因流程改动（dev 阶段不建 MR、新增 issue_id 参数）回归。若 `test_manual_repair.py` / `test_integration.py` 里有断言依赖 dev 阶段的 MR 文案，按 Task 6 同样思路调整为「分支已推送/构建测试中」。

- [ ] **Step 4: 检查点 + 通知用户联调待办**

提醒：以下需真实环境联调（本计划范围外）——
1. developer skill 的 acquire-lock 步骤需真实 agent 跑通（Step 1.5 prompt 是否被 agent 正确执行）。
2. MRBuilder 真实 git push -o 建 MR 的输出格式与 `parse_mr_url` 正则是否匹配你的 GitLab 版本。
3. coordinator 建 MR 依赖 `/tmp/repair/<identifier>/` 工作目录在 developer 会话后仍存活（已确认无清理逻辑）。

---

## 自检对照（spec 覆盖）

- 锁表 `repo_locks`（含 holder_identifier）→ Task 1 ✅
- acquire 整组/任一被占失败/同 holder 重入/事务串行 → Task 1 ✅
- CLI acquire-lock（--issue/--identifier/--repos）→ Task 2 ✅
- developer 改码前申请锁、被占停止 → Task 10 ✅
- 【状态】阻塞 解析 → Task 3 ✅
- build_developer_prompt 传 issue_id → Task 4、coordinator 调用点 Task 6/8 ✅
- 流程后移：dev 阶段不建 MR、resolved 才建 → Task 6 + Task 7 ✅
- MRBuilder（git push options，不引入 REST）→ Task 5 ✅
- 锁释放点（resolved/failed/blocked/root_cause/missing_dep/reject）+ 重修持锁 → Task 6/7/8 ✅
- poll reconcile 兜底 → Task 9 ✅
- 装配 → Task 11 ✅
