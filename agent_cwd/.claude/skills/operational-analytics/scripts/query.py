#!/usr/bin/env python3
"""Simplified CLI tool for executing SQL queries on EOP database.

Usage:
    python query.py "SELECT * FROM t_ocm_order_header LIMIT 10"
    python query.py --file query.sql

Example:
    python query.py "SELECT COUNT(*) FROM t_ocm_tenant WHERE fname LIKE '%微众%'"
"""

import sys
import os
import asyncio
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
# Try to find .env in current working directory or parent directories
current_dir = Path.cwd()
env_file = current_dir / '.env'
if not env_file.exists():
    # Try parent directories (up to 4 levels)
    for i in range(4):
        current_dir = current_dir.parent
        env_file = current_dir / '.env'
        if env_file.exists():
            break
if env_file.exists():
    load_dotenv(env_file)

# Add scripts directory to path to allow imports
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    # Import using absolute module names after adding to path
    import query_executor
    import result_formatter
    QueryExecutor = query_executor.QueryExecutor
    ResultFormatter = result_formatter.ResultFormatter
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保已安装依赖:")
    print("  source .venv/bin/activate && pip install -r requirements.txt")
    sys.exit(1)


async def execute_query(sql: str, show_sql: bool = True) -> None:
    """Execute SQL query and print results.

    Args:
        sql: SQL query to execute
        show_sql: Whether to show the SQL before execution
    """
    executor = QueryExecutor()
    formatter = ResultFormatter()

    try:
        if show_sql:
            print("### SQL:")
            print(f"```sql\n{sql.strip()}\n```\n")

        # Validate SQL
        is_valid, error = executor.validate_sql(sql)
        if not is_valid:
            print(f"❌ SQL 验证失败: {error}\n")
            return

        # Execute query
        print("### 执行结果:\n")
        results = await executor.execute(sql)

        if not results:
            print("查询结果为空（0条记录）\n")
            print("💡 提示:")
            print("  - 检查时间范围是否正确")
            print("  - 尝试放宽过滤条件")
            print("  - 使用诊断工具: python diagnose.py\n")
        else:
            print(formatter.to_markdown_table(results))
            print(f"\n**共 {len(results)} 条记录**\n")

    except ValueError as e:
        print(f"❌ 参数错误: {e}\n")
    except Exception as e:
        print(f"❌ 查询执行失败: {e}\n")
    finally:
        await executor.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Parse arguments
    if sys.argv[1] in ['-h', '--help']:
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] in ['-f', '--file']:
        if len(sys.argv) < 3:
            print("❌ 请指定 SQL 文件路径")
            sys.exit(1)
        sql_file = Path(sys.argv[2])
        if not sql_file.exists():
            print(f"❌ 文件不存在: {sql_file}")
            sys.exit(1)
        sql = sql_file.read_text(encoding='utf-8')
    else:
        sql = sys.argv[1]

    # Execute query
    asyncio.run(execute_query(sql))


if __name__ == '__main__':
    main()
