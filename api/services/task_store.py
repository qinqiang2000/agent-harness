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
STATUS_TIMEOUT = "timeout"        # 超时（执行时间超过阈值）
STATUS_CANCELLED = "cancelled"    # 手动取消

# 任务最长执行时间（秒），超过则视为超时
TASK_MAX_DURATION_SEC = 1800  # 30 分钟


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
        # 增量加列（兼容老数据库）
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "alert_resolved" not in existing_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN alert_resolved INTEGER DEFAULT 0")
        if "alert_resolved_at" not in existing_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN alert_resolved_at TEXT")
        if "alert_resolved_by" not in existing_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN alert_resolved_by TEXT")

        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
    logger.info(f"[TaskStore] SQLite initialized at {DB_PATH}")


# 模块加载时初始化
_init_db()


def cleanup_stale_running_tasks():
    """启动时调用：把所有 running/pending 的任务标记为失败（服务重启导致中断）。"""
    now = _now_str()
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, stages FROM tasks WHERE status IN (?, ?)",
            (STATUS_RUNNING, STATUS_PENDING)
        ).fetchall()
        for row in rows:
            stages = json.loads(row["stages"] or "[]")
            stages.append({"time": now, "msg": "❌ 服务重启，任务被中断"})
            conn.execute("""
                UPDATE tasks SET
                    status = ?,
                    completed_at = ?,
                    updated_at = ?,
                    stages = ?,
                    result_summary = ?
                WHERE id = ?
            """, (
                STATUS_FAILED, now, now,
                json.dumps(stages, ensure_ascii=False),
                "服务重启导致任务中断",
                row["id"]
            ))
        if rows:
            logger.warning(f"[TaskStore] Cleaned up {len(rows)} stale running tasks on startup")
        return len(rows)


def cancel_task(task_id: str, reason: str = "manual") -> bool:
    """手动取消任务。"""
    now = _now_str()
    with _get_db() as conn:
        row = conn.execute("SELECT status, stages FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return False
        if row["status"] not in (STATUS_PENDING, STATUS_RUNNING):
            return False  # 已结束的任务不能取消

        stages = json.loads(row["stages"] or "[]")
        stages.append({"time": now, "msg": f"⛔ 任务被取消（{reason}）"})
        conn.execute("""
            UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, stages = ?, result_summary = ? WHERE id = ?
        """, (
            STATUS_CANCELLED, now, now,
            json.dumps(stages, ensure_ascii=False),
            f"任务被取消（{reason}）",
            task_id
        ))
    logger.info(f"[TaskStore] Task {task_id} cancelled by {reason}")
    return True


def scan_timeout_tasks(max_duration_sec: int = TASK_MAX_DURATION_SEC) -> int:
    """扫描超过执行时间的任务，标记为 timeout。返回处理数量。"""
    now_dt = datetime.now(timezone(timedelta(hours=8)))
    cutoff_dt = now_dt - timedelta(seconds=max_duration_sec)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    with _get_db() as conn:
        rows = conn.execute("""
            SELECT id, stages FROM tasks
            WHERE status = ? AND created_at < ?
        """, (STATUS_RUNNING, cutoff_str)).fetchall()

        for row in rows:
            stages = json.loads(row["stages"] or "[]")
            stages.append({"time": now_str, "msg": f"⏰ 超时（执行超过 {max_duration_sec // 60} 分钟）"})
            conn.execute("""
                UPDATE tasks SET status = ?, completed_at = ?, updated_at = ?, stages = ?, result_summary = ? WHERE id = ?
            """, (
                STATUS_TIMEOUT, now_str, now_str,
                json.dumps(stages, ensure_ascii=False),
                f"任务执行超时（{max_duration_sec}秒）",
                row["id"]
            ))
        if rows:
            logger.warning(f"[TaskStore] Marked {len(rows)} tasks as timeout")
    return len(rows)


# 启动时清理僵尸任务
cleanup_stale_running_tasks()


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


def list_tasks(limit: int = 50, status: str = None, creator: str = None, alert_resolved: Optional[bool] = None) -> list:
    """列出最近的任务（按创建时间倒序）。

    Args:
        limit: 返回数量上限
        status: 按执行状态精确筛选
        creator: 按创建人模糊匹配
        alert_resolved: 按告警恢复状态筛选 (True=已恢复, False=未恢复, None=不筛选)
    """
    conditions = []
    params = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if creator:
        conditions.append("creator LIKE ?")
        params.append(f"%{creator}%")
    if alert_resolved is True:
        conditions.append("alert_resolved = 1")
    elif alert_resolved is False:
        conditions.append("alert_resolved = 0 AND task_type = 'ops-diagnosis' AND status IN ('completed', 'failed')")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM tasks {where_clause} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with _get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(row) for row in rows]


