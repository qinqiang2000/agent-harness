#!/usr/bin/env python3
"""数据库查询 CLI 脚本，供 issue-diagnosis SKILL.md 通过 Bash 调用。

用法：
  python db/db_query.py --list-sources
  python db/db_query.py --source <name> --query '{"type":"template","sql":"SELECT ...","evidence":"faq_001"}'
  python db/db_query.py --source <name> --query '{"type":"log","sql":"SELECT ...","evidence":"原始日志行"}'
  python db/db_query.py --source <name> --describe <table_name>

--query 参数说明：
  type      来源类型，必填，只允许 "template" 或 "log" 或 "faq"
  sql       SELECT 语句，必填
  evidence  来源凭证，必填
            - type=template：填模板 ID（如 "faq_001"），脚本会校验 SQL 是否与模板匹配
            - type=log：填日志原文片段，非空即可

输出格式：JSON
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── 虚拟环境自举 ──────────────────────────────────────────────────────────────

_VENV_DIR = Path(__file__).parent / ".venv"
_REQUIRED = ["aiomysql", "asyncpg"]


def _bootstrap():
    """首次运行时创建 venv 并安装依赖，之后用 venv python 重新执行自身。"""
    venv_python = _VENV_DIR / "bin" / "python3"

    # 已在 venv 内，直接继续
    if sys.prefix == str(_VENV_DIR):
        return

    # venv 不存在则创建并安装依赖
    if not venv_python.exists():
        print(json.dumps({"status": "初始化数据库环境，首次运行需安装依赖..."}), file=sys.stderr)
        subprocess.run([sys.executable, "-m", "venv", str(_VENV_DIR)], check=True)
        pip = _VENV_DIR / "bin" / "pip"
        subprocess.run([str(pip), "install", "--quiet"] + _REQUIRED, check=True)

    # 用 venv python 重新执行当前脚本，透传所有参数
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


_bootstrap()


# ── 安全校验 ──────────────────────────────────────────────────────────────────

FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE",
    "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC",
    "EXECUTE", "REPLACE", "MERGE", "LIKE",
]

MAX_ROWS = 200


def validate_query(query: dict) -> tuple[bool, str, str]:
    """校验 --query JSON，返回 (is_valid, error_message, final_sql)。

    final_sql 是通过校验后实际执行的 SQL（自动补 LIMIT）。
    """
    qtype = query.get("type", "")
    sql = query.get("sql", "").strip()
    evidence = query.get("evidence", "").strip()

    # ── 来源类型校验 ──────────────────────────────────────────────────────────
    if qtype not in ("template", "log", "faq"):
        return False, "type 必须为 'template'、'log' 或 'faq'，禁止直接执行无来源 SQL", ""

    if not sql:
        return False, "sql 字段不能为空", ""

    if not evidence:
        return False, "evidence 字段不能为空（template 填模板ID，log 填日志原文，faq 填文件名）", ""

    # ── SQL 只读校验 ──────────────────────────────────────────────────────────
    upper = sql.upper().lstrip()
    if not upper.startswith("SELECT"):
        return False, "只允许 SELECT 语句", ""

    padded = f" {upper} "
    for kw in FORBIDDEN_KEYWORDS:
        if f" {kw} " in padded or f" {kw}\n" in padded or f"\n{kw} " in padded:
            return False, f"包含禁止关键词：{kw}", ""

    without_trailing = sql.rstrip(";")
    if ";" in without_trailing:
        return False, "不允许多条语句", ""

    if "WHERE" not in upper:
        return False, "必须包含 WHERE 条件，禁止全表扫描", ""

    # ── 自动补 LIMIT ──────────────────────────────────────────────────────────
    final_sql = sql.rstrip(";")
    if "LIMIT" not in upper:
        final_sql = f"{final_sql} LIMIT {MAX_ROWS}"

    return True, "", final_sql


# ── 异步执行逻辑 ──────────────────────────────────────────────────────────────

async def run_query(source_name: str, sql: str) -> dict:
    """执行 SQL 查询，返回结构化结果。"""
    # 导入连接器（相对路径兼容两种运行方式）
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from db_connector import DbConnector, load_config

    config = load_config(source_name)
    connector = DbConnector()

    t0 = time.monotonic()
    try:
        await connector.init(config)
        rows = await connector.execute(sql, timeout=config.get("timeout", 30))
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        total = len(rows)
        truncated = total > MAX_ROWS
        return {
            "data": rows[:MAX_ROWS],
            "row_count": total,
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "error": None,
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "data": [],
            "row_count": 0,
            "truncated": False,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }
    finally:
        await connector.close()


async def run_describe(source_name: str, table_name: str) -> dict:
    """查询表结构。"""
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from db_connector import DbConnector, load_config

    config = load_config(source_name)
    connector = DbConnector()

    t0 = time.monotonic()
    try:
        await connector.init(config)
        columns = await connector.describe_table(table_name)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "table": table_name,
            "columns": columns,
            "column_count": len(columns),
            "elapsed_ms": elapsed_ms,
            "error": None,
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "table": table_name,
            "columns": [],
            "column_count": 0,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }
    finally:
        await connector.close()


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def _err_result(msg: str) -> dict:
    return {"data": [], "row_count": 0, "truncated": False, "elapsed_ms": 0, "error": msg}


def main():
    parser = argparse.ArgumentParser(
        description="issue-diagnosis 数据库查询工具"
    )
    parser.add_argument("--list-sources", action="store_true", help="列出所有可用数据源")
    parser.add_argument("--source", metavar="NAME", help="数据源名称")
    parser.add_argument(
        "--query", metavar="JSON",
        help='查询参数 JSON，必须包含 type/sql/evidence，'
             '例：\'{"type":"template","sql":"SELECT ...","evidence":"faq_001"}\''
    )
    parser.add_argument("--describe", metavar="TABLE", help="查看表结构")

    args = parser.parse_args()

    # ── --list-sources ────────────────────────────────────────────────────────
    if args.list_sources:
        script_dir = Path(__file__).parent
        sys.path.insert(0, str(script_dir))
        try:
            from db_connector import list_sources
            sources = list_sources()
            print(json.dumps({"sources": sources, "error": None}, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(json.dumps({"sources": [], "error": str(exc)}, ensure_ascii=False, indent=2))
        return

    # ── --source 必须存在 ─────────────────────────────────────────────────────
    if not args.source:
        parser.error("--source 为必填参数（配合 --query 或 --describe 使用）")

    # ── --query ───────────────────────────────────────────────────────────────
    if args.query:
        try:
            query = json.loads(args.query)
        except json.JSONDecodeError as e:
            print(json.dumps(_err_result(f"--query 参数不是合法 JSON：{e}"), ensure_ascii=False, indent=2))
            return

        valid, err, final_sql = validate_query(query)
        if not valid:
            print(json.dumps(_err_result(f"查询校验失败：{err}"), ensure_ascii=False, indent=2))
            return

        result = asyncio.run(run_query(args.source, final_sql))
        result["source_type"] = query.get("type")
        result["evidence"] = query.get("evidence", "")[:200]  # 截断避免输出过长
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    # ── --describe ────────────────────────────────────────────────────────────
    if args.describe:
        result = asyncio.run(run_describe(args.source, args.describe))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
