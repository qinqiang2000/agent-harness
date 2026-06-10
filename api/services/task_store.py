"""任务工单存储服务.

使用 SQLite 数据库存储，文件位于 agent_cwd/data/tasks.db。
通过 docker volume 挂载持久化，容器重建不丢数据。
"""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "tasks.db"

# 任务状态
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def _now_str() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def _gen_task_id() -> str:
    date_part = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:4].upper()
    return f"OPS-{date_part}-{short_uuid}"


@contextmanager
def _get_db():
    """获取数据库连接（自动提交）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 并发读写性能更好
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db():
    """初始化数据库表。"""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                creator TEXT NOT NULL,
                task_type TEXT NOT NULL,
                target TEXT,
                content TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                stages TEXT DEFAULT '[]',
                result_summary TEXT,
                full_report TEXT
            )
        """)
        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
    logger.info(f"[TaskStore] SQLite initialized at {DB_PATH}")


# 模块加载时初始化
_init_db()


def create_task(
    creator: str,
    task_type: str,
    target: str,
    content: str,
) -> dict:
    """创建任务工单，返回完整任务对象。"""
    task_id = _gen_task_id()
    now = _now_str()
    stages = [{"time": now, "msg": "📥 任务已创建"}]

    task = {
        "id": task_id,
        "creator": creator,
        "task_type": task_type,
        "target": target,
        "content": content,
        "status": STATUS_PENDING,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "stages": stages,
        "result_summary": None,
        "full_report": None,
    }

    with _get_db() as conn:
        conn.execute("""
            INSERT INTO tasks (id, creator, task_type, target, content, status, created_at, updated_at, stages)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, creator, task_type, target, content, STATUS_PENDING, now, now, json.dumps(stages, ensure_ascii=False)))

    logger.info(f"[TaskStore] Created task {task_id} by {creator}, type={task_type}, target={target}")
    return task


def add_stage(task_id: str, msg: str):
    """给任务追加执行阶段记录。"""
    now = _now_str()
    with _get_db() as conn:
        row = conn.execute("SELECT stages FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            logger.warning(f"[TaskStore] Cannot add stage to unknown task: {task_id}")
            return
        stages = json.loads(row["stages"] or "[]")
        stages.append({"time": now, "msg": msg})
        conn.execute(
            "UPDATE tasks SET stages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(stages, ensure_ascii=False), now, task_id)
        )


def update_status(task_id: str, status: str, result_summary: str = None, full_report: str = None):
    """更新任务状态。"""
    now = _now_str()
    with _get_db() as conn:
        row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            logger.warning(f"[TaskStore] Cannot update unknown task: {task_id}")
            return

        updates = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if status in (STATUS_COMPLETED, STATUS_FAILED):
            updates.append("completed_at = ?")
            params.append(now)
        if result_summary is not None:
            updates.append("result_summary = ?")
            params.append(result_summary)
        if full_report is not None:
            updates.append("full_report = ?")
            params.append(full_report)

        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)

    logger.info(f"[TaskStore] Task {task_id} status -> {status}")


def get_task(task_id: str) -> Optional[dict]:
    """获取单个任务。"""
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return _row_to_dict(row)


def list_tasks(limit: int = 50, status: str = None) -> list:
    """列出最近的任务（按创建时间倒序）。"""
    with _get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_stats() -> dict:
    """获取任务统计信息。"""
    with _get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'failed'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
        }


def _row_to_dict(row: sqlite3.Row) -> dict:
    """将数据库行转为字典。"""
    d = dict(row)
    # stages 是 JSON 字符串，解析为 list
    if d.get("stages"):
        try:
            d["stages"] = json.loads(d["stages"])
        except (json.JSONDecodeError, TypeError):
            d["stages"] = []
    else:
        d["stages"] = []
    return d
