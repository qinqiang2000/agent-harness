# Jenkins 构建+测试集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把修复流水线的 Jenkins mock 占位替换为真实实现：两任务自驱动状态机（cicd-pipeline → at-automated-test）、多服务并行构建、超时兜底转人工、对话重跑 CLI。

**Architecture:** `JenkinsBuildStore` 管两张 SQLite 表（`jenkins_builds` 主表 + `jenkins_cicd_builds` 每 repo 构建记录），`JenkinsClient` 内部后台驱动按节奏推进 phase 并落库，coordinator 的 `get_report` 只读库。`repair_runs` 加 `repos` JSON 字段支持多服务，`prompts.py` 解析对齐，`cli.py` 加 `retrigger-build` 子命令，`coordinator.py` 加超时旁路，`plugin.py` 构造真实 client 并在 `on_start` 扫表接管驱动。

**Tech Stack:** Python 3.11+、httpx（异步 REST）、SQLite WAL、pytest、pytest-asyncio

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `plugins/bundled/repair/jenkins_build_store.py` | 新建 | `JenkinsBuildStore`：`jenkins_builds` + `jenkins_cicd_builds` 两表 CRUD + driver 抢占 |
| `plugins/bundled/repair/jenkins_client.py` | 重写 | 真实 httpx 实现 + 后台驱动 + `trigger_build(repos, branch)` + `get_report` |
| `plugins/bundled/repair/store.py` | 修改 | `RepairRun` + `repair_runs` 表加 `repos` TEXT 字段 |
| `plugins/bundled/repair/prompts.py` | 修改 | `parse_developer_output` 解析 `【仓库】` 兼容单值和 JSON 数组 |
| `plugins/bundled/repair/coordinator.py` | 修改 | `analyze_report` 加超时旁路；`trigger_build` 调用改传 repos 列表 |
| `plugins/bundled/repair/cli.py` | 修改 | 新增 `retrigger-build` 子命令 |
| `plugins/bundled/repair/plugin.py` | 修改 | 构造真实 `JenkinsClient`；`on_start` 扫表拉起驱动 |
| `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md` | 修改 | `【仓库】` 多服务格式说明 + 重跑能力说明 |
| `plugins/config.json` | 修改 | repair 段加 Jenkins 配置项 |
| `.env.example` | 修改 | 加 Jenkins env |
| `tests/repair/test_jenkins_build_store.py` | 新建 | `JenkinsBuildStore` 单测 + 并发抢占测试 |
| `tests/repair/test_jenkins_client.py` | 重写 | 真实逻辑单测（httpx mock transport） |
| `tests/repair/conftest.py` | 修改 | `FakeJenkins` 加 timeout/multi-repo 模式 |
| `tests/repair/test_store.py` | 修改 | `repos` 字段覆盖 |
| `tests/repair/test_prompts.py` | 修改 | `parse_developer_output` 多服务解析 |
| `tests/repair/test_coordinator.py` | 修改 | 超时旁路测试 |
| `tests/repair/test_cli.py` | 修改 | `retrigger-build` 门禁测试 |
| `tests/repair/test_integration.py` | 修改 | 超时旁路集成测试 |

---

## Task 0：JenkinsBuildStore — 两张表 CRUD

**Files:**
- Create: `plugins/bundled/repair/jenkins_build_store.py`
- Create: `tests/repair/test_jenkins_build_store.py`

- [ ] **Step 1：写失败测试（建表 + 基础 CRUD）**

```python
# tests/repair/test_jenkins_build_store.py
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore


@pytest.fixture
def store(tmp_path):
    return JenkinsBuildStore(str(tmp_path / "jenkins.db"))


def test_create_build(store):
    token = store.create_build(
        repos=["piaozone/base/api-auth", "piaozone/base/api-company"],
        branch="fix/ENG-1",
    )
    assert token
    build = store.get_build(token)
    assert build is not None
    assert build["phase"] == "cicd_queued"
    assert build["repos_json"] == '["piaozone/base/api-auth", "piaozone/base/api-company"]'
    assert build["branch"] == "fix/ENG-1"


def test_create_cicd_build_rows(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    rows = store.list_cicd_builds(token)
    assert len(rows) == 1
    assert rows[0]["repo"] == "piaozone/base/api-auth"
    assert rows[0]["service"] == "api-auth"
    assert rows[0]["result"] == "PENDING"


def test_update_build_phase(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="cicd_building")
    build = store.get_build(token)
    assert build["phase"] == "cicd_building"


def test_update_cicd_build_row(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=123, result="SUCCESS")
    rows = store.list_cicd_builds(token)
    assert rows[0]["build_no"] == 123
    assert rows[0]["result"] == "SUCCESS"


def test_list_non_done_builds(store):
    t1 = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    t2 = store.create_build(repos=["piaozone/base/api-company"], branch="fix/ENG-2")
    store.update_build(t1, phase="done_success")
    pending = store.list_non_done_builds()
    tokens = [r["build_token"] for r in pending]
    assert t2 in tokens
    assert t1 not in tokens
```

- [ ] **Step 2：运行确认失败**

```bash
cd /Users/jinfan/code/git-agent/agent-harness
source .venv/bin/activate
python -m pytest tests/repair/test_jenkins_build_store.py -v 2>&1 | head -20
```

期望：`ModuleNotFoundError: No module named 'plugins.bundled.repair.jenkins_build_store'`

- [ ] **Step 3：实现 JenkinsBuildStore**

