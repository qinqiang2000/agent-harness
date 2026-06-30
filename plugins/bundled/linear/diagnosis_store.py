"""
Linear session 诊断结论持久化存储。

将 linear_session_id → 诊断结论文本 保存到 SQLite，重启后不丢失。
供 handle_prompted 阶段检测编码意图时读取历史诊断结论使用。

数据库路径优先级：
  1. 环境变量 AGENT_DATA_DIR
  2. 项目根目录 data/
"""

import os
import sqlite3
from pathlib import Path


def _db_path() -> Path:
    """确定数据库文件路径。"""
    data_dir = os.environ.get("AGENT_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "linear_diagnosis.db"
    # 默认：此文件在 plugins/bundled/linear/，上推 3 层到项目根
    plugin_dir = Path(__file__).resolve().parent
    project_root = plugin_dir.parents[2]
    return project_root / "data" / "linear_diagnosis.db"


def _connect() -> sqlite3.Connection:
    """建立连接并初始化表结构。"""
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS linear_diagnosis (
            session_id  TEXT PRIMARY KEY,
            diagnosis   TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    return conn


def get(session_id: str) -> str:
    """查询 session 对应的诊断结论，不存在时返回空字符串。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT diagnosis FROM linear_diagnosis WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row[0] if row else ""


def save(session_id: str, diagnosis: str) -> None:
    """写入或更新 session 的诊断结论。"""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO linear_diagnosis (session_id, diagnosis, updated_at)
            VALUES (?, ?, datetime('now', 'localtime'))
            ON CONFLICT(session_id) DO UPDATE SET
                diagnosis  = excluded.diagnosis,
                updated_at = excluded.updated_at
            """,
            (session_id, diagnosis),
        )
        conn.commit()


def delete(session_id: str) -> None:
    """删除 session 的诊断记录（编码触发后清理）。"""
    with _connect() as conn:
        conn.execute("DELETE FROM linear_diagnosis WHERE session_id = ?", (session_id,))
        conn.commit()