def list_creators() -> list:
    """列出所有不同的创建人（用于筛选下拉）。"""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT creator, COUNT(*) as cnt FROM tasks GROUP BY creator ORDER BY cnt DESC"
        ).fetchall()
        return [{"name": r["creator"], "count": r["cnt"]} for r in rows]


def mark_alert_resolved(task_id: str, resolved_by: str = "manual") -> bool:
    """标记告警已恢复（手动或 Alertmanager 自动）。返回 True 表示成功。"""
    now = _now_str()
    with _get_db() as conn:
        row = conn.execute("SELECT alert_resolved FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return False
        if row["alert_resolved"]:
            return False  # 已经标记过

        conn.execute(
            "UPDATE tasks SET alert_resolved = 1, alert_resolved_at = ?, alert_resolved_by = ?, updated_at = ? WHERE id = ?",
            (now, resolved_by, now, task_id)
        )
        # 追加一条 stage 记录
        stages_row = conn.execute("SELECT stages FROM tasks WHERE id = ?", (task_id,)).fetchone()
        stages = json.loads(stages_row["stages"] or "[]")
        stages.append({"time": now, "msg": f"🟢 告警已恢复（{resolved_by}）"})
        conn.execute("UPDATE tasks SET stages = ? WHERE id = ?",
                     (json.dumps(stages, ensure_ascii=False), task_id))

    logger.info(f"[TaskStore] Task {task_id} alert resolved by {resolved_by}")
    return True


def find_active_alert_task(alert_type: str, target: str) -> Optional[dict]:
    """查找指定告警类型+目标的最近未恢复任务（向后兼容用，建议改用 find_active_alert_tasks）。"""
    tasks = find_active_alert_tasks(alert_type, target, limit=1)
    return tasks[0] if tasks else None


def find_active_alert_tasks(alert_type: str, target: str, limit: int = 100) -> list:
    """查找指定告警类型+目标的所有未恢复任务（按创建时间倒序）。

    target 通常是 IP，会模糊匹配 task.target 字段。
    同时按 alert_type 关键词过滤，避免不同告警类型互相误标。
    """
    with _get_db() as conn:
        # task.target 形如 "磁盘空间不足 - 172.31.36.49"，同时包含告警类型和 IP
        rows = conn.execute("""
            SELECT * FROM tasks
            WHERE task_type = 'ops-diagnosis'
              AND target LIKE ?
              AND target LIKE ?
              AND alert_resolved = 0
              AND status IN ('completed', 'failed')
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"%{alert_type}%", f"%{target}%", limit)).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_stats() -> dict:
    """获取任务统计信息。"""
    with _get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'failed'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
        # 告警维度：未恢复（已完单但 alert_resolved=0 的诊断任务）
        alert_unresolved = conn.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE task_type = 'ops-diagnosis'
              AND status IN ('completed', 'failed')
              AND alert_resolved = 0
        """).fetchone()[0]
        alert_resolved = conn.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE task_type = 'ops-diagnosis'
              AND alert_resolved = 1
        """).fetchone()[0]
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "alert_unresolved": alert_unresolved,
            "alert_resolved": alert_resolved,
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
