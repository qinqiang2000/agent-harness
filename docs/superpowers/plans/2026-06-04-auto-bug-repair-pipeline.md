# 自动化 Bug 修复流水线（Linear 中枢版）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 FastAPI + Claude Agent SDK 服务上落地一条以 Linear 为中枢的 bug 修复流水线：issue-diagnosis 判定代码 bug → 提 Linear 单 → 用户审核 → webhook 触发 TDD 自动改码并建 MR → 触发 Jenkins（占位）→ 三类归因分析回转，全程状态以 Linear + SQLite 运行时表为准。

**Architecture:** 新增 `plugins/bundled/repair/` 插件（store/coordinator/jenkins_client 占位/cli/prompts/plugin），扩展现有 `linear` 插件（补 `LinearClient` 写方法 + handler 委派分支），新增两个 agent skill（`bug-fix-developer` TDD 改码、`repair-report-analyzer` 三类归因），改 `issue-diagnosis` skill 加提单步，并为修复目录 `/tmp/repair/**` 定向放开 git 写权限（PreToolUse hook 限定工作目录）。RepairCoordinator 是纯编排：每方法 = 读 SQLite → 调 agent 或 Linear → 写新状态，N/M 重试由代码硬兜底。

**Tech Stack:** Python 3 / FastAPI / Claude Agent SDK / SQLite(WAL) / APScheduler / httpx / GraphQL(Linear) / git CLI + GitLab push options / pytest + pytest-asyncio

---

## 关键校准（实现前必读，已与代码现状核对）

这些是探查代码后确认的事实，偏离了设计文档的部分假设，实现时以此为准：

1. **scheduler 拿不到**：`app.py:141` 的 `AsyncIOScheduler` 是 `lifespan` 局部变量，插件无法访问。→ repair 插件在自己的 `on_start()` 里**自建** `AsyncIOScheduler`，`on_stop()` 里 shutdown。
2. **跨插件通信**：`linear` 与 `repair` 是两个独立插件，加载顺序不保证。linear handler 需委派 RepairCoordinator → 用 **module-level singleton**（`repair/coordinator.py` 暴露 `get_coordinator()`，linear handler 软依赖 import，未启用 repair 时 import 失败则跳过）。
3. **git 放开方式**：`agent_cwd/.claude/settings.json` 的 `deny` 优先级高于 `allow`，`allow` 无法覆盖 deny。→ 必须从 `settings.json` 的 deny **移除** git 写命令条目，改由 **PreToolUse hook** `restrict-git-write.py` 按工作目录（仅 `/tmp/repair/**`）放行，其余 git 写一律 deny；同时 hook 内禁 `git merge` / `git push` 主干 / `merge_when_pipeline_succeeds`。
4. **skills 加载语义**：SDK `skills` 参数是白名单 context filter，未列出的 skill 被隐藏。新会话固定 `skills=_default_skills`（env `DEFAULT_SKILLS`，缺省 `customer-service,issue-diagnosis-external`）。→ **不改 `agent_service.py`**；新 skill（`bug-fix-developer`、`repair-report-analyzer`、`issue-diagnosis`）由**用户把它们加进 `DEFAULT_SKILLS` 环境变量**来保证加载（用户已确认此方案）。计划只在部署说明里写明这一要求。
5. **LinearClient 缺写方法**：现有 `linear_client.py` 无 `create_issue` / `create_comment` / `get_team_states` / `get_workflow_states`。需补。
6. **运行环境**：仓库当前无 `.venv`、无 pytest / pytest-asyncio、无 pytest 配置文件。→ Task 0 准备测试环境。
7. **凭证分离**：clone/pull 用现有只读 `GITLAB_TOKEN`；push + 建 MR 用独立的写权限 `GITLAB_PUSH_TOKEN`（值待填）。
8. **Jenkins 占位**：本期 `JenkinsClient` 全 mock，签名按真实 build API 设计，body 留 TODO。

---

## 文件结构

新建/修改的文件及其职责：

| 文件 | 动作 | 职责 |
|---|---|---|
| `pytest.ini` | 创建 | pytest 配置（asyncio_mode=auto、testpaths、markers） |
| `tests/repair/__init__.py` | 创建 | 测试包 |
| `tests/repair/conftest.py` | 创建 | 共享 fixture：内存/临时 SQLite、fake LinearClient、fake JenkinsClient |
| `plugins/bundled/repair/__init__.py` | 创建 | 插件包 |
| `plugins/bundled/repair/plugin.json` | 创建 | 插件清单 |
| `plugins/bundled/repair/store.py` | 创建 | SQLite 运行时表 `repair_runs`（WAL、短事务、locked 重试、幂等 upsert） |
| `plugins/bundled/repair/prompts.py` | 创建 | 各阶段 prompt 模板 + 名→stateId 状态映射配置 + 解析函数 |
| `plugins/bundled/repair/jenkins_client.py` | 创建 | Jenkins 客户端（本期占位 mock） |
| `plugins/bundled/repair/coordinator.py` | 创建 | RepairCoordinator 纯编排 + module-level singleton |
| `plugins/bundled/repair/cli.py` | 创建 | agent 调用入口：`create-issue` 子命令 |
| `plugins/bundled/repair/plugin.py` | 创建 | RepairChannelPlugin：注册 GitLab webhook 路由骨架 + 自建 scheduler 轮询 |
| `plugins/bundled/linear/linear_client.py` | 修改 | 补 `create_issue` / `create_comment` / `get_workflow_states` |
| `plugins/bundled/linear/handler.py` | 修改 | 加 Issue 状态变更/分配事件分支 → 委派 RepairCoordinator |
| `plugins/bundled/linear/plugin.py` | 修改 | webhook 路由识别 `Issue` 事件类型并分发到 handler 新方法 |
| `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md` | 创建 | TDD 驱动修复 skill |
| `agent_cwd/.claude/skills/repair-report-analyzer/SKILL.md` | 创建 | 三类归因分析 skill |
| `agent_cwd/.claude/skills/issue-diagnosis/SKILL.md` | 修改 | 加 Step 6.5：判 bug → AskUserQuestion → 提单 |
| `agent_cwd/.claude/hooks/restrict-git-write.py` | 创建 | PreToolUse hook：git 写仅放行 `/tmp/repair/**` |
| `agent_cwd/.claude/settings.json` | 修改 | deny 移除 git 写硬封；注册 restrict-git-write hook |
| `plugins/config.json` | 修改 | enabled 加 `repair`；plugins 加 repair 配置块 |
| `.env.example` | 修改 | 加 repair 相关 env 文档 |

---

## Task 0: 准备测试环境

**Files:**
- Create: `pytest.ini`
- Modify: `requirements.txt`

- [ ] **Step 1: 确认/创建虚拟环境并安装依赖**

Run:
```bash
cd /Users/jinfan/code/git-agent/agent-harness
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio
```
Expected: 安装成功，`python -m pytest --version` 输出版本号。

- [ ] **Step 2: 把 pytest 依赖写进 requirements.txt**

在 `requirements.txt` 末尾追加（紧跟 `# CLI tool dependencies` 段或文件尾）：
```text

# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 3: 创建 pytest.ini**

Create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    unit: 单元测试
    integration: 集成测试
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 4: 验证 pytest 能跑现有测试目录（不真连外部）**

Run: `source .venv/bin/activate && python -m pytest tests/repair/ -v`
Expected: `no tests ran`（目录还不存在或为空），但 pytest 本身正常启动无报错。若报 `file or directory not found`，先 `mkdir -p tests/repair`。

- [ ] **Step 5: Commit**

```bash
git add pytest.ini requirements.txt
git commit -m "chore: add pytest config and test deps for repair pipeline"
```

---

## Task 1: SQLite 运行时表 store.py

**Files:**
- Create: `plugins/bundled/repair/__init__.py`
- Create: `plugins/bundled/repair/store.py`
- Create: `tests/repair/__init__.py`
- Test: `tests/repair/test_store.py`

- [ ] **Step 1: 创建包 __init__**

Create `plugins/bundled/repair/__init__.py`:
```python
"""自动化 Bug 修复流水线插件。"""
```

Create `tests/repair/__init__.py`:
```python
```

- [ ] **Step 2: 写失败测试**

Create `tests/repair/test_store.py`:
```python
"""repair_runs SQLite 表测试。

Run: python -m pytest tests/repair/test_store.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.store import RepairStore, RepairRun, Stage


@pytest.fixture
def store(tmp_path):
    return RepairStore(str(tmp_path / "repair_runs.db"))


@pytest.mark.unit
def test_create_and_get(store):
    # Arrange
    run = RepairRun(
        linear_issue_id="uuid-1",
        linear_identifier="ENG-1",
        workspace_id="ws-1",
        stage=Stage.PENDING_REVIEW,
        repo="ai-agent/foo",
        root_cause="空指针",
        repair_plan="加判空",
    )

    # Act
    store.upsert(run)
    fetched = store.get("uuid-1")

    # Assert
    assert fetched is not None
    assert fetched.linear_identifier == "ENG-1"
    assert fetched.stage == Stage.PENDING_REVIEW
    assert fetched.fix_retry_count == 0
    assert fetched.rediagnose_count == 0


@pytest.mark.unit
def test_get_missing_returns_none(store):
    assert store.get("nope") is None


@pytest.mark.unit
def test_upsert_is_idempotent(store):
    # Arrange
    run = RepairRun(linear_issue_id="uuid-1", workspace_id="ws-1", stage=Stage.PENDING_REVIEW)

    # Act: 重复 upsert 不应抛错且不产生第二行
    store.upsert(run)
    store.upsert(run)

    # Assert
    assert store.get("uuid-1") is not None
    assert len(store.list_by_stage(Stage.PENDING_REVIEW)) == 1


@pytest.mark.unit
def test_update_stage_and_counters(store):
    # Arrange
    store.upsert(RepairRun(linear_issue_id="uuid-1", workspace_id="ws-1", stage=Stage.DEVELOPING))

    # Act
    store.update("uuid-1", stage=Stage.BUILDING, branch="fix/eng-1", mr_url="http://mr/1")
    store.increment_fix_retry("uuid-1")

    # Assert
    fetched = store.get("uuid-1")
    assert fetched.stage == Stage.BUILDING
    assert fetched.branch == "fix/eng-1"
    assert fetched.mr_url == "http://mr/1"
    assert fetched.fix_retry_count == 1


@pytest.mark.unit
def test_list_by_stage(store):
    # Arrange
    store.upsert(RepairRun(linear_issue_id="a", workspace_id="w", stage=Stage.BUILDING))
    store.upsert(RepairRun(linear_issue_id="b", workspace_id="w", stage=Stage.BUILDING))
    store.upsert(RepairRun(linear_issue_id="c", workspace_id="w", stage=Stage.RESOLVED))

    # Act
    building = store.list_by_stage(Stage.BUILDING)

    # Assert
    assert {r.linear_issue_id for r in building} == {"a", "b"}
```

- [ ] **Step 3: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_store.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'plugins.bundled.repair.store'`

- [ ] **Step 4: 实现 store.py**

Create `plugins/bundled/repair/store.py`:
```python
"""repair_runs SQLite 运行时表（WAL 模式，跨进程并发安全）。