```python
# plugins/bundled/repair/jenkins_build_store.py
"""jenkins_builds + jenkins_cicd_builds 两张表的 CRUD。

jenkins_builds：一次完整构建+测试流程的主记录（一个 build_token 对应一次修复的全部构建）。
jenkins_cicd_builds：每个 repo 的 cicd 构建明细，通过 build_token 与主表关联。
"""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional


class JenkinsBuildStore:
    """管理 jenkins_builds 和 jenkins_cicd_builds 两张表。"""

    DONE_PHASES = {
        "done_success",
        "done_cicd_failure",
        "done_test_failure",
        "done_test_aborted",
        "done_timeout",
    }

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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jenkins_builds (
                    build_token     TEXT PRIMARY KEY,
                    repos_json      TEXT NOT NULL,
                    branch          TEXT NOT NULL,
                    phase           TEXT NOT NULL DEFAULT 'cicd_queued',
                    autotest_queue_id TEXT DEFAULT '',
                    autotest_build_no INTEGER DEFAULT 0,
                    jenkins_result  TEXT DEFAULT '',
                    report_json     TEXT DEFAULT '',
                    started_at      INTEGER NOT NULL,
                    driver_owner    TEXT DEFAULT '',
                    driver_heartbeat INTEGER DEFAULT 0,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jenkins_cicd_builds (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    build_token     TEXT NOT NULL,
                    repo            TEXT NOT NULL,
                    service         TEXT NOT NULL,
                    queue_id        TEXT DEFAULT '',
                    build_no        INTEGER DEFAULT 0,
                    result          TEXT DEFAULT 'PENDING',
                    console_snippet TEXT DEFAULT '',
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cicd_token ON jenkins_cicd_builds(build_token)"
            )

    def create_build(self, repos: List[str], branch: str) -> str:
        """插入主表记录 + 每个 repo 一条 cicd_builds 记录，返回 build_token。"""
        token = uuid.uuid4().hex
        now = int(time.time())
        repos_json = json.dumps(repos, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jenkins_builds "
                "(build_token, repos_json, branch, phase, started_at, created_at, updated_at) "
                "VALUES (?, ?, ?, 'cicd_queued', ?, ?, ?)",
                (token, repos_json, branch, now, now, now),
            )
            for repo in repos:
                service = repo.split("/")[-1]
                conn.execute(
                    "INSERT INTO jenkins_cicd_builds "
                    "(build_token, repo, service, result, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'PENDING', ?, ?)",
                    (token, repo, service, now, now),
                )
        return token

    def get_build(self, build_token: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jenkins_builds WHERE build_token = ?", (build_token,)
            ).fetchone()
        return dict(row) if row else None

    def update_build(self, build_token: str, **kwargs) -> None:
        if not kwargs:
            return
        kwargs["updated_at"] = int(time.time())
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [build_token]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE jenkins_builds SET {set_clause} WHERE build_token = ?", values
            )

    def list_cicd_builds(self, build_token: str) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jenkins_cicd_builds WHERE build_token = ?", (build_token,)
            ).fetchall()
        return [dict(r) for r in rows]

    def update_cicd_build(
        self,
        build_token: str,
        repo: str,
        *,
        queue_id: str = None,
        build_no: int = None,
        result: str = None,
        console_snippet: str = None,
    ) -> None:
        kwargs = {}
        if queue_id is not None:
            kwargs["queue_id"] = queue_id
        if build_no is not None:
            kwargs["build_no"] = build_no
        if result is not None:
            kwargs["result"] = result
        if console_snippet is not None:
            kwargs["console_snippet"] = console_snippet
        if not kwargs:
            return
        kwargs["updated_at"] = int(time.time())
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [build_token, repo]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE jenkins_cicd_builds SET {set_clause} "
                f"WHERE build_token = ? AND repo = ?",
                values,
            )

    def list_non_done_builds(self) -> List[Dict]:
        """列出所有未完成的构建记录（phase 不以 done_ 开头）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jenkins_builds WHERE phase NOT LIKE 'done_%'"
            ).fetchall()
        return [dict(r) for r in rows]

    def try_acquire_driver(self, build_token: str, owner: str, stale_seconds: int = 300) -> bool:
        """尝试抢占 driver_owner。已有新鲜 owner 则返回 False，否则抢占成功返回 True。"""
        now = int(time.time())
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT driver_owner, driver_heartbeat FROM jenkins_builds WHERE build_token = ?",
                (build_token,),
            ).fetchone()
            if row is None:
                return False
            current_owner = row["driver_owner"] or ""
            heartbeat = row["driver_heartbeat"] or 0
            if current_owner and current_owner != owner and (now - heartbeat) < stale_seconds:
                return False
            conn.execute(
                "UPDATE jenkins_builds SET driver_owner = ?, driver_heartbeat = ?, updated_at = ? "
                "WHERE build_token = ?",
                (owner, now, now, build_token),
            )
        return True

    def refresh_heartbeat(self, build_token: str, owner: str) -> None:
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                "UPDATE jenkins_builds SET driver_heartbeat = ?, updated_at = ? "
                "WHERE build_token = ? AND driver_owner = ?",
                (now, now, build_token, owner),
            )

    def is_done(self, build_token: str) -> bool:
        build = self.get_build(build_token)
        if not build:
            return True
        return build["phase"].startswith("done_")
```

- [ ] **Step 4：运行测试确认通过**

```bash
python -m pytest tests/repair/test_jenkins_build_store.py -v
```

期望：5 个测试全部 PASS

- [ ] **Step 5：补充并发抢占测试**

```python
# 追加到 tests/repair/test_jenkins_build_store.py

import threading


def test_driver_acquire_exclusive(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    # 第一个进程抢占成功
    assert store.try_acquire_driver(token, owner="proc-A") is True
    # 第二个进程抢占失败（心跳新鲜）
    assert store.try_acquire_driver(token, owner="proc-B") is False
    # 同一进程重入成功
    assert store.try_acquire_driver(token, owner="proc-A") is True


def test_driver_stale_heartbeat_reacquired(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.try_acquire_driver(token, owner="proc-A")
    # 手动让心跳过期
    store.update_build(token, driver_heartbeat=int(time.time()) - 400)
    # proc-B 可以接管陈旧锁
    assert store.try_acquire_driver(token, owner="proc-B", stale_seconds=300) is True


def test_concurrent_acquire(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    results = []
    barrier = threading.Barrier(2)

    def try_acquire(name):
        barrier.wait()
        results.append(store.try_acquire_driver(token, owner=name))

    threads = [threading.Thread(target=try_acquire, args=(f"proc-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 只有一个能成功
    assert results.count(True) == 1
    assert results.count(False) == 1
```

- [ ] **Step 6：运行确认通过**

```bash
python -m pytest tests/repair/test_jenkins_build_store.py -v
```

期望：8 个测试全部 PASS

- [ ] **Step 7：commit**

```bash
git add plugins/bundled/repair/jenkins_build_store.py tests/repair/test_jenkins_build_store.py
git commit -m "feat: add JenkinsBuildStore with jenkins_builds + jenkins_cicd_builds tables"
```

---

## Task 1：repair_runs 加 repos 字段 + prompts 多服务解析

**Files:**
- Modify: `plugins/bundled/repair/store.py`
- Modify: `plugins/bundled/repair/prompts.py`
- Modify: `tests/repair/test_store.py`
- Modify: `tests/repair/test_prompts.py`

- [ ] **Step 1：写失败测试（store repos 字段）**

```python
# 追加到 tests/repair/test_store.py

def test_repos_field_persisted(store):
    from plugins.bundled.repair.store import RepairRun, Stage
    import json
    run = RepairRun(
        linear_issue_id="issue-multi",
        workspace_id="ws-1",
        stage=Stage.PENDING_REVIEW,
        repo="piaozone/base/api-auth",
        repos=json.dumps(["piaozone/base/api-auth", "piaozone/base/api-company"]),
    )
    store.upsert(run)
    loaded = store.get("issue-multi")
    assert loaded.repos == json.dumps(["piaozone/base/api-auth", "piaozone/base/api-company"])
```

- [ ] **Step 2：写失败测试（prompts 多服务解析）**

