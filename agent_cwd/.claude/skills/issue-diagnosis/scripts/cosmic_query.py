#!/usr/bin/env python3
"""通过 base-platform-adapter HTTP 接口执行 SQL 查询，替代已停用的 Archery。

安全校验由服务端执行（SELECT-only、禁止危险关键词、必须有 WHERE、EXPLAIN 预检）。
SQL 中的条件值必须用 ? 占位符，通过 --params 传入，服务端用 PreparedStatement 绑定，彻底防止 SQL 注入。
SQL 中的表名无需手动加库名前缀，服务端会根据 --db 参数自动注入。

用法：
  python3 scripts/cosmic_query.py \\
    --db invoice \\
    --sql "SELECT id, fcode FROM t_ocm_order_header WHERE fcode = ?" \\
    --params '["123"]' \\
    --evidence "faq_001" \\
    --source-type template

  python3 scripts/cosmic_query.py \\
    --env sit \\
    --db cms \\
    --sql "SELECT fid, fname FROM t_org_org WHERE fid = ? AND fstatus = ?" \\
    --params '["xxx", "1"]' \\
    --evidence "原始日志行" \\
    --source-type log \\
    --format table

环境变量：
  COSMIC_QUERY_TOKEN  鉴权 Token（默认 f952beac1e3bc0c513aca7153428f60d）
  COSMIC_QUERY_HOST   手动指定服务地址，优先级高于 --env
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

ENV_HOSTS = {
    "prod": "https://api.piaozone.com",
    "sit":  "https://api-sit.piaozone.com",
    "demo": "https://api-dev.piaozone.com",
}

DEFAULT_TOKEN = os.environ.get("COSMIC_QUERY_TOKEN", "f952beac1e3bc0c513aca7153428f60d")


def _resolve_host(env: str) -> str:
    override = os.environ.get("COSMIC_QUERY_HOST", "")
    if override:
        return override.rstrip("/")
    return ENV_HOSTS.get(env, ENV_HOSTS["prod"])


def query(host: str, database: str, sql: str, params: list,
          evidence: str, source_type: str, token: str) -> dict:
    url = f"{host}/ai/knowledge/free/db/query"
    payload = json.dumps({
        "database": database,
        "sql": sql,
        "params": params,
        "evidence": evidence,
        "sourceType": source_type,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Query-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}")


def format_table(rows: list, row_count: int, elapsed_ms: int, truncated: bool) -> str:
    if not rows:
        return "(无数据)"
    cols = list(rows[0].keys())
    widths = {c: len(str(c)) for c in cols}
    for row in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(row.get(c)) if row.get(c) is not None else "NULL"))
    sep = "+-" + "-+-".join("-" * widths[c] for c in cols) + "-+"
    header = "| " + " | ".join(str(c).ljust(widths[c]) for c in cols) + " |"
    lines = [sep, header, sep]
    for row in rows:
        val_strs = [
            (str(row.get(c)) if row.get(c) is not None else "NULL").ljust(widths[c])
            for c in cols
        ]
        lines.append("| " + " | ".join(val_strs) + " |")
    lines.append(sep)
    suffix = f"共 {row_count} 行，耗时 {elapsed_ms}ms"
    if truncated:
        suffix += "（结果已截断）"
    lines.append(suffix)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="base-platform-adapter SQL 查询工具（PreparedStatement 防注入）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--env", default="prod",
                        choices=["prod", "sit", "demo"],
                        help="目标环境：prod（生产）/ sit（测试）/ demo（演示），默认 prod")
    parser.add_argument("--db", required=True,
                        help="数据库名，如 invoice / cms / eop")
    parser.add_argument("--sql", required=True,
                        help="SELECT 模板，条件值用 ? 占位，例：SELECT id FROM t WHERE fcode = ?")
    parser.add_argument("--params", default="[]",
                        help='与 ? 一一对应的参数值 JSON 数组，例：\'["123", "1"]\'')
    parser.add_argument("--evidence", default="",
                        help="审计凭证：模板ID（template）、日志原文（log）、faq文件名（faq）")
    parser.add_argument("--source-type", default="log",
                        choices=["template", "log", "faq"],
                        help="来源类型，默认 log")
    parser.add_argument("--format", choices=["json", "rows", "table"], default="rows",
                        help="输出格式：json/rows/table，默认 rows")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
        if not isinstance(params, list):
            raise ValueError("params 必须是 JSON 数组")
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"--params 解析失败：{e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    host = _resolve_host(args.env)

    try:
        resp = query(host, args.db, args.sql, params, args.evidence, args.source_type, DEFAULT_TOKEN)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    errcode = resp.get("errcode", "")
    if errcode not in ("0", "0000"):
        msg = resp.get("description", "未知错误")
        print(json.dumps({"error": msg}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)

    data = resp.get("data", {})
    rows = data.get("rows", [])
    row_count = data.get("rowCount", len(rows))
    elapsed_ms = data.get("elapsedMs", 0)
    truncated = data.get("truncated", False)

    if args.format == "table":
        print(format_table(rows, row_count, elapsed_ms, truncated))
    elif args.format == "rows":
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, default=str))
        print(f"-- {row_count} 行，耗时 {elapsed_ms}ms" + ("（已截断）" if truncated else ""),
              file=sys.stderr)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()