存 Linear 表达不了的运行时细节。stage 为内部真相游标，
Linear 状态为用户可见真相，coordinator 每次推进同步两者。
"""

import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_BUSY_RETRY = 5
_BUSY_SLEEP = 0.2


class Stage:
    """内部阶段游标（非 Linear 状态）。"""

    PENDING_REVIEW = "pending_review"
    DEVELOPING = "developing"
    BUILDING = "building"
    ANALYZING = "analyzing"
    RESOLVED = "resolved"
    REJECTED = "rejected"  # 产研退回转人工


@dataclass
class RepairRun:
    """一条修复流水线运行记录。"""

    linear_issue_id: str
    workspace_id: str
    stage: str
    linear_identifier: str = ""
    repo: str = ""
    branch: str = ""
    mr_url: str = ""
    jenkins_build_id: str = ""
    develop_session_id: str = ""
    fix_retry_count: int = 0
    rediagnose_count: int = 0
    root_cause: str = ""
    repair_plan: str = ""
    last_report: str = ""
    created_at: int = 0
    updated_at: int = 0


_COLUMNS = [f.name for f in fields(RepairRun)]


class RepairStore:
    """repair_runs 表的 CRUD，WAL + 短事务 + locked 重试。写频极低。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repair_runs (
                    linear_issue_id   TEXT PRIMARY KEY,
                    workspace_id      TEXT NOT NULL,
                    stage             TEXT NOT NULL,
                    linear_identifier TEXT DEFAULT '',
                    repo              TEXT DEFAULT '',
                    branch            TEXT DEFAULT '',
                    mr_url            TEXT DEFAULT '',
                    jenkins_build_id  TEXT DEFAULT '',
                    develop_session_id TEXT DEFAULT '',
                    fix_retry_count   INTEGER DEFAULT 0,
                    rediagnose_count  INTEGER DEFAULT 0,
                    root_cause        TEXT DEFAULT '',
                    repair_plan       TEXT DEFAULT '',
                    last_report       TEXT DEFAULT '',
                    created_at        INTEGER NOT NULL,
                    updated_at        INTEGER NOT NULL
                )
                """
            )

    def upsert(self, run: RepairRun) -> None:
        """插入或更新整行（按 linear_issue_id 主键），幂等。"""
        now = int(time.time())
        if not run.created_at:
            run.created_at = now
        run.updated_at = now
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        updates = ", ".join(
            f"{c}=excluded.{c}" for c in _COLUMNS if c != "linear_issue_id"
        )
        values = [getattr(run, c) for c in _COLUMNS]
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO repair_runs ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT(linear_issue_id) DO UPDATE SET {updates}",
                values,
            )

    def get(self, linear_issue_id: str) -> Optional[RepairRun]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM repair_runs WHERE linear_issue_id = ?",
                (linear_issue_id,),
            ).fetchone()
        return self._row_to_run(row) if row else None

    def list_by_stage(self, stage: str) -> List[RepairRun]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM repair_runs WHERE stage = ?", (stage,)
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def update(self, linear_issue_id: str, **kwargs) -> None:
        """部分更新指定字段，自动刷新 updated_at。"""
        if not kwargs:
            return
        allowed = {k: v for k, v in kwargs.items() if k in _COLUMNS}
        allowed["updated_at"] = int(time.time())
        set_clause = ", ".join(f"{k} = ?" for k in allowed)
        values = list(allowed.values()) + [linear_issue_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE repair_runs SET {set_clause} WHERE linear_issue_id = ?",
                values,
            )

    def increment_fix_retry(self, linear_issue_id: str) -> int:
        """fix_retry_count +1，返回新值。"""
        return self._increment(linear_issue_id, "fix_retry_count")

    def increment_rediagnose(self, linear_issue_id: str) -> int:
        """rediagnose_count +1，返回新值。"""
        return self._increment(linear_issue_id, "rediagnose_count")

    def _increment(self, linear_issue_id: str, column: str) -> int:
        with self._conn() as conn:
            conn.execute(
                f"UPDATE repair_runs SET {column} = {column} + 1, updated_at = ? "
                f"WHERE linear_issue_id = ?",
                (int(time.time()), linear_issue_id),
            )
            row = conn.execute(
                f"SELECT {column} FROM repair_runs WHERE linear_issue_id = ?",
                (linear_issue_id,),
            ).fetchone()
        return row[column] if row else 0

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RepairRun:
        return RepairRun(**{c: row[c] for c in _COLUMNS})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_store.py -v`
Expected: PASS（5 passed）

- [ ] **Step 6: Commit**

```bash
git add plugins/bundled/repair/__init__.py plugins/bundled/repair/store.py tests/repair/__init__.py tests/repair/test_store.py
git commit -m "feat(repair): add repair_runs SQLite store with WAL"
```

---

## Task 2: prompts.py — 状态映射 + prompt 模板 + 解析

**Files:**
- Create: `plugins/bundled/repair/prompts.py`
- Test: `tests/repair/test_prompts.py`

`prompts.py` 集中三件事：① Linear 状态名→语义阶段的可配置映射；② 给 developer / analyzer skill 拼 prompt 的模板函数；③ 解析 developer 输出（分支+MR URL）和 analyzer 输出（四选一判定）的纯函数。

- [ ] **Step 1: 写失败测试**

Create `tests/repair/test_prompts.py`:
```python
"""prompts.py 状态映射与解析函数测试。

Run: python -m pytest tests/repair/test_prompts.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair import prompts


@pytest.mark.unit
def test_classify_state_review_to_developing():
    # "开发中"/"In Progress" 类状态视为审核通过
    assert prompts.is_approval_state("In Progress") is True
    assert prompts.is_approval_state("开发中") is True
    assert prompts.is_approval_state("Backlog") is False
    assert prompts.is_approval_state("Triage") is False


@pytest.mark.unit
def test_parse_developer_output_extracts_branch_and_mr():
    text = """
    一些自审说明...
    【分支】fix/ENG-123
    【MR链接】http://gitlab/ai-agent/foo/-/merge_requests/7
    【复现测试】src/test/FooTest.java
    """
    parsed = prompts.parse_developer_output(text)
    assert parsed["branch"] == "fix/ENG-123"
    assert parsed["mr_url"] == "http://gitlab/ai-agent/foo/-/merge_requests/7"
    assert parsed["test_path"] == "src/test/FooTest.java"


@pytest.mark.unit
def test_parse_developer_output_missing_fields():
    parsed = prompts.parse_developer_output("没有结构化字段")
    assert parsed["branch"] == ""
    assert parsed["mr_url"] == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("【判定】已解决", "resolved"),
        ("【判定】代码错", "code_error"),
        ("【判定】根因错", "root_cause_error"),
        ("【判定】漏依赖", "missing_dependency"),
    ],
)
def test_parse_analyzer_verdict(verdict, expected):
    text = f"{verdict}\n【依据】xxx\n【后续动作】yyy"
    parsed = prompts.parse_analyzer_output(text)
    assert parsed["verdict"] == expected


@pytest.mark.unit
def test_parse_analyzer_unknown_verdict_defaults_code_error():
    # 解析不出明确判定时，保守归为 code_error（走同分支重修，不误判已解决）
    parsed = prompts.parse_analyzer_output("乱七八糟没有判定")
    assert parsed["verdict"] == "code_error"


@pytest.mark.unit
def test_build_developer_prompt_contains_inputs():
    p = prompts.build_developer_prompt(
        identifier="ENG-123",
        root_cause="空指针",
        evidence="日志 X",
        repair_plan="加判空",
        repo="ai-agent/foo",
        branch="fix/ENG-123",
        is_retry=False,
        last_report="",
    )
    assert "ENG-123" in p
    assert "空指针" in p
    assert "加判空" in p
    assert "fix/ENG-123" in p
    assert "bug-fix-developer" in p


@pytest.mark.unit
def test_build_developer_prompt_retry_includes_report():
    p = prompts.build_developer_prompt(
        identifier="ENG-123",
        root_cause="空指针",
        evidence="日志 X",
        repair_plan="加判空",
        repo="ai-agent/foo",
        branch="fix/ENG-123",
        is_retry=True,
        last_report="测试仍失败：NPE at line 5",
    )
    assert "重修" in p
    assert "NPE at line 5" in p


@pytest.mark.unit
def test_build_analyzer_prompt_contains_report():
    p = prompts.build_analyzer_prompt(
        identifier="ENG-123",
        root_cause="空指针",
        repair_plan="加判空",
        report="3 passed, 0 failed",
    )
    assert "repair-report-analyzer" in p
    assert "3 passed" in p
    assert "ENG-123" in p
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_prompts.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'plugins.bundled.repair.prompts'`

- [ ] **Step 3: 实现 prompts.py**

Create `plugins/bundled/repair/prompts.py`:
```python
"""状态映射 + 各阶段 prompt 模板 + 输出解析（纯函数，易测）。"""

import os
import re
from typing import Dict


# ── Linear 状态名 → 是否「审核通过（进入开发）」────────────────────────────
# 用户在 Linear 把单子拖到「开发中」类状态即视为审核通过。
# 可通过 env REPAIR_APPROVAL_STATES 覆盖（逗号分隔，小写匹配）。
_DEFAULT_APPROVAL_STATES = ["in progress", "开发中", "in development", "开发"]


def _approval_states() -> list:
    raw = os.getenv("REPAIR_APPROVAL_STATES", "")
    if raw.strip():
        return [s.strip().lower() for s in raw.split(",") if s.strip()]
    return _DEFAULT_APPROVAL_STATES


def is_approval_state(state_name: str) -> bool:
    """判断某 Linear 状态名是否表示「用户已审核通过，可进入开发」。"""
    if not state_name:
        return False
    return state_name.strip().lower() in _approval_states()


# ── developer / analyzer prompt 模板 ───────────────────────────────────────

