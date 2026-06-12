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
        ],
        "repo_locks": [
            # 以后在这里追加
        ],
    },
    _resolve("JENKINS_BUILDS_DB_PATH", "data/repair/jenkins_builds.db"): {
        "jenkins_builds": [
            # 以后在这里追加
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


def main() -> None:
    parser = argparse.ArgumentParser(description="统一数据库迁移脚本")
    parser.parse_args()

    for db_path, tables in MIGRATIONS.items():
        print(f"\n[{db_path}]")
        migrate_db(db_path, tables)

    print("\n全部完成。")


if __name__ == "__main__":
    main()