```python
# 追加到 tests/repair/test_prompts.py

def test_parse_developer_output_single_repo():
    from plugins.bundled.repair.prompts import parse_developer_output
    text = "【状态】完成\n【仓库】piaozone/base/api-auth\n【分支】fix/ENG-1\n【MR链接】\n【复现测试】FooTest.java\n【说明】修了空指针"
    result = parse_developer_output(text)
    assert result["repos"] == ["piaozone/base/api-auth"]


def test_parse_developer_output_multi_repo():
    from plugins.bundled.repair.prompts import parse_developer_output
    import json
    repos = ["piaozone/base/api-auth", "piaozone/base/api-company"]
    text = f'【状态】完成\n【仓库】{json.dumps(repos, ensure_ascii=False)}\n【分支】fix/ENG-1\n【MR链接】\n【复现测试】FooTest.java\n【说明】修了空指针'
    result = parse_developer_output(text)
    assert result["repos"] == repos
```

- [ ] **Step 3：运行确认失败**

```bash
python -m pytest tests/repair/test_store.py::test_repos_field_persisted tests/repair/test_prompts.py::test_parse_developer_output_single_repo tests/repair/test_prompts.py::test_parse_developer_output_multi_repo -v
```

- [ ] **Step 4：更新 RepairRun + repair_runs 表**

在 `plugins/bundled/repair/store.py` 的 `RepairRun` dataclass 加字段：

```python
# 在 last_report: str = "" 后面加
repos: str = ""  # JSON 数组，如 '["piaozone/base/api-auth"]'
```

在 `_init_db` 的 CREATE TABLE 语句加列（`last_report TEXT DEFAULT ''` 后面）：

```sql
repos TEXT DEFAULT '',
```

- [ ] **Step 5：更新 parse_developer_output**

在 `plugins/bundled/repair/prompts.py` 的 `parse_developer_output` 函数，把 `"repo"` 字段改为 `"repos"`（返回 `list[str]`）：

```python
def parse_developer_output(text: str) -> Dict:
    repo_raw = _extract(r"【仓库】\s*(\S+)", text)
    # 兼容单值和 JSON 数组
    if repo_raw.startswith("["):
        try:
            repos = json.loads(repo_raw)
        except Exception:
            repos = [repo_raw] if repo_raw else []
    else:
        repos = [repo_raw] if repo_raw else []

    return {
        "status": _parse_dev_status(text),
        "repos": repos,
        "repo": repos[0] if repos else "",   # 向后兼容，取第一个
        "branch": _extract(r"【分支】\s*(\S+)", text),
        "mr_url": _extract(r"【MR链接】\s*(\S+)", text),
        "test_path": _extract(r"【复现测试】\s*(\S+)", text),
        "summary": _extract(r"【说明】\s*([^\n]+)", text),
    }
```

在文件顶部 `import` 区加 `import json`（若尚未有）。

- [ ] **Step 6：运行测试确认通过**

```bash
python -m pytest tests/repair/test_store.py tests/repair/test_prompts.py -v
```

期望：全部 PASS（含原有测试）

- [ ] **Step 7：commit**

```bash
git add plugins/bundled/repair/store.py plugins/bundled/repair/prompts.py \
        tests/repair/test_store.py tests/repair/test_prompts.py
git commit -m "feat: add repos JSON field to RepairRun; parse_developer_output returns repos list"
```

---

## Task 2：JenkinsClient 真实实现（httpx + 自驱动状态机）

**Files:**
- Modify: `plugins/bundled/repair/jenkins_client.py`（重写）
- Modify: `tests/repair/test_jenkins_client.py`（重写）

- [ ] **Step 1：写失败测试（trigger_build）**

```python
# tests/repair/test_jenkins_client.py  — 完整重写
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _make_client(tmp_path, mock_ready=False):
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient
    store = JenkinsBuildStore(str(tmp_path / "jenkins.db"))
    client = JenkinsClient(
        base_url="http://jenkins:8080",
        user="u",
        api_token="t",
        cicd_job="cicd-pipeline",
        cicd_token="tok1",
        autotest_job="at-automated-test",
        autotest_token="tok2",
        build_store=store,
    )
    return client, store


@pytest.mark.asyncio
async def test_trigger_build_returns_token_and_creates_rows(tmp_path):
    client, store = _make_client(tmp_path)

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/42/"}
        return resp

    with patch.object(client._http, "post", side_effect=fake_post):
        token = await client.trigger_build(
            repos=["piaozone/base/api-auth"], branch="fix/ENG-1"
        )

    assert token
    build = store.get_build(token)
    assert build["phase"] == "cicd_queued"
    rows = store.list_cicd_builds(token)
    assert rows[0]["service"] == "api-auth"
    assert rows[0]["queue_id"] == "42"
```

- [ ] **Step 2：运行确认失败**

```bash
python -m pytest tests/repair/test_jenkins_client.py::test_trigger_build_returns_token_and_creates_rows -v
```

- [ ] **Step 3：实现 JenkinsClient 骨架 + trigger_build**

