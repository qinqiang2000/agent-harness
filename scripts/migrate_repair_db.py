"""repair_runs 数据库迁移脚本。

每次给 repair_runs 表新增字段时，在 MIGRATIONS 列表追加一条，然后手工跑一次：
    python scripts/migrate_repair_db.py [--db data/repair/repair_runs.db]

脚本幂等：列已存在时跳过，不会重复执行。
"""

import argparse
import os
import sqlite3
from pathlib import Path

# 按加入顺序追加，不要修改已有条目
MIGRATIONS: list[tuple[str, str]] = [
    # (列名, 列定义)
    ("repos", "TEXT DEFAULT ''"),
]


def migrate(db_path: str) -> None:
    if not os.path.exists(db_path):
        print(f"数据库文件不存在：{db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(repair_runs)")}
        applied = 0
        for col, definition in MIGRATIONS:
            if col in existing:
                print(f"  skip  {col}（已存在）")
            else:
                conn.execute(f"ALTER TABLE repair_runs ADD COLUMN {col} {definition}")
                conn.commit()
                print(f"  add   {col} {definition}")
                applied += 1
        print(f"完成，新增 {applied} 列，跳过 {len(MIGRATIONS) - applied} 列。")
    finally:
        conn.close()


def main() -> None:
    default_db = str(Path(__file__).resolve().parents[1] / "data/repair/repair_runs.db")
    parser = argparse.ArgumentParser(description="repair_runs 数据库迁移")
    parser.add_argument("--db", default=default_db, help="数据库文件路径")
    args = parser.parse_args()
    migrate(args.db)


if __name__ == "__main__":
    main()
