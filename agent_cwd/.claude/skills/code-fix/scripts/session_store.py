#!/usr/bin/env python3
"""
code-fix session 持久化存储。

将 issue → 分支 映射保存到 SQLite，支持二次修改时复用原分支。

数据库路径优先级：
  1. 环境变量 CODE_FIX_DATA_DIR
  2. 环境变量 AGENT_DATA_DIR
  3. 脚本推断的项目 data 目录（agent-harness/data/）

用法：
  # 查询
  python3 session_store.py get CNPRD-866
  # 写入/更新
  python3 session_store.py set CNPRD-866 api-expense /tmp/gitlab/fix/api-expense_170833 fixbug_20260622170909
  # 删除
  python3 session_store.py delete CNPRD-866
"""

import os
import sqlite3
import sys
from pathlib import Path


def _db_path() -> Path:
    """确定数据库文件路径。"""
    # 优先使用环境变量
    data_dir = os.environ.get("CODE_FIX_DATA_DIR") or os.environ.get("AGENT_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "code_fix_sessions.db"

    # 默认：脚本在 agent_cwd/.claude/skills/code-fix/scripts/，上推 5 层到项目根
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parents[4]  # agent-harness/
    return project_root / "data" / "code_fix_sessions.db"


def _connect() -> sqlite3.Connection:
    """建立连接并初始化表结构。"""
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS code_fix_sessions (
            issue_id    TEXT PRIMARY KEY,
            repo_name   TEXT NOT NULL,
            local_dir   TEXT NOT NULL,
            branch_name TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    return conn


def get(issue_id: str) -> dict | None:
    """查询 issue 对应的 session 信息，不存在时返回 None。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT issue_id, repo_name, local_dir, branch_name, created_at, updated_at "
            "FROM code_fix_sessions WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "issue_id": row[0],
        "repo_name": row[1],
        "local_dir": row[2],
        "branch_name": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def set_session(
    issue_id: str, repo_name: str, local_dir: str, branch_name: str
) -> None:
    """写入或更新 issue 的 session 记录。"""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO code_fix_sessions (issue_id, repo_name, local_dir, branch_name, updated_at)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(issue_id) DO UPDATE SET
                repo_name   = excluded.repo_name,
                local_dir   = excluded.local_dir,
                branch_name = excluded.branch_name,
                updated_at  = excluded.updated_at
        """,
            (issue_id, repo_name, local_dir, branch_name),
        )
        conn.commit()


def delete(issue_id: str) -> None:
    """删除 issue 的 session 记录。"""
    with _connect() as conn:
        conn.execute("DELETE FROM code_fix_sessions WHERE issue_id = ?", (issue_id,))
        conn.commit()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "get":
        if len(sys.argv) < 3:
            print("用法: session_store.py get <issue_id>", file=sys.stderr)
            sys.exit(1)
        result = get(sys.argv[2])
        if result:
            for k, v in result.items():
                print(f"{k}={v}")
        else:
            print("NOT_FOUND")

    elif cmd == "set":
        if len(sys.argv) < 6:
            print(
                "用法: session_store.py set <issue_id> <repo_name> <local_dir> <branch_name>",
                file=sys.stderr,
            )
            sys.exit(1)
        set_session(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        print("OK")

    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("用法: session_store.py delete <issue_id>", file=sys.stderr)
            sys.exit(1)
        delete(sys.argv[2])
        print("OK")

    else:
        print(f"未知命令: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