```python
# plugins/bundled/repair/jenkins_client.py
"""Jenkins 客户端 —— 真实 httpx 实现 + 自驱动两任务状态机。

两个公共方法（coordinator 接口不变）：
  trigger_build(repos, branch) -> build_token   异步，立即返回，只落库
  get_report(build_token) -> dict|None          同步，只读库

后台驱动由 start_driver(build_token) 拉起（asyncio.create_task），
由 plugin.on_start / poller 扫表统一调用，不在 trigger_build 内直接启动。
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

import httpx

from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore

logger = logging.getLogger(__name__)


class JenkinsClient:
    def __init__(
        self,
        base_url: str,
        user: str,
        api_token: str,
        cicd_job: str,
        cicd_token: str,
        autotest_job: str,
        autotest_token: str,
        build_store: JenkinsBuildStore,
        deploy: bool = True,
        autotest_run_mode: str = "smoke",
        autotest_threads: int = 4,
        build_timeout_seconds: int = 86400,
        cicd_poll_seconds: int = 15,
        autotest_poll_seconds: int = 30,
        queue_poll_seconds: int = 5,
    ):
        self._base = base_url.rstrip("/")
        self._auth = (user, api_token)
        self._cicd_job = cicd_job
        self._cicd_token = cicd_token
        self._autotest_job = autotest_job
        self._autotest_token = autotest_token
        self._store = build_store
        self._deploy = deploy
        self._run_mode = autotest_run_mode
        self._threads = autotest_threads
        self._timeout_s = build_timeout_seconds
        self._cicd_poll = cicd_poll_seconds
        self._autotest_poll = autotest_poll_seconds
        self._queue_poll = queue_poll_seconds
        self._http = httpx.AsyncClient(auth=self._auth, timeout=30)
        self._owner = f"pid-{os.getpid()}"

    async def trigger_build(self, repos: List[str], branch: str) -> str:
        """并行触发各 repo 的 cicd 构建，落库，返回 build_token。不启动驱动。"""
        token = self._store.create_build(repos=repos, branch=branch)
        tasks = [self._trigger_cicd_one(token, repo, branch) for repo in repos]
        await asyncio.gather(*tasks, return_exceptions=True)
        return token

    async def _trigger_cicd_one(self, build_token: str, repo: str, branch: str) -> None:
        service = repo.split("/")[-1]
        url = f"{self._base}/job/{self._cicd_job}/buildWithParameters"
        params = {
            "token": self._cicd_token,
            "SERVICE": service,
            "BRANCH": branch,
            "DEPLOY": str(self._deploy).lower(),
        }
        try:
            resp = await self._http.post(url, params=params)
            if resp.status_code != 201:
                raise RuntimeError(f"cicd trigger failed: {resp.status_code}")
            location = resp.headers.get("Location", "")
            m = re.search(r"/queue/item/(\d+)/", location)
            if not m:
                raise RuntimeError(f"cannot parse queue id from: {location}")
            queue_id = m.group(1)
            self._store.update_cicd_build(build_token, repo, queue_id=queue_id)
        except Exception as exc:
            logger.error("[Jenkins] trigger cicd failed repo=%s: %s", repo, exc)
            self._store.update_cicd_build(build_token, repo, result="FAILURE",
                                           console_snippet=str(exc))
            # 如果触发就失败，整体短路
            rows = self._store.list_cicd_builds(build_token)
            if all(r["result"] in ("FAILURE", "ABORTED") or not r["queue_id"] for r in rows):
                self._store.update_build(
                    build_token,
                    phase="done_cicd_failure",
                    report_json=f"[构建失败] 触发 cicd 失败: {exc}",
                )

    def get_report(self, build_token: str) -> Optional[Dict]:
        """只读库，phase 以 done_ 开头则按 phase 组装报告字典，否则返回 None。"""
        build = self._store.get_build(build_token)
        if not build:
            return None
        phase = build["phase"]
        if not phase.startswith("done_"):
            return None
        report_json = build.get("report_json", "")
        if phase == "done_success":
            return {"status": "success", "summary": report_json, "failures": []}
        elif phase == "done_cicd_failure":
            summary = f"[构建失败] {report_json}" if not report_json.startswith("[构建失败]") else report_json
            return {"status": "failure", "summary": summary, "failures": []}
        elif phase == "done_test_failure":
            return {"status": "failure", "summary": report_json, "failures": []}
        elif phase == "done_test_aborted":
            summary = f"[测试任务未正常完成] {report_json}"
            return {"status": "failure", "summary": summary, "failures": []}
        elif phase == "done_timeout":
            return {"status": "timeout", "summary": report_json or "构建+测试超过配置时限未完成，判定超时", "failures": []}
        return {"status": "failure", "summary": report_json, "failures": []}
```

- [ ] **Step 4：运行测试确认通过**

```bash
python -m pytest tests/repair/test_jenkins_client.py::test_trigger_build_returns_token_and_creates_rows -v
```

- [ ] **Step 5：写 _advance 单步推进测试**

```python
# 追加到 tests/repair/test_jenkins_client.py

@pytest.mark.asyncio
async def test_advance_cicd_queued_to_building(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", queue_id="42")

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"executable": {"number": 100}}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    rows = store.list_cicd_builds(token)
    assert rows[0]["build_no"] == 100
    build = store.get_build(token)
    assert build["phase"] == "cicd_building"


@pytest.mark.asyncio
async def test_advance_cicd_building_success_triggers_autotest(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="cicd_building")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=100, result="PENDING")

    call_count = {"n": 0}

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": False, "result": "SUCCESS"}
        return resp

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/99/"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get), \
         patch.object(client._http, "post", side_effect=fake_post):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "autotest_queued"
    assert build["autotest_queue_id"] == "99"


@pytest.mark.asyncio
async def test_advance_cicd_building_failure_shortcircuits(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="cicd_building")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=100, result="PENDING")

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "consoleText" in url:
            resp.text = "BUILD FAILED: compilation error"
            return resp
        resp.json.return_value = {"building": False, "result": "FAILURE"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_cicd_failure"
    report = client.get_report(token)
    assert report["status"] == "failure"
    assert "[构建失败]" in report["summary"]


@pytest.mark.asyncio
async def test_advance_autotest_building_success(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": False, "result": "SUCCESS",
                                   "testReport": {"passCount": 10, "failCount": 0}}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"
    report = client.get_report(token)
    assert report["status"] == "success"


@pytest.mark.asyncio
async def test_advance_autotest_aborted(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": False, "result": "ABORTED"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_test_aborted"
    report = client.get_report(token)
    assert report["status"] == "failure"
    assert "[测试任务未正常完成]" in report["summary"]


@pytest.mark.asyncio
async def test_advance_timeout(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    # 让 started_at 超时
    store.update_build(token, started_at=int(time.time()) - 86401)

    await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_timeout"
    report = client.get_report(token)
    assert report["status"] == "timeout"


@pytest.mark.asyncio
async def test_advance_request_exception_does_not_change_phase(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", queue_id="42")

    async def fake_get(url, **kwargs):
        raise httpx.ConnectError("network down")

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "cicd_queued"  # 不变
```

- [ ] **Step 6：运行确认失败（_advance 未实现）**

```bash
python -m pytest tests/repair/test_jenkins_client.py -v 2>&1 | tail -20
```

- [ ] **Step 7：实现 _advance**

在 `JenkinsClient` 类末尾追加：