def build_developer_prompt(
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
    parts = [
        f"严格按 skill: bug-fix-developer 执行 TDD 修复任务。",
        f"\n# 修复任务 {identifier}",
        f"目标仓库: {repo}",
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


def build_analyzer_prompt(
    identifier: str,
    root_cause: str,
    repair_plan: str,
    report: str,
) -> str:
    """拼出调用 repair-report-analyzer skill 的 prompt。"""
    return "\n".join(
        [
            "严格按 skill: repair-report-analyzer 执行三类归因分析。",
            f"\n# 待分析的修复 {identifier}",
            f"\n## 原根因\n{root_cause}",
            f"\n## 修复计划\n{repair_plan}",
            f"\n## 测试报告\n{report}",
            "\n请按 skill 要求输出【判定】【依据】【后续动作】结构化结果。",
        ]
    )


# ── 输出解析（纯函数）──────────────────────────────────────────────────────

def _extract(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def parse_developer_output(text: str) -> Dict[str, str]:
    """从 developer skill 输出解析分支、MR URL、测试路径。

    缺失字段返回空串。
    """
    return {
        "branch": _extract(r"【分支】\s*(\S+)", text),
        "mr_url": _extract(r"【MR链接】\s*(\S+)", text),
        "test_path": _extract(r"【复现测试】\s*(\S+)", text),
    }


_VERDICT_MAP = [
    ("已解决", "resolved"),
    ("代码错", "code_error"),
    ("根因错", "root_cause_error"),
    ("漏依赖", "missing_dependency"),
]


def parse_analyzer_output(text: str) -> Dict[str, str]:
    """从 analyzer skill 输出解析【判定】。

    解析不出明确判定时，保守归为 code_error（走同分支重修，
    绝不误判为已解决而关单）。
    """
    verdict_line = _extract(r"【判定】\s*([^\n]+)", text)
    verdict = "code_error"
    for zh, key in _VERDICT_MAP:
        if zh in verdict_line:
            verdict = key
            break
    return {
        "verdict": verdict,
        "raw": text,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_prompts.py -v`
Expected: PASS（约 11 passed）

- [ ] **Step 5: Commit**

```bash
git add plugins/bundled/repair/prompts.py tests/repair/test_prompts.py
git commit -m "feat(repair): add prompts, state mapping, output parsers"
```

---

## Task 3: LinearClient 补写方法

**Files:**
- Modify: `plugins/bundled/linear/linear_client.py`
- Test: `tests/repair/test_linear_client.py`

补 `create_issue`（提单）、`create_comment`（回写评论）、`get_workflow_states`（取团队状态列表，供 coordinator 名→stateId 映射）。

- [ ] **Step 1: 写失败测试（mock httpx）**

Create `tests/repair/test_linear_client.py`:
```python
"""LinearClient 写方法测试（mock GraphQL）。

Run: python -m pytest tests/repair/test_linear_client.py -v
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.linear.linear_client import LinearClient


@pytest.mark.unit
async def test_create_issue_builds_mutation():
    client = LinearClient("token-x")
    fake_data = {
        "issueCreate": {
            "success": True,
            "issue": {"id": "uuid-9", "identifier": "ENG-9"},
        }
    }
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)) as q:
        result = await client.create_issue(
            team_id="team-1",
            title="bug: NPE",
            description="根因...",
        )

    assert result["id"] == "uuid-9"
    assert result["identifier"] == "ENG-9"
    # 校验调用了 mutation 且带 input
    args, kwargs = q.call_args
    assert "issueCreate" in args[0]
    assert args[1]["input"]["teamId"] == "team-1"
    assert args[1]["input"]["title"] == "bug: NPE"


@pytest.mark.unit
async def test_create_comment_builds_mutation():
    client = LinearClient("token-x")
    fake_data = {"commentCreate": {"success": True, "comment": {"id": "c-1"}}}
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)) as q:
        cid = await client.create_comment("issue-1", "分析结果...")

    assert cid == "c-1"
    args, _ = q.call_args
    assert "commentCreate" in args[0]
    assert args[1]["input"]["issueId"] == "issue-1"
    assert args[1]["input"]["body"] == "分析结果..."


@pytest.mark.unit
async def test_get_workflow_states_returns_list():
    client = LinearClient("token-x")
    fake_data = {
        "team": {
            "states": {
                "nodes": [
                    {"id": "s1", "name": "Backlog", "type": "backlog", "position": 0},
                    {"id": "s2", "name": "In Progress", "type": "started", "position": 1},
                ]
            }
        }
    }
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)):
        states = await client.get_workflow_states("team-1")

    assert len(states) == 2
    assert states[1]["name"] == "In Progress"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_linear_client.py -v`
Expected: FAIL，`AttributeError: 'LinearClient' object has no attribute 'create_issue'`

- [ ] **Step 3: 实现写方法**

在 `plugins/bundled/linear/linear_client.py` 的 `# ── Team ──` 段之前（即 `get_team_first_started_state_id` 上方、`update_issue` 之后）插入以下方法：

```python
    async def create_issue(
        self,
        team_id: str,
        title: str,
        description: str = "",
        state_id: Optional[str] = None,
        delegate_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建 Issue（用于自动提 bug 单）。

        Args:
            team_id: 目标团队 ID
            title: Issue 标题
            description: Markdown 描述（根因+证据+修复计划）
            state_id: 初始状态 ID（可选，默认团队默认状态）
            delegate_id: 委派的 bot 用户 ID（可选）

        Returns:
            含 id/identifier/url 的字典
        """
        input_data: Dict[str, Any] = {
            "teamId": team_id,
            "title": title,
            "description": description,
        }
        if state_id:
            input_data["stateId"] = state_id
        if delegate_id:
            input_data["delegateId"] = delegate_id
        data = await self._query(
            """
            mutation IssueCreate($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                    success
                    issue { id identifier url }
                }
            }
            """,
            {"input": input_data},
        )
        return data["issueCreate"]["issue"]

    async def create_comment(self, issue_id: str, body: str) -> str:
        """在 Issue 上创建评论（用于回写分析结果/进度）。

        Args:
            issue_id: Linear Issue UUID
            body: Markdown 评论内容

        Returns:
            新建 comment 的 ID
        """
        data = await self._query(
            """
            mutation CommentCreate($input: CommentCreateInput!) {
                commentCreate(input: $input) {
                    success
                    comment { id }
                }
            }
            """,
            {"input": {"issueId": issue_id, "body": body}},
        )
        return data["commentCreate"]["comment"]["id"]

    async def get_workflow_states(self, team_id: str) -> List[Dict[str, Any]]:
        """获取团队全部 workflow 状态（id/name/type/position）。

        供 coordinator 做「状态名 → stateId」映射。

        Args:
            team_id: Linear team ID

        Returns:
            状态字典列表
        """
        data = await self._query(
            """
            query TeamStates($teamId: String!) {
                team(id: $teamId) {
                    states { nodes { id name type position } }
                }
            }
            """,
            {"teamId": team_id},
        )
        return data["team"]["states"]["nodes"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_linear_client.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add plugins/bundled/linear/linear_client.py tests/repair/test_linear_client.py
git commit -m "feat(linear): add create_issue/create_comment/get_workflow_states"
```

---

## Task 4: jenkins_client.py 占位

**Files:**
- Create: `plugins/bundled/repair/jenkins_client.py`
- Test: `tests/repair/test_jenkins_client.py`

本期全 mock。签名按真实 Jenkins build API 设计，body 留 TODO 标明待联调字段（job 名/凭证/分支参数/报告格式）。联调时只改本文件实现，不动编排。

- [ ] **Step 1: 写失败测试**

Create `tests/repair/test_jenkins_client.py`:
```python
"""JenkinsClient 占位契约测试。

Run: python -m pytest tests/repair/test_jenkins_client.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.jenkins_client import JenkinsClient


@pytest.mark.unit
def test_trigger_build_returns_id():
    client = JenkinsClient()
    build_id = client.trigger_build(repo="ai-agent/foo", branch="fix/ENG-1")
    assert isinstance(build_id, str)
    assert build_id  # 非空


@pytest.mark.unit
def test_get_report_not_ready_returns_none():
    # 本期 mock：默认未就绪返回 None（可由 ready_after 控制）
    client = JenkinsClient(mock_ready=False)
    assert client.get_report("build-1") is None


@pytest.mark.unit
def test_get_report_ready_returns_dict():
    client = JenkinsClient(mock_ready=True)
    report = client.get_report("build-1")
    assert report is not None
    assert "status" in report
    assert "summary" in report
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_jenkins_client.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'plugins.bundled.repair.jenkins_client'`

- [ ] **Step 3: 实现 jenkins_client.py**

Create `plugins/bundled/repair/jenkins_client.py`:
```python
"""Jenkins 客户端 —— 本期占位 mock。

签名按真实 Jenkins build API 设计：
  POST {JENKINS_URL}/job/{job}/buildWithParameters?BRANCH=...
  GET  {JENKINS_URL}/job/{job}/{build_no}/api/json  + testReport
联调时只改这里的实现，coordinator 不动。
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


class JenkinsClient:
    """触发构建 + 拉取测试报告。本期 mock，真实实现见各方法 TODO。"""

    def __init__(self, mock_ready: bool = True):
        """
        Args:
            mock_ready: 占位用——get_report 是否立即返回就绪报告。
                        真实实现会忽略此参数，按 Jenkins 实际状态返回。
        """
        self._mock_ready = mock_ready

    def trigger_build(self, repo: str, branch: str) -> str:
        """触发一次构建，返回 build_id。

        TODO(联调): 真实实现
          POST {JENKINS_URL}/job/{job_name}/buildWithParameters
            params: BRANCH={branch}, REPO={repo}
            auth: (JENKINS_USER, JENKINS_API_TOKEN)
          从 Location header 的 queue item 轮询拿到 build number 作为 build_id。

        Args:
            repo: 目标仓库（如 ai-agent/foo）
            branch: 修复分支名

        Returns:
            build_id（本期 mock 为随机 id）
        """
        build_id = f"mock-build-{uuid.uuid4().hex[:8]}"
        logger.info(
            "[Jenkins][MOCK] trigger_build repo=%s branch=%s -> %s",
            repo,
            branch,
            build_id,
        )
        return build_id

    def get_report(self, build_id: str) -> Optional[dict]:
        """拉取构建的测试报告；未就绪返回 None。

        TODO(联调): 真实实现
          GET {JENKINS_URL}/job/{job}/{build_no}/api/json -> 看 building/result
          building=true -> return None
          完成 -> GET .../testReport/api/json 解析 pass/fail，
                 组装 {"status": "...", "summary": "...", "failures": [...]}

        Args:
            build_id: trigger_build 返回的 id

        Returns:
            报告字典或 None（未就绪）
        """
        if not self._mock_ready:
            logger.info("[Jenkins][MOCK] get_report %s -> not ready", build_id)
            return None
        logger.info("[Jenkins][MOCK] get_report %s -> ready (mock pass)", build_id)
        return {
            "status": "success",
            "summary": "[MOCK] 3 passed, 0 failed",
            "failures": [],
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_jenkins_client.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add plugins/bundled/repair/jenkins_client.py tests/repair/test_jenkins_client.py
git commit -m "feat(repair): add Jenkins client placeholder (mock)"
```

---

## Task 5: RepairCoordinator 编排 + singleton

**Files:**
- Create: `plugins/bundled/repair/coordinator.py`
- Create: `tests/repair/conftest.py`
- Test: `tests/repair/test_coordinator.py`

这是流水线的核心。RepairCoordinator 是**纯编排**：每方法 = 读 store → 调 agent 或 Linear → 写新状态。N/M 重试由代码硬兜底（不靠 agent 自觉）。通过 module-level `get_coordinator()` / `set_coordinator()` 暴露 singleton，供 linear handler 软依赖委派。

关键转移（对应设计 §13 状态机）：
- `start_development()`：pending_review + 审核通过 → developing，调 developer skill → 解析分支/MR → building → 触发 Jenkins
- `analyze_report()`：building + 报告就绪 → analyzing，调 analyzer skill → 解析判定 → 回转
  - resolved → 回写 Linear + 评论 + stage=resolved（终态）
  - code_error → fix_retry_count+1，<N 则 resume develop_session 重修；≥N → rejected（产研退回）
  - root_cause_error → rediagnose_count+1，<M 则回 issue-diagnosis 重诊断；≥M → rejected
  - missing_dependency → 建子单 + 父单 blockedBy（本期记录到评论，stage 保持，标注待人工）

依赖注入：coordinator 构造接收 `agent_service`、`store`、`jenkins`、`linear_client_factory`（`workspace_id -> LinearClient`），便于测试注入 fake。

- [ ] **Step 1: 写共享 fixture conftest.py**

Create `tests/repair/conftest.py`:
```python
"""repair 测试共享 fixture：临时 store、fake LinearClient、fake JenkinsClient、
fake AgentService。"""

import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.store import RepairStore


@pytest.fixture
def store(tmp_path):
    return RepairStore(str(tmp_path / "repair_runs.db"))


class FakeLinearClient:
    """记录所有写操作，便于断言。"""

    def __init__(self):
        self.updated = []  # (issue_id, kwargs)
        self.comments = []  # (issue_id, body)
        self.created_issues = []  # input dicts
        self._next_issue = {"id": "child-uuid", "identifier": "ENG-CHILD", "url": "http://x"}
        self._states = [
            {"id": "s-backlog", "name": "Backlog", "type": "backlog", "position": 0},
            {"id": "s-prog", "name": "In Progress", "type": "started", "position": 1},
            {"id": "s-done", "name": "Done", "type": "completed", "position": 2},
            {"id": "s-cancel", "name": "Canceled", "type": "canceled", "position": 3},
        ]

    async def update_issue(self, issue_id, state_id=None, delegate_id=None, description=None):
        self.updated.append((issue_id, {"state_id": state_id, "description": description}))

    async def create_comment(self, issue_id, body):
        self.comments.append((issue_id, body))
        return "comment-id"

    async def create_issue(self, team_id, title, description="", state_id=None, delegate_id=None):
        self.created_issues.append(
            {"team_id": team_id, "title": title, "description": description}
        )
        return dict(self._next_issue)

    async def get_workflow_states(self, team_id):
        return list(self._states)

    async def get_issue(self, issue_id):
        return {"id": issue_id, "identifier": "ENG-1", "team": {"id": "team-1"}}


class FakeJenkins:
    def __init__(self, ready=True):
        self.ready = ready
        self.triggered = []

    def trigger_build(self, repo, branch):
        self.triggered.append((repo, branch))
        return "build-xyz"

    def get_report(self, build_id):
        if not self.ready:
            return None
        return {"status": "success", "summary": "3 passed", "failures": []}


class FakeAgentService:
    """按预设脚本逐次返回 result 文本。process_query 是 async generator。"""

    def __init__(self, scripted_results):
        # scripted_results: list[str]，每次 process_query 弹一个
        self._results = list(scripted_results)
        self.calls = []  # 记录每次 QueryRequest

    async def process_query(self, request, context_file_path=None):
        self.calls.append(request)
        text = self._results.pop(0) if self._results else ""
        yield {"type": "session_created", "data": {"session_id": "claude-sess-1"}}
        yield {"type": "result", "data": {"result": text}}


@pytest.fixture
def fake_linear():
    return FakeLinearClient()


@pytest.fixture
def fake_jenkins():
    return FakeJenkins(ready=True)
```

- [ ] **Step 2: 写 coordinator 失败测试**

Create `tests/repair/test_coordinator.py`:
```python
"""RepairCoordinator 状态机 + 三类归因回转 + N/M 兜底测试。

Run: python -m pytest tests/repair/test_coordinator.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.coordinator import RepairCoordinator
from plugins.bundled.repair.store import RepairRun, Stage
from tests.repair.conftest import FakeAgentService, FakeJenkins


def _make_coordinator(store, fake_linear, agent_results, jenkins_ready=True):
    jenkins = FakeJenkins(ready=jenkins_ready)
    agent = FakeAgentService(agent_results)
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=jenkins,
        linear_client_factory=lambda ws: fake_linear,
        fix_retry_limit=3,
        rediagnose_limit=2,
    )
    return coord, agent, jenkins


def _seed_pending(store, stage=Stage.PENDING_REVIEW):
    store.upsert(
        RepairRun(
            linear_issue_id="issue-1",
            linear_identifier="ENG-1",
            workspace_id="ws-1",
            stage=stage,
            repo="ai-agent/foo",
            root_cause="空指针",
            repair_plan="加判空",
        )
    )


@pytest.mark.unit
async def test_start_development_happy_path(store, fake_linear):
    # Arrange
    _seed_pending(store)
    dev_output = "【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java"
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output])

    # Act
    await coord.start_development("issue-1")

    # Assert
    run = store.get("issue-1")
    assert run.stage == Stage.BUILDING
    assert run.branch == "fix/ENG-1"
    assert run.mr_url == "http://mr/1"
    assert run.develop_session_id == "claude-sess-1"
    assert jenkins.triggered == [("ai-agent/foo", "fix/ENG-1")]
    assert run.jenkins_build_id == "build-xyz"


@pytest.mark.unit
async def test_start_development_idempotent_when_not_pending(store, fake_linear):
    # 已经 building 的单子再次触发 start 不应重复开发
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(store, fake_linear, ["should not be used"])

    await coord.start_development("issue-1")

    assert len(agent.calls) == 0  # 未调用 developer


@pytest.mark.unit
async def test_analyze_resolved_writes_done_and_comment(store, fake_linear):
    # Arrange: 处于 building，jenkins 就绪
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", jenkins_build_id="build-xyz", branch="fix/ENG-1")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】已解决\n【依据】全绿\n【后续动作】无"]
    )

    # Act
    await coord.analyze_report("issue-1")

    # Assert
    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    # 回写了 Done 状态 + 评论
    assert any(kw["state_id"] == "s-done" for _, kw in fake_linear.updated)
    assert len(fake_linear.comments) >= 1


@pytest.mark.unit
async def test_analyze_code_error_resumes_and_increments(store, fake_linear):
    # Arrange
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", develop_session_id="claude-sess-1", branch="fix/ENG-1")
    # 第一次 analyzer 返回代码错；随后 developer 重修返回新 MR
    coord, agent, jenkins = _make_coordinator(
        store,
        fake_linear,
        [
            "【判定】代码错\n【依据】NPE 仍在\n【后续动作】补判空",
            "【分支】fix/ENG-1\n【MR链接】http://mr/2",
        ],
    )

    # Act
    await coord.analyze_report("issue-1")

    # Assert
    run = store.get("issue-1")
    assert run.fix_retry_count == 1
    assert run.stage == Stage.BUILDING  # 重修后再次进 building
    # developer 重修时 resume 了同一 session
    dev_call = agent.calls[-1]
    assert dev_call.session_id == "claude-sess-1"


@pytest.mark.unit
async def test_code_error_exceeds_limit_goes_rejected(store, fake_linear):
    # Arrange: fix_retry_count 已达上限-1，再错一次即超限
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", fix_retry_count=2, branch="fix/ENG-1", develop_session_id="s1")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】代码错\n【依据】还是错\n【后续动作】x"]
    )

    # Act
    await coord.analyze_report("issue-1")

    # Assert: 第 3 次失败 → 超限 → rejected，不再 resume developer
    run = store.get("issue-1")
    assert run.fix_retry_count == 3
    assert run.stage == Stage.REJECTED
    assert any(kw["state_id"] == "s-cancel" for _, kw in fake_linear.updated)
    # 只调了 analyzer，没有再调 developer
    assert len(agent.calls) == 1


@pytest.mark.unit
async def test_root_cause_error_rediagnoses_then_limit(store, fake_linear):
    # Arrange: 根因错，重诊断计数未超限
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】根因错\n【依据】根因站不住\n【后续动作】回诊断"]
    )

    # Act
    await coord.analyze_report("issue-1")

    # Assert
    run = store.get("issue-1")
    assert run.rediagnose_count == 1
    # 未超限 M=2：标注回诊断（本期记录到评论，stage 回 pending_review 或标注）
    assert len(fake_linear.comments) >= 1


@pytest.mark.unit
async def test_root_cause_error_exceeds_limit_rejected(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", rediagnose_count=1)  # M=2，再错一次超限
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】根因错\n【依据】x\n【后续动作】y"]
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.rediagnose_count == 2
    assert run.stage == Stage.REJECTED


@pytest.mark.unit
async def test_missing_dependency_creates_child_issue(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(
        store,
        fake_linear,
        ["【判定】漏依赖\n【依据】需改上游服务\n【后续动作】建子单：修上游 X"],
    )

    await coord.analyze_report("issue-1")

    # 建了子单 + 评论说明
    assert len(fake_linear.created_issues) >= 1
    assert len(fake_linear.comments) >= 1


@pytest.mark.unit
async def test_analyze_skips_when_jenkins_not_ready(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", jenkins_build_id="build-xyz")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["should not run"], jenkins_ready=False
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.BUILDING  # 报告未就绪，保持
    assert len(agent.calls) == 0  # analyzer 未被调用
```

- [ ] **Step 3: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'plugins.bundled.repair.coordinator'`

- [ ] **Step 4: 实现 coordinator.py**

Create `plugins/bundled/repair/coordinator.py`:
```python
"""RepairCoordinator —— 纯编排状态机。

每方法 = 读 store → 调 agent 或 Linear → 写新状态。
N/M 重试由代码硬兜底。通过 module-level singleton 供 linear handler 委派。
"""

import logging
import os
from typing import Callable, Optional

from plugins.bundled.repair import prompts
from plugins.bundled.repair.jenkins_client import JenkinsClient
from plugins.bundled.repair.store import RepairRun, RepairStore, Stage

logger = logging.getLogger(__name__)


async def _run_agent(agent_service, prompt: str, skill: str, session_id: Optional[str]) -> tuple:
    """调 AgentService.process_query，返回 (result_text, claude_session_id)。

    新会话靠 DEFAULT_SKILLS 加载 skill；resume 时传 session_id。
    """
    from api.models.requests import QueryRequest

    request = QueryRequest(
        prompt=prompt,
        language="中文",
        skill=skill if not session_id else None,
        session_id=session_id,
    )
    result_text = ""
    new_session_id = session_id
    async for event in agent_service.process_query(request):
        etype = event.get("type") or event.get("event", "")
        data = event.get("data", {})
        if isinstance(data, str):
            import json

            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if etype == "session_created":
            new_session_id = data.get("session_id", new_session_id)
        elif etype == "result":
            result_text = data.get("result", "") or data.get("content", "")
    return result_text, new_session_id


class RepairCoordinator:
    """状态机编排。依赖全部注入，便于测试。"""

    def __init__(
        self,
        agent_service,
        store: RepairStore,
        jenkins: JenkinsClient,
        linear_client_factory: Callable,
        fix_retry_limit: int = 3,
        rediagnose_limit: int = 2,
    ):
        """
        Args:
            agent_service: AgentService 实例（有 process_query）
            store: RepairStore
            jenkins: JenkinsClient
            linear_client_factory: workspace_id -> LinearClient
            fix_retry_limit: N，代码错同分支重修上限
            rediagnose_limit: M，根因错重诊断上限
        """
        self.agent_service = agent_service
        self.store = store
        self.jenkins = jenkins
        self._linear_factory = linear_client_factory
        self.N = fix_retry_limit
        self.M = rediagnose_limit

    def _linear(self, workspace_id: str):
        return self._linear_factory(workspace_id)

    async def _state_id_by_type(self, client, team_id: str, type_name: str) -> Optional[str]:
        """按 workflow state type（started/completed/canceled）取第一个 stateId。"""
        states = await client.get_workflow_states(team_id)
        matched = [s for s in states if s["type"] == type_name]
        if not matched:
            return None
        return min(matched, key=lambda s: s["position"])["id"]

    # ── 阶段 1：开始开发 ─────────────────────────────────────────────────
    async def start_development(self, linear_issue_id: str) -> None:
        """pending_review + 审核通过 → developing → 调 developer → building → 触发 Jenkins。"""
        run = self.store.get(linear_issue_id)
        if not run:
            logger.warning("[Repair] start_development: run not found %s", linear_issue_id)
            return
        if run.stage != Stage.PENDING_REVIEW:
            logger.info(
                "[Repair] start_development skip: %s stage=%s (not pending_review)",
                linear_issue_id,
                run.stage,
            )
            return

        self.store.update(linear_issue_id, stage=Stage.DEVELOPING)
        branch = run.branch or f"fix/{run.linear_identifier}"

        prompt = prompts.build_developer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence=run.last_report or "（见 Linear 单描述）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=branch,
            is_retry=False,
            last_report="",
        )
        result_text, session_id = await _run_agent(
            self.agent_service, prompt, skill="bug-fix-developer", session_id=None
        )

        parsed = prompts.parse_developer_output(result_text)
        new_branch = parsed["branch"] or branch
        mr_url = parsed["mr_url"]

        build_id = self.jenkins.trigger_build(repo=run.repo, branch=new_branch)

        self.store.update(
            linear_issue_id,
            stage=Stage.BUILDING,
            branch=new_branch,
            mr_url=mr_url,
            develop_session_id=session_id or "",
            jenkins_build_id=build_id,
        )

        client = self._linear(run.workspace_id)
        try:
            await client.create_comment(
                linear_issue_id,
                f"已自动开发并建 MR：{mr_url or '(未解析到 MR 链接)'}\n"
                f"分支：{new_branch}\n构建已触发，等待测试报告。",
            )
        except Exception:
            logger.warning("[Repair] failed to comment after development", exc_info=True)

    # ── 阶段 2：分析报告 + 三类归因 ──────────────────────────────────────
    async def analyze_report(self, linear_issue_id: str) -> None:
        """building + 报告就绪 → analyzer → 解析判定 → 回转。"""
        run = self.store.get(linear_issue_id)
        if not run or run.stage != Stage.BUILDING:
            return

        report = self.jenkins.get_report(run.jenkins_build_id)
        if report is None:
            logger.info("[Repair] report not ready: %s", linear_issue_id)
            return

        self.store.update(linear_issue_id, stage=Stage.ANALYZING)
        report_summary = report.get("summary", "") + "\n" + str(report.get("failures", ""))
        self.store.update(linear_issue_id, last_report=report_summary)

        prompt = prompts.build_analyzer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            repair_plan=run.repair_plan,
            report=report_summary,
        )
        result_text, _ = await _run_agent(
            self.agent_service, prompt, skill="repair-report-analyzer", session_id=None
        )
        parsed = prompts.parse_analyzer_output(result_text)
        verdict = parsed["verdict"]
        run = self.store.get(linear_issue_id)  # 重新读最新

        if verdict == "resolved":
            await self._handle_resolved(run, parsed["raw"])
        elif verdict == "code_error":
            await self._handle_code_error(run, parsed["raw"])
        elif verdict == "root_cause_error":
            await self._handle_root_cause_error(run, parsed["raw"])
        elif verdict == "missing_dependency":
            await self._handle_missing_dependency(run, parsed["raw"])

    async def _handle_resolved(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        done_id = await self._state_id_by_type(client, team_id, "completed") if team_id else None
        if done_id:
            await client.update_issue(run.linear_issue_id, state_id=done_id)
        await client.create_comment(
            run.linear_issue_id,
            f"✅ Bug 已修复并通过测试。\n分支：{run.branch}\nMR：{run.mr_url}\n\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.RESOLVED)

    async def _handle_code_error(self, run: RepairRun, raw: str) -> None:
        count = self.store.increment_fix_retry(run.linear_issue_id)
        if count >= self.N:
            await self._reject(run, f"代码错重修达上限 N={self.N}，转人工。\n{raw}")
            return
        # 同分支 resume 重修
        prompt = prompts.build_developer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence="（见上一轮失败报告）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=run.branch,
            is_retry=True,
            last_report=run.last_report,
        )
        result_text, session_id = await _run_agent(
            self.agent_service,
            prompt,
            skill="bug-fix-developer",
            session_id=run.develop_session_id or None,
        )
        parsed = prompts.parse_developer_output(result_text)
        mr_url = parsed["mr_url"] or run.mr_url
        build_id = self.jenkins.trigger_build(repo=run.repo, branch=run.branch)
        self.store.update(
            run.linear_issue_id,
            stage=Stage.BUILDING,
            mr_url=mr_url,
            develop_session_id=session_id or run.develop_session_id,
            jenkins_build_id=build_id,
        )

    async def _handle_root_cause_error(self, run: RepairRun, raw: str) -> None:
        count = self.store.increment_rediagnose(run.linear_issue_id)
        client = self._linear(run.workspace_id)
        if count >= self.M:
            await self._reject(run, f"根因错重诊断达上限 M={self.M}，转人工。\n{raw}")
            return
        # 本期：标注回诊断，回 pending_review 等重新提单/重诊断
        await client.create_comment(
            run.linear_issue_id,
            f"⚠️ 原根因判错（第 {count} 次），需重新诊断。\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.PENDING_REVIEW)

    async def _handle_missing_dependency(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        child = await client.create_issue(
            team_id=team_id,
            title=f"[依赖] {run.linear_identifier} 修复牵出的外部依赖",
            description=raw,
        )
        await client.create_comment(
            run.linear_issue_id,
            f"🔗 修复牵出外部依赖，已建子单 {child.get('identifier')}，"
            f"父单 blockedBy 子单（本期记录，合并接力待人工）。\n{raw}",
        )
        # 父单保持 building/标注，等子单完成后人工接力（本期不自动 rebase）

    async def _reject(self, run: RepairRun, reason: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        cancel_id = await self._state_id_by_type(client, team_id, "canceled") if team_id else None
        if cancel_id:
            await client.update_issue(run.linear_issue_id, state_id=cancel_id)
        await client.create_comment(run.linear_issue_id, f"🚫 产研退回：{reason}")
        self.store.update(run.linear_issue_id, stage=Stage.REJECTED)

    # ── 轮询入口（scheduler 调用）────────────────────────────────────────
    async def poll_building_runs(self) -> None:
        """扫描所有 building 的 run，逐个尝试分析报告。"""
        for run in self.store.list_by_stage(Stage.BUILDING):
            try:
                await self.analyze_report(run.linear_issue_id)
            except Exception:
                logger.error(
                    "[Repair] poll analyze failed: %s",
                    run.linear_issue_id,
                    exc_info=True,
                )


# ── module-level singleton ─────────────────────────────────────────────
_coordinator: Optional[RepairCoordinator] = None


def set_coordinator(coord: RepairCoordinator) -> None:
    global _coordinator
    _coordinator = coord


def get_coordinator() -> Optional[RepairCoordinator]:
    """linear handler 软依赖此函数；repair 未启用时返回 None。"""
    return _coordinator
```

- [ ] **Step 5: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_coordinator.py -v`
Expected: PASS（约 9 passed）。若个别断言因字段名不符报错，对照 store.py 字段修正测试或实现。

- [ ] **Step 6: Commit**

```bash
git add plugins/bundled/repair/coordinator.py tests/repair/conftest.py tests/repair/test_coordinator.py
git commit -m "feat(repair): add RepairCoordinator state machine + singleton"
```

---

## Task 6: cli.py — create-issue 子命令

**Files:**
- Create: `plugins/bundled/repair/cli.py`
- Test: `tests/repair/test_cli.py`

agent（issue-diagnosis）判定代码 bug 且用户同意后，用 Write 写一个 payload JSON，再跑此 CLI 建 Linear 单 + 落 repair_runs(pending_review)。payload 经临时文件传，避开多行文本 shell 转义。

payload JSON 字段：`team_id`(或 `workspace_id`+由 CLI 取默认 team)、`title`、`root_cause`、`evidence`、`repair_plan`、`repo`。CLI 输出单行 JSON 到 stdout。

- [ ] **Step 1: 写失败测试**

Create `tests/repair/test_cli.py`:
```python
"""cli.py create-issue 测试。

Run: python -m pytest tests/repair/test_cli.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair import cli


@pytest.mark.unit
def test_load_payload_reads_json(tmp_path):
    p = tmp_path / "payload.json"
    p.write_text(
        json.dumps(
            {
                "team_id": "team-1",
                "title": "bug: NPE",
                "root_cause": "空指针",
                "evidence": "日志",
                "repair_plan": "判空",
                "repo": "ai-agent/foo",
            }
        ),
        encoding="utf-8",
    )
    data = cli.load_payload(str(p))
    assert data["title"] == "bug: NPE"
    assert data["repo"] == "ai-agent/foo"


@pytest.mark.unit
def test_build_description_combines_fields():
    desc = cli.build_description(
        root_cause="空指针", evidence="日志 X", repair_plan="判空"
    )
    assert "空指针" in desc
    assert "日志 X" in desc
    assert "判空" in desc
    assert "根因" in desc


@pytest.mark.unit
async def test_create_issue_flow_writes_store_and_prints(tmp_path, capsys):
    # Arrange
    payload = {
        "team_id": "team-1",
        "workspace_id": "ws-1",
        "title": "bug: NPE",
        "root_cause": "空指针",
        "evidence": "日志",
        "repair_plan": "判空",
        "repo": "ai-agent/foo",
    }
    pfile = tmp_path / "payload.json"
    pfile.write_text(json.dumps(payload), encoding="utf-8")

    fake_client = MagicMock()
    fake_client.create_issue = AsyncMock(
        return_value={"id": "issue-uuid", "identifier": "ENG-7", "url": "http://x"}
    )
    store = MagicMock()

    # Act
    with patch.object(cli, "_make_linear_client", return_value=fake_client), patch.object(
        cli, "_make_store", return_value=store
    ):
        await cli.create_issue_cmd(str(pfile))

    # Assert
    out = capsys.readouterr().out.strip().splitlines()[-1]
    result = json.loads(out)
    assert result["ok"] is True
    assert result["identifier"] == "ENG-7"
    assert result["issue_id"] == "issue-uuid"
    # 落了 repair_runs
    store.upsert.assert_called_once()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_cli.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'plugins.bundled.repair.cli'`

- [ ] **Step 3: 实现 cli.py**

Create `plugins/bundled/repair/cli.py`:
```python
"""agent 调用入口：create-issue 子命令。

issue-diagnosis agent 判 bug + 用户同意后调用：
  $AGENTS_ROOT/.venv/bin/python plugins/bundled/repair/cli.py create-issue --input /tmp/repair/payload.json

stdout 输出单行 JSON：{"ok": true, "identifier": "ENG-7", "issue_id": "..."}
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# 用 PYTHONPATH=$AGENTS_ROOT 引仓库模块（与现有 hooks 同源）
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def load_payload(path: str) -> dict:
    """读 payload JSON 文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_description(root_cause: str, evidence: str, repair_plan: str) -> str:
    """把根因/证据/修复计划拼成 Linear 单 Markdown 描述。"""
    return (
        f"## 根因\n{root_cause}\n\n"
        f"## 证据\n{evidence}\n\n"
        f"## 修复计划\n{repair_plan}\n\n"
        f"---\n_本单由 issue-diagnosis 自动诊断生成，待审核后进入自动修复流水线。_"
    )


def _make_linear_client(workspace_id: str):
    """构造 LinearClient（取 token）。"""
    from plugins.bundled.linear.token_store import TokenStore

    db_path = os.getenv("LINEAR_TOKEN_DB", "data/linear/linear_tokens.db")
    ts = TokenStore(str(_ROOT / db_path) if not os.path.isabs(db_path) else db_path)
    ws = workspace_id or ts.get_first_workspace_id()
    token = ts.get_token(ws) if ws else None
    if not token:
        raise RuntimeError(f"no Linear token for workspace={ws}")
    from plugins.bundled.linear.linear_client import LinearClient

    return LinearClient(token), ws


def _make_store():
    from plugins.bundled.repair.store import RepairStore

    db_path = os.getenv("REPAIR_DB_PATH", "data/repair/repair_runs.db")
    full = str(_ROOT / db_path) if not os.path.isabs(db_path) else db_path
    return RepairStore(full)


async def create_issue_cmd(input_path: str) -> None:
    """建 Linear 单 + 落 repair_runs(pending_review)，结果打到 stdout。"""
    from plugins.bundled.repair.store import RepairRun, Stage

    payload = load_payload(input_path)
    title = payload["title"]
    team_id = payload.get("team_id", "")
    workspace_id = payload.get("workspace_id", "")

    # _make_linear_client 在测试中被 patch（返回 MagicMock，非 tuple），故兼容两种返回
    made = _make_linear_client(workspace_id)
    if isinstance(made, tuple):
        client, workspace_id = made
    else:
        client = made

    description = build_description(
        payload.get("root_cause", ""),
        payload.get("evidence", ""),
        payload.get("repair_plan", ""),
    )

    issue = await client.create_issue(
        team_id=team_id, title=title, description=description
    )

    store = _make_store()
    store.upsert(
        RepairRun(
            linear_issue_id=issue["id"],
            linear_identifier=issue.get("identifier", ""),
            workspace_id=workspace_id,
            stage=Stage.PENDING_REVIEW,
            repo=payload.get("repo", ""),
            root_cause=payload.get("root_cause", ""),
            repair_plan=payload.get("repair_plan", ""),
        )
    )

    print(
        json.dumps(
            {
                "ok": True,
                "identifier": issue.get("identifier", ""),
                "issue_id": issue["id"],
                "url": issue.get("url", ""),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="repair pipeline CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create-issue", help="建 Linear bug 单")
    p_create.add_argument("--input", required=True, help="payload JSON 文件路径")
    args = parser.parse_args()

    if args.cmd == "create-issue":
        try:
            asyncio.run(create_issue_cmd(args.input))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_cli.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add plugins/bundled/repair/cli.py tests/repair/test_cli.py
git commit -m "feat(repair): add create-issue CLI for agent to file Linear bug"
```

---

## Task 7: plugin.py — RepairChannelPlugin + 自建 scheduler

**Files:**
- Create: `plugins/bundled/repair/plugin.py`
- Create: `plugins/bundled/repair/plugin.json`
- Test: `tests/repair/test_plugin.py`

插件职责：① 构造 store / jenkins / coordinator 并 `set_coordinator()` 注册 singleton；② `on_start()` 自建 `AsyncIOScheduler`，按 `REPAIR_POLL_ENABLED` 决定是否注册 `poll_building_runs` 定时任务；③ `on_stop()` shutdown scheduler；④ 注册 `/repair/gitlab/webhook` 路由骨架（本期验签占位，不作主驱动）。

LinearClient factory：用 linear 插件的 TokenStore 按 workspace_id 取 token 构造 LinearClient。

- [ ] **Step 1: 写 plugin.json**

Create `plugins/bundled/repair/plugin.json`:
```json
{
  "id": "repair",
  "name": "Bug 修复流水线",
  "version": "1.0.0",
  "description": "Linear 中枢的自动 bug 修复流水线：提单→审核→TDD改码→建MR→Jenkins→三类归因回转",
  "type": "channel",
  "entry_point": "plugin:register",
  "config_schema": {
    "type": "object",
    "properties": {
      "repair_db_path": {
        "type": "string",
        "default": "data/repair/repair_runs.db",
        "description": "repair_runs SQLite 路径"
      },
      "poll_interval_seconds": {
        "type": "integer",
        "default": 60,
        "description": "构建报告轮询间隔（秒）"
      },
      "fix_retry_limit": {
        "type": "integer",
        "default": 3,
        "description": "代码错同分支重修上限 N"
      },
      "rediagnose_limit": {
        "type": "integer",
        "default": 2,
        "description": "根因错重诊断上限 M"
      }
    }
  }
}
```

- [ ] **Step 2: 写失败测试**

Create `tests/repair/test_plugin.py`:
```python
"""RepairChannelPlugin 构造与 singleton 注册测试。

Run: python -m pytest tests/repair/test_plugin.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair import coordinator as coord_mod
from plugins.bundled.repair.plugin import RepairChannelPlugin


def _make_api(tmp_path):
    api = MagicMock()
    api.config = {
        "repair_db_path": str(tmp_path / "repair.db"),
        "poll_interval_seconds": 60,
        "fix_retry_limit": 3,
        "rediagnose_limit": 2,
    }
    api.agent_service = MagicMock()
    return api


@pytest.mark.unit
def test_plugin_registers_singleton(tmp_path):
    # Arrange
    coord_mod.set_coordinator(None)
    api = _make_api(tmp_path)

    # Act
    plugin = RepairChannelPlugin(api)

    # Assert: 构造后 singleton 已注册
    assert coord_mod.get_coordinator() is not None
    assert plugin.get_meta().id == "repair"


@pytest.mark.unit
async def test_on_start_without_poll_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("REPAIR_POLL_ENABLED", "false")
    api = _make_api(tmp_path)
    plugin = RepairChannelPlugin(api)

    await plugin.on_start()
    await plugin.on_stop()


@pytest.mark.unit
def test_create_router_has_webhook(tmp_path):
    api = _make_api(tmp_path)
    plugin = RepairChannelPlugin(api)
    router = plugin.create_router()
    paths = [r.path for r in router.routes]
    assert any("/repair/gitlab/webhook" in p for p in paths)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_plugin.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'plugins.bundled.repair.plugin'`

- [ ] **Step 4: 实现 plugin.py**

Create `plugins/bundled/repair/plugin.py`:
```python
"""Bug 修复流水线插件入口。

构造 store/jenkins/coordinator 并注册 module-level singleton；
on_start 自建 AsyncIOScheduler 轮询构建报告；注册 GitLab webhook 路由骨架。
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.constants import AGENTS_ROOT
from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.repair import coordinator as coord_mod
from plugins.bundled.repair.coordinator import RepairCoordinator
from plugins.bundled.repair.jenkins_client import JenkinsClient
from plugins.bundled.repair.store import RepairStore

logger = logging.getLogger(__name__)


def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else str(AGENTS_ROOT / path)


class RepairChannelPlugin(ChannelPlugin):
    """修复流水线 channel plugin（自建 scheduler + GitLab webhook 骨架）。"""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config

        store = RepairStore(_resolve(self.config.get("repair_db_path", "data/repair/repair_runs.db")))
        jenkins = JenkinsClient(mock_ready=True)

        coord = RepairCoordinator(
            agent_service=api.agent_service,
            store=store,
            jenkins=jenkins,
            linear_client_factory=self._linear_client_factory,
            fix_retry_limit=int(self.config.get("fix_retry_limit", 3)),
            rediagnose_limit=int(self.config.get("rediagnose_limit", 2)),
        )
        self.store = store
        self.coordinator = coord
        coord_mod.set_coordinator(coord)

        self._scheduler = None  # 在 on_start 自建

    # ── LinearClient factory ─────────────────────────────────────────────
    def _linear_client_factory(self, workspace_id: str):
        from plugins.bundled.linear.linear_client import LinearClient
        from plugins.bundled.linear.token_store import TokenStore

        db_path = _resolve(os.getenv("LINEAR_TOKEN_DB", "data/linear/linear_tokens.db"))
        ts = TokenStore(db_path)
        ws = workspace_id or ts.get_first_workspace_id()
        token = ts.get_token(ws) if ws else None
        if not token:
            raise RuntimeError(f"no Linear token for workspace={ws}")
        return LinearClient(token)

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="repair",
            name="Bug 修复流水线",
            webhook_path="/repair/gitlab/webhook",
            description="Linear 中枢自动 bug 修复流水线",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=False,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=False,
            transfer_human=False,
        )

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["repair"])

        @router.post("/repair/gitlab/webhook")
        async def gitlab_webhook(request: Request):
            """GitLab webhook 骨架（本期占位，验签 TODO，不作主驱动）。

            TODO(联调): 校验 X-Gitlab-Token；解析 MR/pipeline 事件，
            按 source branch 反查 repair_runs，推进 coordinator。
            本期 APScheduler 轮询为主驱动。
            """
            logger.info("[Repair] gitlab webhook received (placeholder)")
            return JSONResponse(status_code=200, content={"ok": True})

        return router

    async def send_text(self, recipient_id, text, context=None) -> bool:
        return False

    async def on_start(self) -> None:
        poll_enabled = os.getenv("REPAIR_POLL_ENABLED", "false").lower() in ("1", "true", "yes")
        if not poll_enabled:
            logger.info("[Repair] poll disabled (set REPAIR_POLL_ENABLED=true to enable)")
            return
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        interval = int(self.config.get("poll_interval_seconds", 60))
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self.coordinator.poll_building_runs,
            "interval",
            seconds=interval,
            id="repair_poll",
        )
        self._scheduler.start()
        logger.info("[Repair] poll scheduler started, interval=%ds", interval)

    async def on_stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("[Repair] poll scheduler stopped")


def register(api: PluginAPI) -> RepairChannelPlugin:
    """插件注册入口，由 PluginManager 调用。"""
    plugin = RepairChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[Repair] plugin registered")
    return plugin
```

- [ ] **Step 5: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_plugin.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add plugins/bundled/repair/plugin.py plugins/bundled/repair/plugin.json tests/repair/test_plugin.py
git commit -m "feat(repair): add RepairChannelPlugin with self-built scheduler"
```

---

## Task 8: linear 插件接 Issue 事件 → 委派 coordinator

**Files:**
- Modify: `plugins/bundled/linear/handler.py`
- Modify: `plugins/bundled/linear/plugin.py`
- Test: `tests/repair/test_linear_issue_event.py`

linear webhook 现仅处理 `AgentSession` 事件。需加 `Issue` 事件分支：当 Issue 状态变更/分配且新状态为「审核通过」时，委派 `RepairCoordinator.start_development()`。软依赖 repair 插件（未启用时 import 失败则跳过）。

- [ ] **Step 1: 写失败测试**

Create `tests/repair/test_linear_issue_event.py`:
```python
"""linear handler Issue 事件委派测试。

Run: python -m pytest tests/repair/test_linear_issue_event.py -v
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.linear.handler import LinearSessionHandler
from plugins.bundled.repair import coordinator as coord_mod


def _make_handler():
    return LinearSessionHandler(
        agent_service=MagicMock(),
        token_store=MagicMock(),
        config={},
    )


@pytest.mark.unit
async def test_issue_event_approval_triggers_start_development():
    fake_coord = MagicMock()
    fake_coord.start_development = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {
            "id": "issue-1",
            "state": {"name": "In Progress", "type": "started"},
        },
    }

    await handler.handle_issue_event(payload)

    fake_coord.start_development.assert_awaited_once_with("issue-1")


@pytest.mark.unit
async def test_issue_event_non_approval_state_ignored():
    fake_coord = MagicMock()
    fake_coord.start_development = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {"id": "issue-1", "state": {"name": "Backlog", "type": "backlog"}},
    }

    await handler.handle_issue_event(payload)

    fake_coord.start_development.assert_not_awaited()


@pytest.mark.unit
async def test_issue_event_no_coordinator_is_safe():
    coord_mod.set_coordinator(None)
    handler = _make_handler()
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {"id": "issue-1", "state": {"name": "In Progress", "type": "started"}},
    }
    await handler.handle_issue_event(payload)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_linear_issue_event.py -v`
Expected: FAIL，`AttributeError: 'LinearSessionHandler' object has no attribute 'handle_issue_event'`

- [ ] **Step 3: 给 handler 加 handle_issue_event**

在 `plugins/bundled/linear/handler.py` 的 `handle_stopped` 方法之后（即 `# ── 核心处理流程 ──` 注释之前）插入：

```python
    async def handle_issue_event(self, payload: Dict[str, Any]) -> None:
        """处理 Issue 状态变更/分配事件，审核通过则委派 RepairCoordinator。

        当 Issue 新状态为「审核通过」（如 In Progress）时，触发自动开发。
        软依赖 repair 插件：未启用时 get_coordinator() 返回 None，直接跳过。

        Args:
            payload: Linear Webhook 原始 payload（type=Issue）
        """
        data = payload.get("data", {})
        issue_id = data.get("id", "")
        state = data.get("state", {}) or {}
        state_name = state.get("name", "")

        if not issue_id:
            return

        try:
            from plugins.bundled.repair.coordinator import get_coordinator
            from plugins.bundled.repair import prompts
        except Exception:
            return

        coordinator = get_coordinator()
        if coordinator is None:
            return

        if not prompts.is_approval_state(state_name):
            logger.info(
                "[Linear] Issue %s state=%s not approval, ignore", issue_id, state_name
            )
            return

        logger.info(
            "[Linear] Issue %s approved (state=%s), triggering development",
            issue_id,
            state_name,
        )
        try:
            await coordinator.start_development(issue_id)
        except Exception:
            logger.error(
                "[Linear] start_development failed for %s", issue_id, exc_info=True
            )
```

- [ ] **Step 4: 在 plugin.py webhook 路由分发 Issue 事件**

在 `plugins/bundled/linear/plugin.py` 的 `linear_webhook` 函数内，找到现有分支：

```python
            if event_type in ("AgentSession", "AgentSessionEvent"):
                if action == "created":
                    background_tasks.add_task(handler.handle_created, payload_json)
                elif action == "prompted":
                    background_tasks.add_task(handler.handle_prompted, payload_json)
                elif action in ("stopped", "stop"):
                    background_tasks.add_task(handler.handle_stopped, payload_json)
```

在其后追加（与 `if` 同级）：

```python
            elif event_type == "Issue":
                background_tasks.add_task(handler.handle_issue_event, payload_json)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_linear_issue_event.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 回归 repair 全部测试**

Run: `source .venv/bin/activate && python -m pytest tests/repair/ -v`
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add plugins/bundled/linear/handler.py plugins/bundled/linear/plugin.py tests/repair/test_linear_issue_event.py
git commit -m "feat(linear): delegate Issue approval event to RepairCoordinator"
```

---

## Task 9: git 写权限定向放开（PreToolUse hook + settings）

**Files:**
- Create: `agent_cwd/.claude/hooks/restrict-git-write.py`
- Modify: `agent_cwd/.claude/settings.json`
- Test: `tests/repair/test_restrict_git_write.py`

**关键**：`settings.json` 的 `deny` 优先级最高，无法被 `allow` 覆盖。所以必须从 deny **移除** git 写命令，改由 hook 按工作目录放行。hook 逻辑：解析 Bash 命令，若是 git 写操作（add/commit/push/checkout -b 等），仅当命令字符串含 `/tmp/repair/` 时放行；否则一律 deny。同时硬禁 `git merge`、push 主干（main/master）、`merge_when_pipeline_succeeds`。

> hook 判定「工作目录」的方式：developer skill 约定用 `cd /tmp/repair/<id> && git ...` 或 `git -C /tmp/repair/<id> ...`。hook 检查命令字符串是否包含 `/tmp/repair/`。这是务实近似，符合 skill 约定写法。

- [ ] **Step 1: 写失败测试**

Create `tests/repair/test_restrict_git_write.py`:
```python
"""restrict-git-write hook 单元测试（直接调 decide 函数）。

Run: python -m pytest tests/repair/test_restrict_git_write.py -v
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = ROOT / "agent_cwd" / ".claude" / "hooks"

_spec = importlib.util.spec_from_file_location(
    "restrict_git_write", str(HOOK_DIR / "restrict-git-write.py")
)
rgw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rgw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        "cd /tmp/repair/ENG-1 && git add -A",
        "git -C /tmp/repair/ENG-1 commit -m 'fix'",
        "cd /tmp/repair/ENG-1 && git checkout -b fix/ENG-1",
        "cd /tmp/repair/ENG-1 && git push -o merge_request.create origin fix/ENG-1",
    ],
)
def test_allows_git_write_in_repair_dir(cmd):
    assert rgw.decide(cmd) == "allow"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        "git add -A",
        "cd /tmp/gitlab/src/foo && git commit -m x",
        "git checkout -b feature/x",
    ],
)
def test_denies_git_write_outside_repair(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        "cd /tmp/repair/ENG-1 && git merge main",
        "cd /tmp/repair/ENG-1 && git push origin main",
        "cd /tmp/repair/ENG-1 && git push origin master",
        "cd /tmp/repair/ENG-1 && git push -o merge_request.merge_when_pipeline_succeeds origin fix/x",
    ],
)
def test_denies_dangerous_even_in_repair_dir(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
def test_non_git_command_is_allow():
    assert rgw.decide("ls -la /tmp/repair/ENG-1") == "allow"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_restrict_git_write.py -v`
Expected: FAIL，找不到 `restrict-git-write.py`。

- [ ] **Step 3: 实现 restrict-git-write.py**

Create `agent_cwd/.claude/hooks/restrict-git-write.py`:
```python
#!/usr/bin/env python3
"""PreToolUse hook：git 写操作仅在 /tmp/repair/** 目录放行。

deny 优先级高于 allow，所以 settings.json 的 deny 不再硬封 git 写，
改由本 hook 按命令上下文决定：
  - git 写命令（add/commit/push/checkout -b/branch -d/reset/rebase/stash/tag）
    且命令字符串含 /tmp/repair/ → allow
  - 其余 git 写 → deny
  - 危险操作（merge / push 主干 / merge_when_pipeline_succeeds）→ 永远 deny
  - 非 git 命令 → allow（交给其它规则）
"""
import json
import re
import sys

_REPAIR_PREFIX = "/tmp/repair/"

_WRITE_SUBCMDS = (
    "add",
    "commit",
    "push",
    "checkout -b",
    "branch -d",
    "branch -D",
    "reset",
    "rebase",
    "stash",
    "tag",
)

_DANGER_PATTERNS = (
    r"\bgit\s+merge\b",
    r"git\s+push[^\n]*\borigin\s+main\b",
    r"git\s+push[^\n]*\borigin\s+master\b",
    r"merge_when_pipeline_succeeds",
    r"\bgit\s+push[^\n]*\s(main|master)\b",
)


def _is_git_write(cmd: str) -> bool:
    if "git " not in cmd and not cmd.strip().startswith("git"):
        return False
    for sub in _WRITE_SUBCMDS:
        if re.search(rf"git\b[^\n]*\b{re.escape(sub)}", cmd):
            return True
    return False


def decide(cmd: str) -> str:
    """返回 'allow' 或 'deny'。"""
    for pat in _DANGER_PATTERNS:
        if re.search(pat, cmd):
            return "deny"

    if not _is_git_write(cmd):
        return "allow"

    if _REPAIR_PREFIX in cmd:
        return "allow"
    return "deny"


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    if event.get("tool_name", "") != "Bash":
        return

    cmd = event.get("tool_input", {}).get("command", "")
    if decide(cmd) == "deny":
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "git 写操作仅允许在 /tmp/repair/** 修复目录执行，"
                    "且禁止 merge / 推主干 / 自动合并 MR。"
                ),
            }
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_restrict_git_write.py -v`
Expected: PASS（约 12 passed）

- [ ] **Step 5: 改 settings.json — 移除 git 写硬封 + 注册 hook**

修改 `agent_cwd/.claude/settings.json`。把 `permissions.deny` 从：
```json
    "deny": [
      "Bash(git add*)",
      "Bash(git commit*)",
      "Bash(git push*)",
      "Bash(git checkout -b*)",
      "Bash(git branch -d*)",
      "Bash(git branch -D*)",
      "Bash(git reset*)",
      "Bash(git rebase*)",
      "Bash(git merge*)",
      "Bash(git tag*)",
      "Bash(git stash*)",
      "Edit(/tmp/gitlab/**)",
      "Write(/tmp/gitlab/**)"
    ]
```
改为：
```json
    "deny": [
      "Bash(git merge*)",
      "Edit(/tmp/gitlab/**)",
      "Write(/tmp/gitlab/**)"
    ]
```

> 说明：`git merge` 仍用 deny 硬封（双保险，hook 也禁）。其余 git 写从 deny 移除，交 `restrict-git-write.py` 按目录放行。`/tmp/gitlab/**` 的 Edit/Write 保持 deny。

在 `hooks.PreToolUse` 数组中**追加**一个 matcher（与现有 `Edit|Write` 并列）：
```json
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "../.venv/bin/python3 .claude/hooks/restrict-git-write.py"
          }
        ]
      }
```

修改后 `hooks.PreToolUse` 应含三个 matcher：`mcp__elastic__searchTraceOrKeyWordsLog`、`Edit|Write`、`Bash`。

- [ ] **Step 6: 校验 settings.json 合法**

Run:
```bash
source .venv/bin/activate && python -c "import json; json.load(open('agent_cwd/.claude/settings.json')); print('settings.json OK')"
```
Expected: `settings.json OK`

- [ ] **Step 7: Commit**

```bash
git add agent_cwd/.claude/hooks/restrict-git-write.py agent_cwd/.claude/settings.json tests/repair/test_restrict_git_write.py
git commit -m "feat(repair): open git write only for /tmp/repair via PreToolUse hook"
```

---

## Task 10: 两个新 skill 的 SKILL.md

**Files:**
- Create: `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md`
- Create: `agent_cwd/.claude/skills/repair-report-analyzer/SKILL.md`

这两个 skill 是 agent 行为说明书，无单元测试（skill 是 prompt，不是代码）。验证方式见 Task 12 集成测试用 stub agent。约束严格：developer 只在 `/tmp/repair/<id>/` 修复分支写码并 push，禁 push 主干/禁 merge/禁自动合并 MR；输出必须含 `【分支】`/`【MR链接】`/`【复现测试】` 供 coordinator 解析。analyzer 输出必须含 `【判定】` 四选一。

- [ ] **Step 1: 创建 bug-fix-developer/SKILL.md**

Create `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md`:
```markdown
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
- **禁止** push 到 main/master，**禁止** `git merge`，**禁止** 任何自动合并 MR 的 push option（如 `merge_request.merge_when_pipeline_succeeds`）
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

- 按修复计划改**最小**代码使复现测试转绿。
- 不顺手重构无关代码（YAGNI / Surgical Changes）。

## Step 4：REFACTOR + 回归

- 必要的重构，跑相关测试确认无回归（本地能跑则跑）。

## Step 5：commit + push + 建 MR

```bash
cd "$WORK"
git add -A
git commit -m "fix($ID): <一句话修复说明>"
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
```

- [ ] **Step 2: 创建 repair-report-analyzer/SKILL.md**

Create `agent_cwd/.claude/skills/repair-report-analyzer/SKILL.md`:
```markdown
---
name: repair-report-analyzer
description: >-
  修复测试报告的三类归因分析 skill。输入本地 TDD 结果 + Jenkins 测试报告 + 原根因/修复计划，
  判定修复是否成功，未成功则归因为「代码错 / 根因错 / 漏依赖」之一，供 coordinator 决定回转路径。
  由修复流水线 coordinator 调起。
---

# 修复报告分析（三类归因）

根据测试报告判断 bug 是否解决，未解决时给出归因。**输出必须严格遵守末尾格式，供 coordinator 程序解析。**

## 输入（由 coordinator 拼进 prompt）

- 本地 TDD 测试结果（如有）
- Jenkins 自动化测试报告（本期可能为 mock）
- 原根因
- 修复计划

## 判定标准

| 判定 | 标准 |
|------|------|
| **已解决** | 复现测试转绿，且报告中无新增失败/回归 |
| **代码错** | 修复计划方向正确，但实现有偏差或引入了新错误（同分支可继续修） |
| **根因错** | 测试证明原诊断的根因判错了（再怎么按原计划修都不会对） |
| **漏依赖** | 修复本身正确，但牵出范围外的依赖问题（需改别的服务/前置数据） |

判定不确定时，**保守归为「代码错」**（走同分支重修），绝不轻易判「已解决」而错误关单。

## 输出格式（必须严格遵守）

```
【判定】已解决 | 代码错 | 根因错 | 漏依赖
【依据】<引用报告中支撑判定的具体条目>
【后续动作】
  - 已解决：无
  - 代码错：<同分支重修要点>
  - 根因错：<为何原根因站不住>
  - 漏依赖：<牵出的外部依赖，建议子单标题>
```

【判定】行必须恰好包含「已解决/代码错/根因错/漏依赖」四词之一，不得改写措辞。
```

- [ ] **Step 3: 验证 skill 目录被 SDK 识别**

Run:
```bash
ls agent_cwd/.claude/skills/bug-fix-developer/SKILL.md agent_cwd/.claude/skills/repair-report-analyzer/SKILL.md
```
Expected: 两文件都存在。

> 注：skill 能否被加载取决于 `DEFAULT_SKILLS` 是否包含它们（见 Task 12 部署说明）。本步只确认文件就位。

- [ ] **Step 4: Commit**

```bash
git add agent_cwd/.claude/skills/bug-fix-developer/ agent_cwd/.claude/skills/repair-report-analyzer/
git commit -m "feat(repair): add bug-fix-developer and repair-report-analyzer skills"
```

---

## Task 11: 改 issue-diagnosis 加提单步

**Files:**
- Modify: `agent_cwd/.claude/skills/issue-diagnosis/SKILL.md`

在 Step 6 输出结论之后、Step 7 之前，插入 Step 6.5：当根因指向代码逻辑（Step 3/4 已判定进入源码定位）且已 clone 到源码时，用 AskUserQuestion 问用户是否自动修复；同意则写 payload JSON 并跑 `repair/cli.py create-issue` 提单。

- [ ] **Step 1: 在 SKILL.md 插入 Step 6.5**

在 `agent_cwd/.claude/skills/issue-diagnosis/SKILL.md` 中，找到 `## Step 7：反馈监听与学习` 这一行，在它**之前**插入以下整段：

````markdown
## Step 6.5：代码 bug 自动修复提单（可选）

**仅当满足全部条件时执行，否则跳过本步直接进入 Step 7：**
- 本次诊断走过 Step 4 源码定位（根因指向代码逻辑），且
- 已成功 clone 到目标仓库源码（拿到 `namespace/repo` 与 `project_id`），且
- 根因结论有源码级证据（具体类/行号）

满足时，用 `AskUserQuestion` 询问用户：

> 本次根因定位到代码逻辑层面。是否要启动自动修复流水线？同意后将创建一张 Linear bug 单，您在 Linear 审核确认后系统会自动进行 TDD 修复并提交 MR（合并到主干仍需人工）。

- 用户**否** → 跳过，进入 Step 7。
- 用户**同意** → 执行以下提单流程：

**① 用 Write 写 payload 文件** `/tmp/repair/payload.json`（避开多行 shell 转义）：

```json
{
  "team_id": "",
  "workspace_id": "",
  "title": "fix: <一句话 bug 标题>",
  "root_cause": "<Step 6 的根因结论>",
  "evidence": "<日志/数据库/源码证据，多行>",
  "repair_plan": "<修复方向，基于源码定位给出>",
  "repo": "<namespace/repo，如 ai-agent/foo>"
}
```

`team_id`/`workspace_id` 未知时留空，CLI 会取默认 workspace + 团队。`repair_plan` 只写修复**方向**（哪个类/方法、加什么校验），不写完整代码。

**② 跑 CLI 提单**：

```bash
$AGENTS_ROOT/.venv/bin/python plugins/bundled/repair/cli.py create-issue --input /tmp/repair/payload.json
```

（`$AGENTS_ROOT` 为仓库根目录；若环境变量未设置，用绝对路径 `/Users/jinfan/code/git-agent/agent-harness`。）

**③ 解析 stdout 的单行 JSON**，向用户回复：

> 已创建 Linear bug 单 {identifier}。请在 Linear 中审核，确认无误后将单子拖到「开发中」状态即可启动自动修复。

CLI 返回 `{"ok": false, ...}` 时如实告知用户提单失败，不影响 Step 6 已输出的诊断结论。

**约束**：本步只提单，不在此 skill 内改任何代码；提单失败不阻塞诊断流程。
````

- [ ] **Step 2: 校验 SKILL.md 结构未破坏（Step 6.5 在 Step 6 与 Step 7 之间）**

Run:
```bash
grep -n "^## Step 6：\|^## Step 6.5：\|^## Step 7：" agent_cwd/.claude/skills/issue-diagnosis/SKILL.md
```
Expected: 三行按 6 → 6.5 → 7 顺序出现。

- [ ] **Step 3: Commit**

```bash
git add agent_cwd/.claude/skills/issue-diagnosis/SKILL.md
git commit -m "feat(issue-diagnosis): add Step 6.5 to file Linear bug for auto-repair"
```

---

## Task 12: 配置接线 + 集成测试 + 部署说明

**Files:**
- Modify: `plugins/config.json`
- Modify: `.env.example`
- Test: `tests/repair/test_integration.py`

启用 repair 插件，补 env 文档，写端到端集成测试（全 mock 外部，验编排闭环）。

- [ ] **Step 1: 写集成测试**

Create `tests/repair/test_integration.py`:
```python
"""端到端集成测试：create-issue → 审核 webhook → 开发 → 轮询 → 分析 → 终态。
全部 mock 外部（Linear / Jenkins / AgentService）。

Run: python -m pytest tests/repair/test_integration.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.coordinator import RepairCoordinator
from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
from tests.repair.conftest import FakeAgentService, FakeJenkins, FakeLinearClient


@pytest.mark.integration
async def test_happy_path_end_to_end(tmp_path):
    # Arrange: 提单后处于 pending_review
    store = RepairStore(str(tmp_path / "r.db"))
    store.upsert(
        RepairRun(
            linear_issue_id="issue-1",
            linear_identifier="ENG-1",
            workspace_id="ws-1",
            stage=Stage.PENDING_REVIEW,
            repo="ai-agent/foo",
            root_cause="空指针",
            repair_plan="判空",
        )
    )
    fake_linear = FakeLinearClient()
    agent = FakeAgentService(
        [
            "【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java",  # developer
            "【判定】已解决\n【依据】全绿\n【后续动作】无",  # analyzer
        ]
    )
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=FakeJenkins(ready=True),
        linear_client_factory=lambda ws: fake_linear,
    )

    # Act：模拟审核通过 → 开发
    await coord.start_development("issue-1")
    assert store.get("issue-1").stage == Stage.BUILDING
    # 模拟轮询 → 报告就绪 → 分析
    await coord.poll_building_runs()

    # Assert：终态 resolved + Linear 置 Done
    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    assert run.mr_url == "http://mr/1"
    assert any(kw["state_id"] == "s-done" for _, kw in fake_linear.updated)


@pytest.mark.integration
async def test_code_error_retry_then_resolve(tmp_path):
    # Arrange
    store = RepairStore(str(tmp_path / "r.db"))
    store.upsert(
        RepairRun(
            linear_issue_id="issue-1",
            linear_identifier="ENG-1",
            workspace_id="ws-1",
            stage=Stage.PENDING_REVIEW,
            repo="ai-agent/foo",
            root_cause="空指针",
            repair_plan="判空",
        )
    )
    fake_linear = FakeLinearClient()
    agent = FakeAgentService(
        [
            "【分支】fix/ENG-1\n【MR链接】http://mr/1",  # developer 首次
            "【判定】代码错\n【依据】NPE 仍在\n【后续动作】补判空",  # analyzer 第一轮
            "【分支】fix/ENG-1\n【MR链接】http://mr/2",  # developer 重修
            "【判定】已解决\n【依据】绿\n【后续动作】无",  # analyzer 第二轮
        ]
    )
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=FakeJenkins(ready=True),
        linear_client_factory=lambda ws: fake_linear,
    )

    # Act
    await coord.start_development("issue-1")  # → building
    await coord.poll_building_runs()  # analyzer 代码错 → resume 重修 → building
    assert store.get("issue-1").fix_retry_count == 1
    assert store.get("issue-1").stage == Stage.BUILDING
    await coord.poll_building_runs()  # analyzer 已解决 → resolved

    # Assert
    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    # 重修用了 resume（同 develop_session_id）
    dev_calls = [c for c in agent.calls if c.session_id]
    assert any(c.session_id == "claude-sess-1" for c in dev_calls)
```

- [ ] **Step 2: 运行集成测试确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/repair/test_integration.py -v`
Expected: PASS（2 passed）

- [ ] **Step 3: 启用 repair 插件**

修改 `plugins/config.json`：
- `enabled` 数组末尾加 `"repair"`
- `plugins` 对象加：
```json
    "repair": {
      "repair_db_path": "data/repair/repair_runs.db",
      "poll_interval_seconds": 60,
      "fix_retry_limit": 3,
      "rediagnose_limit": 2
    }
```

- [ ] **Step 4: 补 .env.example repair 段**

在 `.env.example` 的 GitLab 段之后追加：
```text

# ===========================================
# Bug 修复流水线（repair 插件）
# ===========================================
# 新 skill 必须加进 DEFAULT_SKILLS 才会被加载（SDK skills 是白名单 context filter）：
DEFAULT_SKILLS=customer-service,issue-diagnosis-external,issue-diagnosis,bug-fix-developer,repair-report-analyzer
# 构建报告轮询开关（默认关，本期 Jenkins 为 mock）
REPAIR_POLL_ENABLED=false
# repair 运行时 SQLite 路径
REPAIR_DB_PATH=data/repair/repair_runs.db
# 「审核通过」状态名（逗号分隔，小写匹配；默认 in progress,开发中,...）
# REPAIR_APPROVAL_STATES=in progress,开发中
# clone/pull 用只读 token（沿用现有 GITLAB_TOKEN）；push + 建 MR 用独立写权限 token：
GITLAB_PUSH_TOKEN=
```

- [ ] **Step 5: 校验 config.json 合法**

Run:
```bash
source .venv/bin/activate && python -c "import json; c=json.load(open('plugins/config.json')); assert 'repair' in c['enabled']; assert 'repair' in c['plugins']; print('config.json OK')"
```
Expected: `config.json OK`

- [ ] **Step 6: 全量回归**

Run: `source .venv/bin/activate && python -m pytest tests/repair/ -v`
Expected: 全部 PASS（store/prompts/linear_client/jenkins/coordinator/cli/plugin/linear_issue_event/restrict_git_write/integration）。

- [ ] **Step 7: 验证服务能加载 repair 插件（冒烟）**

Run:
```bash
source .venv/bin/activate && python -c "
import asyncio
from unittest.mock import MagicMock
from plugins.bundled.repair.plugin import RepairChannelPlugin
from plugins.bundled.repair import coordinator
api = MagicMock()
api.config = {'repair_db_path': '/tmp/smoke_repair.db'}
api.agent_service = MagicMock()
p = RepairChannelPlugin(api)
assert coordinator.get_coordinator() is not None
print('repair plugin loads OK')
"
```
Expected: `repair plugin loads OK`

- [ ] **Step 8: Commit**

```bash
git add plugins/config.json .env.example tests/repair/test_integration.py
git commit -m "feat(repair): enable plugin, add integration tests and env docs"
```

---

## 部署 / 联调说明（实现完成后交接用）

实现完成后，上线前需人工确认/配置以下项（非代码任务）：

1. **DEFAULT_SKILLS 必配**：在生产 `.env` 设置 `DEFAULT_SKILLS=customer-service,issue-diagnosis-external,issue-diagnosis,bug-fix-developer,repair-report-analyzer`。否则新 skill 被 SDK 隐藏，流水线无法工作（SDK skills 是白名单 context filter）。
2. **凭证**：填 `GITLAB_PUSH_TOKEN`（写权限 + api scope，用于 push + 建 MR）；`GITLAB_TOKEN` 保持只读用于 clone/pull。
3. **push options 手动验证一次**：拿一个真实 piaozone 仓库，手动跑通 `clone → git checkout -b → 改一行 → commit → git push -o merge_request.create` → 确认 GitLab 生成 MR 且 push 输出回带 URL（需 GitLab ≥11.10 / git ≥2.10）。
4. **Linear 状态映射**：确认团队 workflow「审核通过」状态名，必要时设 `REPAIR_APPROVAL_STATES`。
5. **Linear webhook 配置 Issue 事件**：在 Linear 应用 webhook 设置里勾选 `Issue` 事件类型，回调到 `/linear/webhook`。
6. **开轮询**：联调 Jenkins 前 `REPAIR_POLL_ENABLED=false`；Jenkins client 实现后置 true。
7. **Jenkins 联调**：实现 `jenkins_client.py` 的两个 TODO（job 名/凭证/分支参数/报告格式），不动 coordinator。

**始终人工**：合并 MR 到主干。

## 本期边界

**做**：repair 插件全套（store/coordinator/jenkins 占位/cli/prompts/plugin）、LinearClient 三个写方法、linear handler Issue 事件委派、两个新 skill、issue-diagnosis 提单步、git 写定向放开（hook + settings）、轮询兜底、全套单测 + 集成测试。

**占位待联调**：Jenkins client 真实实现、GitLab webhook 主驱动、agent 主机 Java 构建/测试能力、真实 Linear webhook 连通。

**手动验证一次**：真实 Java 仓库 clone + 建分支 + `push -o merge_request.create` 链路。
