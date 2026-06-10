"""任务工单存储服务.

Phase 1: JSON 文件存储（后续可切换为 PostgreSQL）。
每个任务是一个 JSON 文件，存储在 agent_cwd/data/tasks/ 目录下。
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

TASKS_DIR = DATA_DIR / "tasks"

# 任务状态
STATUS_PENDING = "pending"      # 已创建，等待执行
STATUS_RUNNING = "running"      # 执行中
STATUS_COMPLETED = "completed"  # 已完单
STATUS_FAILED = "failed"        # 失败


def _ensure_dir():
    TASKS_DIR.mkdir(parents=True, exist_ok=True)


def _now_str() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def _gen_task_id() -> str:
    """生成任务 ID: OPS-yyyyMMdd-xxxx."""
    date_part = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:4].upper()
    return f"OPS-{date_part}-{short_uuid}"


def create_task(
    creator: str,
    task_type: str,
    target: str,
    content: str,
) -> dict:
    """创建任务工单，返回完整任务对象。"""
    _ensure_dir()
    task_id = _gen_task_id()
    task = {
        "id": task_id,
        "creator": creator,
        "task_type": task_type,
        "target": target,
        "content": content,
        "status": STATUS_PENDING,
        "created_at": _now_str(),
        "updated_at": _now_str(),
        "completed_at": None,
        "stages": [
            {"time": _now_str(), "msg": "📥 任务已创建"}
        ],
        "result_summary": None,
        "full_report": None,
        "report_id": None,
    }
    _save(task)
    logger.info(f"[TaskStore] Created task {task_id} by {creator}, type={task_type}, target={target}")
    return task


def add_stage(task_id: str, msg: str):
    """给任务追加执行阶段记录。"""
    task = get_task(task_id)
    if not task:
        logger.warning(f"[TaskStore] Cannot add stage to unknown task: {task_id}")
        return
    task["stages"].append({"time": _now_str(), "msg": msg})
    task["updated_at"] = _now_str()
    _save(task)


def update_status(task_id: str, status: str, result_summary: str = None, report_id: str = None, full_report: str = None):
    """更新任务状态。"""
    task = get_task(task_id)
    if not task:
        logger.warning(f"[TaskStore] Cannot update unknown task: {task_id}")
        return
    task["status"] = status
    task["updated_at"] = _now_str()
    if status in (STATUS_COMPLETED, STATUS_FAILED):
        task["completed_at"] = _now_str()
    if result_summary:
        task["result_summary"] = result_summary
    if report_id:
        task["report_id"] = report_id
    if full_report:
        task["full_report"] = full_report
    _save(task)
    logger.info(f"[TaskStore] Task {task_id} status -> {status}")


def get_task(task_id: str) -> Optional[dict]:
    """获取单个任务。"""
    task_file = TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        return None
    try:
        return json.loads(task_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"[TaskStore] Failed to read task {task_id}: {e}")
        return None


def list_tasks(limit: int = 50, status: str = None) -> list:
    """列出最近的任务（按时间倒序），可按状态筛选。"""
    _ensure_dir()
    files = sorted(TASKS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    tasks = []
    for f in files:
        if len(tasks) >= limit:
            break
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if status and data.get("status") != status:
                continue
            tasks.append(data)
        except Exception:
            continue
    return tasks


def _save(task: dict):
    """持久化任务到文件。"""
    _ensure_dir()
    task_file = TASKS_DIR / f"{task['id']}.json"
    task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