```python
    async def _advance(self, build_token: str) -> None:
        """非阻塞单步推进。整轮包 try/except，单次失败不改 phase。"""
        build = self._store.get_build(build_token)
        if not build or build["phase"].startswith("done_"):
            return

        # 超时检查（每轮最先判）
        if int(time.time()) - build["started_at"] > self._timeout_s:
            self._store.update_build(
                build_token,
                phase="done_timeout",
                report_json="构建+测试超过配置时限未完成，判定超时",
            )
            logger.warning("[Jenkins] build timeout: %s", build_token)
            return

        phase = build["phase"]
        try:
            if phase == "cicd_queued":
                await self._advance_cicd_queued(build_token)
            elif phase == "cicd_building":
                await self._advance_cicd_building(build_token)
            elif phase == "autotest_queued":
                await self._advance_autotest_queued(build_token)
            elif phase == "autotest_building":
                await self._advance_autotest_building(build_token)
        except Exception as exc:
            logger.warning("[Jenkins] _advance error phase=%s token=%s: %s", phase, build_token, exc)

    async def _advance_cicd_queued(self, build_token: str) -> None:
        rows = self._store.list_cicd_builds(build_token)
        pending_rows = [r for r in rows if r["build_no"] == 0 and r["queue_id"]]
        for row in pending_rows:
            url = f"{self._base}/queue/item/{row['queue_id']}/api/json"
            resp = await self._http.get(url)
            data = resp.json()
            executable = data.get("executable")
            if executable and executable.get("number"):
                self._store.update_cicd_build(
                    build_token, row["repo"], build_no=executable["number"]
                )
        # 重读检查全部有构建号
        rows = self._store.list_cicd_builds(build_token)
        if all(r["build_no"] > 0 for r in rows):
            self._store.update_build(build_token, phase="cicd_building")

    async def _advance_cicd_building(self, build_token: str) -> None:
        rows = self._store.list_cicd_builds(build_token)
        for row in rows:
            if row["result"] != "PENDING":
                continue
            url = f"{self._base}/job/{self._cicd_job}/{row['build_no']}/api/json"
            resp = await self._http.get(url)
            data = resp.json()
            if data.get("building"):
                continue
            result = data.get("result", "ABORTED")
            self._store.update_cicd_build(build_token, row["repo"], result=result)
            if result in ("FAILURE", "ABORTED"):
                # 拉 consoleText 片段
                snippet = await self._get_console_snippet(self._cicd_job, row["build_no"])
                self._store.update_cicd_build(build_token, row["repo"], console_snippet=snippet)

        rows = self._store.list_cicd_builds(build_token)
        failed = [r for r in rows if r["result"] in ("FAILURE", "ABORTED")]
        if failed:
            summaries = [f"{r['repo']}: {r['console_snippet'] or r['result']}" for r in failed]
            self._store.update_build(
                build_token,
                phase="done_cicd_failure",
                report_json="[构建失败]\n" + "\n".join(summaries),
            )
            return
        if all(r["result"] == "SUCCESS" for r in rows):
            await self._trigger_autotest(build_token)

    async def _trigger_autotest(self, build_token: str) -> None:
        url = f"{self._base}/job/{self._autotest_job}/buildWithParameters"
        params = {
            "token": self._autotest_token,
            "RUN_MODE": self._run_mode,
            "THREADS": str(self._threads),
        }
        resp = await self._http.post(url, params=params)
        if resp.status_code != 201:
            raise RuntimeError(f"autotest trigger failed: {resp.status_code}")
        location = resp.headers.get("Location", "")
        m = re.search(r"/queue/item/(\d+)/", location)
        if not m:
            raise RuntimeError(f"cannot parse autotest queue id: {location}")
        self._store.update_build(
            build_token,
            phase="autotest_queued",
            autotest_queue_id=m.group(1),
        )

    async def _advance_autotest_queued(self, build_token: str) -> None:
        build = self._store.get_build(build_token)
        queue_id = build.get("autotest_queue_id", "")
        if not queue_id:
            return
        url = f"{self._base}/queue/item/{queue_id}/api/json"
        resp = await self._http.get(url)
        data = resp.json()
        executable = data.get("executable")
        if executable and executable.get("number"):
            self._store.update_build(
                build_token,
                phase="autotest_building",
                autotest_build_no=executable["number"],
            )

    async def _advance_autotest_building(self, build_token: str) -> None:
        build = self._store.get_build(build_token)
        build_no = build.get("autotest_build_no", 0)
        if not build_no:
            return
        url = f"{self._base}/job/{self._autotest_job}/{build_no}/api/json"
        resp = await self._http.get(url)
        data = resp.json()
        if data.get("building"):
            return
        result = data.get("result", "ABORTED")
        self._store.update_build(build_token, jenkins_result=result)
        if result == "SUCCESS":
            test_report = data.get("testReport", {})
            pass_count = test_report.get("passCount", 0)
            fail_count = test_report.get("failCount", 0)
            self._store.update_build(
                build_token,
                phase="done_success",
                report_json=f"{pass_count} passed, {fail_count} failed",
            )
        elif result == "FAILURE":
            test_report = data.get("testReport", {})
            fail_count = test_report.get("failCount", 0)
            self._store.update_build(
                build_token,
                phase="done_test_failure",
                report_json=f"测试失败：{fail_count} 个用例未通过",
            )
        else:
            self._store.update_build(
                build_token,
                phase="done_test_aborted",
                report_json=f"autotest 未正常完成，Jenkins result={result}",
            )

    async def _get_console_snippet(self, job: str, build_no: int, max_lines: int = 20) -> str:
        """拉构建日志末尾片段（失败时辅助归因）。失败静默返回空串。"""
        try:
            url = f"{self._base}/job/{job}/{build_no}/consoleText"
            resp = await self._http.get(url)
            lines = resp.text.strip().splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception:
            return ""

    async def start_driver(self, build_token: str) -> None:
        """启动 per-build 后台驱动（asyncio.create_task 包装）。"""
        if not self._store.try_acquire_driver(build_token, self._owner):
            return  # 已有其他驱动在跑
        asyncio.create_task(self._run_driver(build_token))

    async def _run_driver(self, build_token: str) -> None:
        """驱动主循环：推进 phase 直到 done，按 phase 选轮询间隔。"""
        logger.info("[Jenkins] driver started: %s", build_token)
        while True:
            build = self._store.get_build(build_token)
            if not build or build["phase"].startswith("done_"):
                break
            await self._advance(build_token)
            # 重读 phase 选 sleep 间隔
            build = self._store.get_build(build_token)
            if not build or build["phase"].startswith("done_"):
                break
            phase = build["phase"]
            if "queued" in phase:
                interval = self._queue_poll
            elif "autotest" in phase:
                interval = self._autotest_poll
            else:
                interval = self._cicd_poll
            self._store.refresh_heartbeat(build_token, self._owner)
            await asyncio.sleep(interval)
        logger.info("[Jenkins] driver done: %s", build_token)

    async def resume_pending_drivers(self) -> None:
        """扫表，对无驱动或驱动陈旧的非 done 记录拉起驱动。on_start / poller 调用。"""
        for build in self._store.list_non_done_builds():
            token = build["build_token"]
            await self.start_driver(token)

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 8：运行全部测试确认通过**

```bash
python -m pytest tests/repair/test_jenkins_client.py -v
```

期望：全部 PASS

- [ ] **Step 9：commit**

```bash
git add plugins/bundled/repair/jenkins_client.py tests/repair/test_jenkins_client.py
git commit -m "feat: implement real JenkinsClient with two-job state machine and async driver"
```

---

## Task 3：coordinator 超时旁路 + trigger_build 改传 repos 列表

**Files:**
- Modify: `plugins/bundled/repair/coordinator.py`
- Modify: `tests/repair/conftest.py`
- Modify: `tests/repair/test_coordinator.py`

- [ ] **Step 1：更新 FakeJenkins 支持 timeout 模式和多 repo**

```python
# 在 tests/repair/conftest.py 替换 FakeJenkins

class FakeJenkins:
    def __init__(self, ready=True, timeout=False):
        self.ready = ready
        self.timeout = timeout
        self.triggered = []  # list of (repos, branch)

    def trigger_build(self, repos, branch):
        self.triggered.append((repos, branch))
        return "build-xyz"

    def get_report(self, build_id):
        if not self.ready:
            return None
        if self.timeout:
            return {"status": "timeout", "summary": "构建+测试超过配置时限未完成，判定超时", "failures": []}
        return {"status": "success", "summary": "3 passed", "failures": []}
```

- [ ] **Step 2：写超时旁路失败测试**

```python
# 追加到 tests/repair/test_coordinator.py

