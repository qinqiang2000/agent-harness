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
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

class Stage:
    """内部阶段游标（非 Linear 状态）。"""

    PENDING_REVIEW = "pending_review"
    DEVELOPING = "developing"
    BUILDING = "building"
    ANALYZING = "analyzing"
    RESOLVED = "resolved"
    REJECTED = "rejected"  # 产研退回转人工
    BLOCKED = "blocked"  # 漏依赖：父单阻塞等子单，由人工接力
    PENDING_RERUN = "pending_rerun"  # 等待人工确认后重修


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
    linear_session_id: str = ""
    fix_retry_count: int = 0
    rediagnose_count: int = 0
    root_cause: str = ""
    repair_plan: str = ""
    evidence: str = ""
    last_report: str = ""
    repos: str = ""  # JSON 数组，如 '["piaozone/base/api-auth"]'
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
                    linear_session_id TEXT DEFAULT '',
                    fix_retry_count   INTEGER DEFAULT 0,
                    rediagnose_count  INTEGER DEFAULT 0,
                    root_cause        TEXT DEFAULT '',
                    repair_plan       TEXT DEFAULT '',
                    evidence          TEXT DEFAULT '',
                    last_report       TEXT DEFAULT '',
                    repos             TEXT DEFAULT '',
                    created_at        INTEGER NOT NULL,
                    updated_at        INTEGER NOT NULL
                )
                """
            )
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
            # 迁移：旧库补列
            try:
                conn.execute("ALTER TABLE repair_runs ADD COLUMN linear_session_id TEXT DEFAULT ''")
            except Exception:
                pass

    def upsert(self, run: RepairRun) -> None:
        """插入或更新整行（按 linear_issue_id 主键），幂等。不修改传入对象。"""
        now = int(time.time())
        created_at = run.created_at or now
        overrides = {"created_at": created_at, "updated_at": now}
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        updates = ", ".join(
            f"{c}=excluded.{c}" for c in _COLUMNS if c not in ("linear_issue_id", "created_at")
        )
        values = [overrides.get(c, getattr(run, c)) for c in _COLUMNS]
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

    def update(self, linear_issue_id: str, **kwargs) -> None:  # noqa: already annotated
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

    def acquire_repos(
        self, issue_id: str, identifier: str, repos: List[str]
    ) -> Tuple[bool, str]:
        """原子申请一组 repo 锁。任一被别的 holder 占用则整组失败，不占任何一个。

        同一 holder 重入算成功（幂等）。返回 (ok, blocking_identifier)：
        成功 (True, "")；被占 (False, 占用方人类可读单号)。
        同一 holder 重入会用 `INSERT OR REPLACE` 重置 `acquired_at`（无副作用，poller 按当前时间判陈旧）。
        """
        now = int(time.time())
        with self._conn() as conn:
            # BEGIN IMMEDIATE：立即取写锁，使「检查 + 占用」成为一个串行化事务，
            # 杜绝两个并发申请各自 SELECT 判空后双双 INSERT 的竞态（busy_timeout 让后者等待）。
            conn.execute("BEGIN IMMEDIATE")
            blocker = None
            for repo in repos:
                row = conn.execute(
                    "SELECT holder_issue_id, holder_identifier FROM repo_locks WHERE repo = ?",
                    (repo,),
                ).fetchone()
                if row is not None and row["holder_issue_id"] != issue_id:
                    blocker = row["holder_identifier"]
                    break
            if blocker is not None:
                return (False, blocker)
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

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RepairRun:
        return RepairRun(**{c: row[c] for c in _COLUMNS})
