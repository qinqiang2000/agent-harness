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