@pytest.mark.asyncio
async def test_analyze_report_timeout_rejects_without_analyzer(tmp_path):
    from plugins.bundled.repair.coordinator import RepairCoordinator
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    from tests.repair.conftest import FakeAgentService, FakeJenkins, FakeLinearClient

    store = RepairStore(str(tmp_path / "r.db"))
    store.upsert(RepairRun(
        linear_issue_id="issue-t",
        linear_identifier="ENG-T",
        workspace_id="ws-1",
        stage=Stage.BUILDING,
        repo="ai-agent/foo",
        repos='["ai-agent/foo"]',
        root_cause="空指针",
        repair_plan="判空",
        jenkins_build_id="build-xyz",
    ))

    fake_linear = FakeLinearClient()
    # FakeAgentService 脚本为空——超时旁路不应调用 analyzer
    agent = FakeAgentService([])
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=FakeJenkins(ready=True, timeout=True),
        linear_client_factory=lambda ws: fake_linear,
    )

    await coord.analyze_report("issue-t")

    run = store.get("issue-t")
    assert run.stage == Stage.REJECTED
    # analyzer 没有被调用（脚本为空但没有抛异常）
    assert len(agent.calls) == 0
    # Linear 有超时通知评论
    bodies = [b for _, b in fake_linear.comments]
    assert any("超时" in b for b in bodies)
    # 锁已释放（repo_locks 表应为空）
    assert store.list_locks() == []
```

- [ ] **Step 3：运行确认失败**

```bash
python -m pytest tests/repair/test_coordinator.py::test_analyze_report_timeout_rejects_without_analyzer -v
```

- [ ] **Step 4：更新 coordinator.py**

在 `coordinator.py` 的 `analyze_report` 方法里，在 `report_summary = ...` 之前加超时判断，并更新 `trigger_build` 调用处：

```python
# analyze_report 方法开头（report = self.jenkins.get_report(...) 之后）加：
if report.get("status") == "timeout":
    client = self._linear(run.workspace_id)
    self.store.update(linear_issue_id, stage=Stage.REJECTED)
    self.store.release_repos(linear_issue_id)
    await self._set_issue_linear_state(client, linear_issue_id, "canceled")
    await client.create_comment(
        linear_issue_id,
        "⚠️ 构建+测试超时（超过配置时限未完成），已转人工。\n"
        "请检查 Jenkins/部署环境后，在本单评论「重跑」重新触发。",
    )
    logger.warning("[Repair] build timeout, rejected: %s", linear_issue_id)
    return
```

在 `_develop_and_build` 方法中，把 `trigger_build` 调用改为：

```python
import json as _json
repos = _json.loads(run.repos) if run.repos else ([run.repo] if run.repo else [])
build_id = self.jenkins.trigger_build(repos=repos, branch=new_branch)
```

同理，`_handle_code_error` 中的 `trigger_build` 调用改为：

```python
repos = _json.loads(run.repos) if run.repos else ([run.repo] if run.repo else [])
build_id = self.jenkins.trigger_build(repos=repos, branch=run.branch)
```

在文件顶部加 `import json as _json`（若尚未有）。

同时更新 `RepairRun` 存储：在 `_develop_and_build` 里 `store.update` 时补充 `repos` 字段：

```python
resolved_repos = parsed["repos"] or ([resolved_repo] if resolved_repo else [])
self.store.update(
    linear_issue_id,
    stage=Stage.BUILDING,
    repo=resolved_repo,
    repos=_json.dumps(resolved_repos, ensure_ascii=False),
    branch=new_branch,
    develop_session_id=session_id_for_store or "",
    jenkins_build_id=build_id,
)
```

- [ ] **Step 5：运行全部 coordinator 测试确认通过**

```bash
python -m pytest tests/repair/test_coordinator.py tests/repair/test_integration.py -v
```

期望：全部 PASS（含原有测试）

- [ ] **Step 6：commit**

```bash
git add plugins/bundled/repair/coordinator.py tests/repair/conftest.py tests/repair/test_coordinator.py
git commit -m "feat: coordinator timeout bypass + trigger_build accepts repos list"
```

---

## Task 4：cli.py 加 retrigger-build 子命令

**Files:**
- Modify: `plugins/bundled/repair/cli.py`
- Modify: `tests/repair/test_cli.py`

- [ ] **Step 1：写失败测试**

```python
# 追加到 tests/repair/test_cli.py

def test_retrigger_build_rejects_wrong_stage(tmp_path, monkeypatch):
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    db = str(tmp_path / "r.db")
    store = RepairStore(db)
    store.upsert(RepairRun(
        linear_issue_id="issue-1",
        linear_identifier="ENG-1",
        workspace_id="ws-1",
        stage=Stage.DEVELOPING,   # 不允许重跑
        repo="ai-agent/foo",
        repos='["ai-agent/foo"]',
        branch="fix/ENG-1",
    ))
    monkeypatch.setenv("REPAIR_DB_PATH", db)

    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "plugins/bundled/repair/cli.py", "retrigger-build", "--issue", "issue-1"],
        capture_output=True, text=True,
    )
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "不可重跑" in output.get("error", "") or "stage" in output.get("error", "")


def test_retrigger_build_rejects_empty_branch(tmp_path, monkeypatch):
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    db = str(tmp_path / "r.db")
    store = RepairStore(db)
    store.upsert(RepairRun(
        linear_issue_id="issue-2",
        linear_identifier="ENG-2",
        workspace_id="ws-1",
        stage=Stage.REJECTED,
        repo="ai-agent/foo",
        repos='["ai-agent/foo"]',
        branch="",  # 无分支
    ))
    monkeypatch.setenv("REPAIR_DB_PATH", db)

    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "plugins/bundled/repair/cli.py", "retrigger-build", "--issue", "issue-2"],
        capture_output=True, text=True,
    )
    output = json.loads(result.stdout)
    assert output["ok"] is False


