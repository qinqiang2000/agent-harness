"""统一数据库迁移脚本。

每次给任意表新增字段时，在对应 db 的 MIGRATIONS 里追加一条，然后手工跑一次：
    python scripts/migrate_repair_db.py

脚本幂等：列已存在时跳过，不会重复执行。
所有 db 文件路径可通过环境变量覆盖（与各 store 保持一致）。
"""

import argparse
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _resolve(env_key: str, default: str) -> str:
    path = os.getenv(env_key, default)
    return path if os.path.isabs(path) else str(ROOT / path)


# db文件路径 → 该库内各表的新增列迁移
# 格式：{ db_path_resolver: { table: [(col, definition), ...] } }
# 按加入顺序追加，不要修改已有条目
MIGRATIONS: dict[str, dict[str, list[tuple[str, str]]]] = {
    _resolve("REPAIR_DB_PATH", "data/repair/repair_runs.db"): {
        "repair_runs": [
            ("repos", "TEXT DEFAULT ''"),
            ("linear_session_id", "TEXT DEFAULT ''"),
        ],
        "repo_locks": [
            # 以后在这里追加
        ],
    },
    _resolve("JENKINS_BUILDS_DB_PATH", "data/repair/jenkins_builds.db"): {
        "jenkins_builds": [
            ("linear_identifier", "TEXT DEFAULT ''"),
            ("report_path", "TEXT DEFAULT ''"),
        ],
        "jenkins_cicd_builds": [
            # 以后在这里追加
        ],
    },
    _resolve("LINEAR_TOKEN_DB", "data/linear/linear_tokens.db"): {
        "linear_installations": [
            # 以后在这里追加
        ],
    },
}


def migrate_db(db_path: str, tables: dict[str, list[tuple[str, str]]]) -> None:
    if not os.path.exists(db_path):
        print(f"  [skip] 文件不存在：{db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        for table, columns in tables.items():
            if not columns:
                continue
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not existing:
                print(f"  [skip] 表不存在：{table}")
                continue
            for col, definition in columns:
                if col in existing:
                    print(f"  skip  {table}.{col}（已存在）")
                else:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                    conn.commit()
                    print(f"  add   {table}.{col} {definition}")
    finally:
        conn.close()


def migrate_linear_session_map(db_path: str) -> None:
    """重建 linear_session_map：旧表以 issue_id 为主键，新表以 linear_session_id 为主键。"""
    if not os.path.exists(db_path):
        print(f"  [skip] 文件不存在：{db_path}")
        return
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(linear_session_map)")}
        if not cols:
            print(f"  [skip] 表不存在：linear_session_map")
            return
        if "linear_session_id" in cols:
            print(f"  skip  linear_session_map（已是新结构）")
            return
        print(f"  migrate linear_session_map: issue_id PK → linear_session_id PK")
        conn.execute("ALTER TABLE linear_session_map RENAME TO linear_session_map_old")
        conn.execute("""
            CREATE TABLE linear_session_map (
                linear_session_id TEXT PRIMARY KEY,
                issue_id          TEXT NOT NULL DEFAULT '',
                claude_session_id TEXT NOT NULL,
                updated_at        INTEGER NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO linear_session_map (linear_session_id, issue_id, claude_session_id, updated_at)
            SELECT claude_session_id, issue_id, claude_session_id, updated_at
            FROM linear_session_map_old
        """)
        conn.execute("DROP TABLE linear_session_map_old")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_linear_session_map_issue_id
            ON linear_session_map (issue_id, updated_at)
        """)
        conn.commit()
        print(f"  done  linear_session_map rebuilt")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="统一数据库迁移脚本")
    parser.parse_args()

    for db_path, tables in MIGRATIONS.items():
        print(f"\n[{db_path}]")
        migrate_db(db_path, tables)

    # linear_session_map 结构重建（主键变更，不能用 ALTER TABLE）
    linear_db = _resolve("LINEAR_TOKEN_DB", "data/linear/linear_tokens.db")
    print(f"\n[{linear_db}] linear_session_map 结构迁移")
    migrate_linear_session_map(linear_db)

    print("\n全部完成。")


if __name__ == "__main__":
    main()