def test_retrigger_build_ok(tmp_path, monkeypatch):
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    db = str(tmp_path / "r.db")
    store = RepairStore(db)
    store.upsert(RepairRun(
        linear_issue_id="issue-3",
        linear_identifier="ENG-3",
        workspace_id="ws-1",
        stage=Stage.REJECTED,
        repo="ai-agent/foo",
        repos='["ai-agent/foo"]',
        branch="fix/ENG-3",
    ))
    jenkins_db = str(tmp_path / "jenkins.db")
    monkeypatch.setenv("REPAIR_DB_PATH", db)
    monkeypatch.setenv("JENKINS_BUILDS_DB_PATH", jenkins_db)
    monkeypatch.setenv("JENKINS_BASE_URL", "http://mock-jenkins:8080")
    monkeypatch.setenv("JENKINS_USER", "u")
    monkeypatch.setenv("JENKINS_API_TOKEN", "t")
    monkeypatch.setenv("JENKINS_CICD_JOB", "cicd-pipeline")
    monkeypatch.setenv("JENKINS_CICD_TOKEN", "tok1")
    monkeypatch.setenv("JENKINS_AUTOTEST_JOB", "at-automated-test")
    monkeypatch.setenv("JENKINS_AUTOTEST_TOKEN", "tok2")

    # mock httpx so no real request is made
    import httpx
    from unittest.mock import AsyncMock, MagicMock, patch

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://mock-jenkins:8080/queue/item/55/"}
        return resp

    import subprocess, sys
    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        result = subprocess.run(
            [sys.executable, "plugins/bundled/repair/cli.py", "retrigger-build", "--issue", "issue-3"],
            capture_output=True, text=True,
            env={**__import__("os").environ,
                 "REPAIR_DB_PATH": db,
                 "JENKINS_BUILDS_DB_PATH": jenkins_db,
                 "JENKINS_BASE_URL": "http://mock-jenkins:8080",
                 "JENKINS_USER": "u", "JENKINS_API_TOKEN": "t",
                 "JENKINS_CICD_JOB": "cicd-pipeline", "JENKINS_CICD_TOKEN": "tok1",
                 "JENKINS_AUTOTEST_JOB": "at-automated-test", "JENKINS_AUTOTEST_TOKEN": "tok2"},
        )
    # store 应已更新为 BUILDING
    run = store.get("issue-3")
    assert run.stage == Stage.BUILDING
```

- [ ] **Step 2：运行确认失败**

```bash
python -m pytest tests/repair/test_cli.py::test_retrigger_build_rejects_wrong_stage tests/repair/test_cli.py::test_retrigger_build_rejects_empty_branch -v
```

- [ ] **Step 3：实现 retrigger-build 子命令**

在 `cli.py` 的 `main()` 函数的 `sub` 解析器区追加，并加 `retrigger_build_cmd` 函数：

```python
# 在 acquire_lock_cmd 函数后追加：

def _make_jenkins_client():
    """构造真实 JenkinsClient（从 env 读配置）。"""
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient

    builds_db = os.getenv("JENKINS_BUILDS_DB_PATH", "data/repair/jenkins_builds.db")
    full = str(_ROOT / builds_db) if not os.path.isabs(builds_db) else builds_db
    build_store = JenkinsBuildStore(full)

    return JenkinsClient(
        base_url=os.getenv("JENKINS_BASE_URL", ""),
        user=os.getenv("JENKINS_USER", ""),
        api_token=os.getenv("JENKINS_API_TOKEN", ""),
        cicd_job=os.getenv("JENKINS_CICD_JOB", "cicd-pipeline"),
        cicd_token=os.getenv("JENKINS_CICD_TOKEN", ""),
        autotest_job=os.getenv("JENKINS_AUTOTEST_JOB", "at-automated-test"),
        autotest_token=os.getenv("JENKINS_AUTOTEST_TOKEN", ""),
        build_store=build_store,
    )


async def retrigger_build_cmd(issue_id: str) -> None:
    """重新触发构建+测试（门禁：stage∈{BUILDING,REJECTED} 且 branch 非空）。"""
    import json
    from plugins.bundled.repair.store import Stage

    store = _make_store()
    run = store.get(issue_id)
    if run is None:
        print(json.dumps({"ok": False, "error": f"找不到修复单 {issue_id}"}))
        return
    if run.stage not in (Stage.BUILDING, Stage.REJECTED):
        print(json.dumps({"ok": False, "error": f"不可重跑：当前 stage={run.stage}，需为 building 或 rejected"}))
        return
    if not run.branch:
        print(json.dumps({"ok": False, "error": "不可重跑：分支为空，开发尚未完成"}))
        return

    # 重申 repo 锁
    repos = json.loads(run.repos) if run.repos else ([run.repo] if run.repo else [])
    ok, blocker = store.acquire_repos(issue_id, run.linear_identifier, repos)
    if not ok:
        print(json.dumps({"ok": False, "error": f"涉及的服务正被 {blocker} 占用，请稍后重试"}))
        return

    jenkins = _make_jenkins_client()
    try:
        build_id = await jenkins.trigger_build(repos=repos, branch=run.branch)
        store.update(issue_id, stage=Stage.BUILDING, jenkins_build_id=build_id)
        print(json.dumps({"ok": True, "build_id": build_id, "branch": run.branch}))
    except Exception as e:
        store.release_repos(issue_id)
        print(json.dumps({"ok": False, "error": str(e)}))
    finally:
        await jenkins.aclose()
```

在 `main()` 的 `sub` 区加子命令解析：

```python
    p_retrigger = sub.add_parser("retrigger-build", help="重新触发构建+测试")
    p_retrigger.add_argument("--issue", required=True, help="Linear issue UUID")
```

在 `main()` 的分支判断区追加：

```python
    elif args.cmd == "retrigger-build":
        try:
            asyncio.run(retrigger_build_cmd(args.issue))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
```

- [ ] **Step 4：运行测试确认通过**

```bash
python -m pytest tests/repair/test_cli.py::test_retrigger_build_rejects_wrong_stage tests/repair/test_cli.py::test_retrigger_build_rejects_empty_branch -v
```

- [ ] **Step 5：commit**

```bash
git add plugins/bundled/repair/cli.py tests/repair/test_cli.py
git commit -m "feat: add retrigger-build CLI subcommand with stage/branch gate"
```

---

## Task 5：plugin.py 构造真实 JenkinsClient + on_start 扫表

**Files:**
- Modify: `plugins/bundled/repair/plugin.py`
- Modify: `plugins/config.json`
- Modify: `.env.example`

- [ ] **Step 1：更新 plugin.py**

在 `plugin.py` 的 `RepairChannelPlugin.__init__` 里，把 `JenkinsClient(mock_ready=True)` 替换为构造真实 client：

```python
# 替换 jenkins = JenkinsClient(mock_ready=True) 为：
from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore

jenkins_builds_db = _resolve(
    self.config.get("jenkins_builds_db_path", "data/repair/jenkins_builds.db")
)
build_store = JenkinsBuildStore(jenkins_builds_db)

jenkins = JenkinsClient(
    base_url=os.getenv("JENKINS_BASE_URL", ""),
    user=os.getenv("JENKINS_USER", ""),
    api_token=os.getenv("JENKINS_API_TOKEN", ""),
    cicd_job=os.getenv("JENKINS_CICD_JOB", "cicd-pipeline"),
    cicd_token=os.getenv("JENKINS_CICD_TOKEN", ""),
    autotest_job=os.getenv("JENKINS_AUTOTEST_JOB", "at-automated-test"),
    autotest_token=os.getenv("JENKINS_AUTOTEST_TOKEN", ""),
    build_store=build_store,
    deploy=self.config.get("jenkins_deploy", True),
    autotest_run_mode=self.config.get("autotest_run_mode", "smoke"),
    autotest_threads=int(self.config.get("autotest_threads", 4)),
    build_timeout_seconds=int(self.config.get("build_timeout_seconds", 86400)),
    cicd_poll_seconds=int(self.config.get("cicd_poll_seconds", 15)),
    autotest_poll_seconds=int(self.config.get("autotest_poll_seconds", 30)),
    queue_poll_seconds=int(self.config.get("queue_poll_seconds", 5)),
)
self.jenkins = jenkins
```

在 `on_start` 方法里，scheduler 启动后追加扫表拉起驱动：

```python
# scheduler.start() 之后加：
await self.jenkins.resume_pending_drivers()
logger.info("[Repair] resumed pending Jenkins drivers on start")
```

在 `on_stop` 方法里追加关闭 httpx client：

```python
# scheduler shutdown 后加：
await self.jenkins.aclose()
```

- [ ] **Step 2：更新 config.json**

把 `plugins/config.json` 的 `repair` 配置段更新为：

```json
"repair": {
    "repair_db_path": "data/repair/repair_runs.db",
    "jenkins_builds_db_path": "data/repair/jenkins_builds.db",
    "poll_interval_seconds": 60,
    "fix_retry_limit": 3,
    "rediagnose_limit": 2,
    "jenkins_deploy": true,
    "autotest_run_mode": "smoke",
    "autotest_threads": 4,
    "build_timeout_seconds": 86400,
    "cicd_poll_seconds": 15,
    "autotest_poll_seconds": 30,
    "queue_poll_seconds": 5
}
```

- [ ] **Step 3：更新 .env.example**

在 `.env.example` 末尾追加：

```bash
# Jenkins 构建+测试集成
JENKINS_BASE_URL=http://jump-test.piaozone.com:8080
JENKINS_USER=chuang_li
JENKINS_API_TOKEN=<basic auth 密码/token>
JENKINS_CICD_JOB=cicd-pipeline
JENKINS_CICD_TOKEN=<cicd 触发 token，见 docs/cicd.md>
JENKINS_AUTOTEST_JOB=at-automated-test
JENKINS_AUTOTEST_TOKEN=<autotest 触发 token，见 docs/autotest.md>
JENKINS_BUILDS_DB_PATH=data/repair/jenkins_builds.db
```

- [ ] **Step 4：运行现有插件测试确认无回归**

```bash
python -m pytest tests/repair/test_plugin.py -v
```

- [ ] **Step 5：commit**

```bash
git add plugins/bundled/repair/plugin.py plugins/config.json .env.example
git commit -m "feat: plugin.py constructs real JenkinsClient and resumes drivers on start"
```

---

## Task 6：集成测试补超时旁路 + bug-fix-developer skill 更新

**Files:**
- Modify: `tests/repair/test_integration.py`
- Modify: `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md`

- [ ] **Step 1：补集成测试超时旁路**

```python
# 追加到 tests/repair/test_integration.py

@pytest.mark.integration
async def test_timeout_rejects_without_retry(tmp_path):
    from plugins.bundled.repair.coordinator import RepairCoordinator
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    from tests.repair.conftest import FakeAgentService, FakeJenkins, FakeLinearClient
    import json

    store = RepairStore(str(tmp_path / "r.db"))
    store.upsert(RepairRun(
        linear_issue_id="issue-timeout",
        linear_identifier="ENG-TM",
        workspace_id="ws-1",
        stage=Stage.BUILDING,
        repo="ai-agent/foo",
        repos=json.dumps(["ai-agent/foo"]),
        root_cause="空指针",
        repair_plan="判空",
        jenkins_build_id="build-timeout",
    ))

    fake_linear = FakeLinearClient()
    agent = FakeAgentService([])  # 不应被调用
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=FakeJenkins(ready=True, timeout=True),
        linear_client_factory=lambda ws: fake_linear,
    )

    await coord.poll_building_runs()

    run = store.get("issue-timeout")
    assert run.stage == Stage.REJECTED
    assert len(agent.calls) == 0  # analyzer 未被调用
    assert run.fix_retry_count == 0  # 未计重试
    bodies = [b for _, b in fake_linear.comments]
    assert any("超时" in b for b in bodies)
```

- [ ] **Step 2：运行集成测试确认通过**

```bash
python -m pytest tests/repair/test_integration.py -v
```

- [ ] **Step 3：更新 bug-fix-developer skill**

在 `agent_cwd/.claude/skills/bug-fix-developer/SKILL.md` 的「输出格式」章节，`【仓库】` 说明改为：

```markdown
【仓库】<实际使用的完整 project_id；多服务时输出 JSON 数组，如 ["piaozone/base/api-auth","piaozone/base/api-company"]>
```

在文件末尾（或 Step 7 之后）追加重跑说明章节：

```markdown
## 构建+测试重跑

若用户在 Linear 评论要求重跑构建测试（如「帮我重跑」「重新构建」「retry」），调：

```bash
"$AGENTS_ROOT/.venv/bin/python" plugins/bundled/repair/cli.py retrigger-build \
  --issue "<linear_issue_id>"
```

解析 stdout JSON：
- `{"ok": true, "build_id": "...", "branch": "..."}` → 回复用户「已重新触发构建+测试，等待报告」
- `{"ok": false, "error": "..."}` → 回复用户错误原因
```

- [ ] **Step 4：运行全量测试确认无回归**

```bash
python -m pytest tests/repair/ -v --tb=short 2>&1 | tail -30
```

期望：全部通过（仅预存的 test_cli create_issue mock 那条已知失败，与本期无关）

- [ ] **Step 5：commit**

```bash
git add tests/repair/test_integration.py \
        agent_cwd/.claude/skills/bug-fix-developer/SKILL.md
git commit -m "feat: integration test for timeout bypass; update bug-fix-developer skill with multi-repo and retrigger docs"
```

---

## 自检

### Spec 覆盖检查

| Spec 要求 | 对应 Task |
|---|---|
| 两任务自驱动状态机（cicd → autotest） | Task 2 |
| phase 细粒度终态枚举（5 个 done_* phase） | Task 2 |
| jenkins_builds + jenkins_cicd_builds 两张表 | Task 0 |
| driver 抢占（BEGIN IMMEDIATE） | Task 0 |
| 崩溃自愈（on_start 扫表） | Task 5 |
| 多服务并行触发 cicd | Task 2 |
| repair_runs.repos JSON 字段 | Task 1 |
| parse_developer_output 兼容单值/数组 | Task 1 |
| cicd 失败短路不跑测试 | Task 2 |
| autotest ABORTED → done_test_aborted | Task 2 |
| get_report 只读库按 phase 组装报告 | Task 2 |
| 超时判定（build_timeout_seconds 可配） | Task 2 |
| 超时旁路（不归因不计重试直接 REJECTED） | Task 3、Task 6 |
| 超时反写 Linear 通知 | Task 3 |
| retrigger-build CLI 门禁+重申锁 | Task 4 |
| bug-fix-developer skill 重跑说明 | Task 6 |
| Jenkins env 配置 | Task 5 |
| config.json 新增参数 | Task 5 |
| FakeJenkins 支持 timeout/multi-repo | Task 3 |
| 集成测试超时旁路 | Task 6 |
