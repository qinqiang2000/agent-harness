#!/usr/bin/env python3
"""通过 Archery Web 接口执行 SQL 查询。

自动处理登录、Session、CSRF Token，执行前强制 EXPLAIN 检查，拦截全表扫描和大结果集。

安全限制：
  - 只允许 SELECT 语句
  - 执行前先 EXPLAIN，发现全表扫描（type=ALL）或预估行数超阈值则拒绝
  - 默认最大预估行数 10000，可通过 --max-rows 调整

用法：
  python3 scripts/archery_query.py \
    --host http://archery.example.com \
    --user admin --password secret \
    --instance my_db_instance \
    --db mydb \
    --sql "SELECT id, name FROM users WHERE id = 1"

  # 调整行数阈值
  python3 scripts/archery_query.py ... --max-rows 5000

  # 输出表格格式
  python3 scripts/archery_query.py ... --format table

  # 从文件读取 SQL，结果写入文件
  python3 scripts/archery_query.py ... --sql-file /tmp/q.sql --output /tmp/result.json

环境变量（优先级低于命令行参数）：
  ARCHERY_HOST      Archery 地址
  ARCHERY_USER      用户名
  ARCHERY_PASSWORD  密码
"""

import argparse
import json
import os
import re
import sys
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

# EXPLAIN 结果中判定为全表扫描的 type 值
FULL_SCAN_TYPES = {"ALL"}

# EXPLAIN Extra 列中判定为高危的关键词
DANGEROUS_EXTRA = {"Using filesort", "Using temporary"}

# 默认预估行数上限
DEFAULT_MAX_ROWS = 1000

# SQL 静态分析规则：(描述, 正则)
# 在发给 Archery 之前拦截高危模式
_STATIC_RULES: list[tuple[str, re.Pattern]] = [
    (
        "禁止前缀通配符 LIKE '%...'，会导致全表扫描",
        re.compile(r"LIKE\s+['\"]%", re.IGNORECASE),
    ),
    (
        "禁止对字段使用函数（如 YEAR(col)、DATE(col)），会导致索引失效",
        re.compile(r"\b(?:YEAR|MONTH|DAY|DATE|DATE_FORMAT|IFNULL|COALESCE|LOWER|UPPER|TRIM|LENGTH|SUBSTR|SUBSTRING|CAST|CONVERT)\s*\(\s*\w+\s*[,)]", re.IGNORECASE),
    ),
    (
        "禁止无 WHERE 条件的查询，可能导致全表扫描",
        re.compile(r"^\s*SELECT\b(?!.*\bWHERE\b)", re.IGNORECASE | re.DOTALL),
    ),
#     (
#         "禁止 SELECT *，请明确列出需要的字段",
#         re.compile(r"SELECT\s+\*", re.IGNORECASE),
#     ),
    (
        "禁止 OR 连接不同字段的条件，可能导致索引失效",
        re.compile(r"\b(\w+)\s*=\s*[^\s]+\s+OR\s+(?!\1\b)\w+\s*=", re.IGNORECASE),
    ),
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _build_opener():
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    return opener, jar


def _get_jar(opener) -> CookieJar:
    for handler in opener.handlers:
        if isinstance(handler, HTTPCookieProcessor):
            return handler.cookiejar
    return CookieJar()


def _csrf_from_jar(jar: CookieJar) -> str:
    for cookie in jar:
        if cookie.name == "csrftoken":
            return cookie.value
    return ""


def _do_request(opener, url: str, data: bytes | None = None, referer: str = "", csrf: str = "") -> str:
    req = Request(url, data=data)
    req.add_header("User-Agent", "archery-query-script/1.0")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    if referer:
        req.add_header("Referer", referer)
    if csrf:
        req.add_header("X-CSRFToken", csrf)
    try:
        resp = opener.open(req)
        return resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code not in (200, 302):
            raise RuntimeError(f"HTTP {e.code}：{body[:300]}")
        return body
    except URLError as e:
        raise RuntimeError(f"网络错误：{e}")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(opener, host: str, username: str, password: str) -> str:
    """登录 Archery，返回 csrftoken。"""
    login_url = urljoin(host, "/login/")
    jar = _get_jar(opener)

    # GET 登录页，写入初始 csrftoken
    _do_request(opener, login_url)
    csrf = _csrf_from_jar(jar)

    # POST 登录（Archery 用 /authenticate/ 接口，返回 JSON）
    auth_url = urljoin(host, "/authenticate/")
    payload = urlencode({
        "username": username,
        "password": password,
    }).encode()
    body = _do_request(opener, auth_url, data=payload, referer=login_url, csrf=csrf)
    try:
        resp_json = json.loads(body)
        if resp_json.get("status") != 0:
            raise RuntimeError(f"登录失败：{resp_json.get('msg', body[:200])}")
    except json.JSONDecodeError:
        raise RuntimeError(f"登录响应不是合法 JSON：{body[:200]}")

    # 登录后 csrftoken 可能刷新
    csrf = _csrf_from_jar(jar)
    if not csrf:
        raise RuntimeError("登录后未获取到 csrftoken，请检查用户名/密码或 Archery 地址")
    return csrf


# ---------------------------------------------------------------------------
# SQL safety checks
# ---------------------------------------------------------------------------

def check_select_only(sql: str) -> None:
    """只允许 SELECT 语句，否则抛出 ValueError。"""
    first_word = sql.strip().split()[0].upper() if sql.strip() else ""
    if first_word != "SELECT":
        raise ValueError(f"只允许 SELECT 语句，当前语句类型：{first_word or '(空)'}")


def check_static_rules(sql: str) -> None:
    """静态分析：拦截高危 SQL 模式，在发给 Archery 之前执行。"""
    # 去掉注释再检测，避免注释内容误触发
    sql_clean = re.sub(r"--[^\n]*", " ", sql)
    sql_clean = re.sub(r"/\*.*?\*/", " ", sql_clean, flags=re.DOTALL)

    violations = []
    for desc, pattern in _STATIC_RULES:
        if pattern.search(sql_clean):
            violations.append(f"  - {desc}")

    if violations:
        raise ValueError(
            "SQL 包含高危模式，已拒绝执行：\n" + "\n".join(violations)
        )


def parse_explain_rows(explain_result: dict) -> tuple[bool, int, list[str]]:
    """
    解析 EXPLAIN 结果，返回 (has_full_scan, max_estimated_rows, dangerous_extras)。
    Archery /query/ 返回格式：
      data.column_list = ["id", "select_type", "table", "type", "rows", "Extra", ...]
      data.rows = [[...], ...]
    """
    data = explain_result.get("data", {})
    columns = [c.lower() for c in data.get("column_list", [])]
    rows = data.get("rows", [])

    if not columns or not rows:
        return False, 0, []

    type_idx = columns.index("type") if "type" in columns else -1
    rows_idx = columns.index("rows") if "rows" in columns else -1
    extra_idx = columns.index("extra") if "extra" in columns else -1

    has_full_scan = False
    max_rows = 0
    dangerous_extras = []

    for row in rows:
        if type_idx >= 0 and len(row) > type_idx:
            if str(row[type_idx]).upper() in FULL_SCAN_TYPES:
                has_full_scan = True
        if rows_idx >= 0 and len(row) > rows_idx:
            try:
                max_rows = max(max_rows, int(row[rows_idx]))
            except (TypeError, ValueError):
                pass
        if extra_idx >= 0 and len(row) > extra_idx:
            extra_val = str(row[extra_idx]) if row[extra_idx] else ""
            for danger in DANGEROUS_EXTRA:
                if danger in extra_val and danger not in dangerous_extras:
                    dangerous_extras.append(danger)

    return has_full_scan, max_rows, dangerous_extras


# ---------------------------------------------------------------------------
# Core query
# ---------------------------------------------------------------------------

def _call_query(opener, host: str, csrf: str, instance_name: str, db_name: str,
                sql: str, limit_num: int, schema_name: str) -> dict:
    query_url = urljoin(host, "/query/")
    params = {
        "instance_name": instance_name,
        "db_name": db_name,
        "sql_content": sql,
        "limit_num": str(limit_num),
        "csrfmiddlewaretoken": csrf,
    }
    if schema_name:
        params["schema_name"] = schema_name

    body = _do_request(
        opener, query_url,
        data=urlencode(params).encode(),
        referer=urljoin(host, "/sqlquery/"),
        csrf=csrf,
    )
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"响应不是合法 JSON：{body[:200]}")


def explain_and_check(opener, host: str, csrf: str, instance_name: str, db_name: str,
                      sql: str, schema_name: str, max_rows: int) -> None:
    """执行 EXPLAIN，发现全表扫描、危险 Extra 或预估行数超限则拒绝。"""
    result = _call_query(
        opener, host, csrf,
        instance_name=instance_name,
        db_name=db_name,
        sql=f"EXPLAIN {sql}",
        limit_num=0,
        schema_name=schema_name,
    )

    if result.get("status") != 0:
        print(f"警告：EXPLAIN 执行失败（{result.get('msg')}），跳过预检", file=sys.stderr)
        return

    has_full_scan, estimated_rows, dangerous_extras = parse_explain_rows(result)

    if has_full_scan:
        raise ValueError(
            "查询包含全表扫描（EXPLAIN type=ALL），已拒绝执行。\n"
            "请添加合适的索引条件后重试。"
        )
    if dangerous_extras:
        raise ValueError(
            f"EXPLAIN 发现高危执行计划（{', '.join(dangerous_extras)}），已拒绝执行。\n"
            "Using filesort 表示需要额外排序，Using temporary 表示使用了临时表，均可能导致慢查询。\n"
            "请优化查询条件或添加合适的索引。"
        )
    if estimated_rows > max_rows:
        raise ValueError(
            f"EXPLAIN 预估返回行数 {estimated_rows:,} 超过限制 {max_rows:,}，已拒绝执行。\n"
            "请缩小查询范围或使用 --max-rows 调整阈值。"
        )


def query_sql(opener, host: str, csrf: str, instance_name: str, db_name: str,
              sql: str, limit_num: int, schema_name: str, max_rows: int) -> dict:
    """安全查询：静态分析 → SELECT 校验 → EXPLAIN 检查 → 执行。"""
    check_select_only(sql)
    check_static_rules(sql)
    explain_and_check(opener, host, csrf, instance_name, db_name, sql, schema_name, max_rows)
    return _call_query(opener, host, csrf, instance_name, db_name, sql, limit_num, schema_name)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_output(result: dict, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)

    if result.get("status") != 0:
        return json.dumps({"error": result.get("msg", "未知错误")}, ensure_ascii=False)

    data = result.get("data", {})
    columns = data.get("column_list", [])
    rows = data.get("rows", [])

    if fmt == "rows":
        lines = [
            json.dumps(dict(zip(columns, row)), ensure_ascii=False)
            for row in rows
        ]
        return "\n".join(lines)

    if fmt == "table":
        if not rows:
            return "(无数据)"
        col_widths = [len(str(c)) for c in columns]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val) if val is not None else "NULL"))
        sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
        header = "| " + " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(columns)) + " |"
        lines = [sep, header, sep]
        for row in rows:
            line = "| " + " | ".join(
                (str(v) if v is not None else "NULL").ljust(col_widths[i])
                for i, v in enumerate(row)
            ) + " |"
            lines.append(line)
        lines.append(sep)
        lines.append(f"共 {len(rows)} 行，耗时 {data.get('query_time', '?')}s")
        return "\n".join(lines)

    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Archery SQL 查询工具（生产环境安全版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default=os.environ.get("ARCHERY_HOST", ""),
                        help="Archery 地址，如 http://archery.example.com")
    parser.add_argument("--user", default=os.environ.get("ARCHERY_USER", ""), help="用户名")
    parser.add_argument("--password", default=os.environ.get("ARCHERY_PASSWORD", ""), help="密码")
    parser.add_argument("--instance", default=os.environ.get("ARCHERY_INSTANCE", "发票云"), help="Archery 实例名称，默认 发票云")
    parser.add_argument("--db", required=True, help="数据库名")
    parser.add_argument("--sql", help="SQL 语句（仅支持 SELECT）")
    parser.add_argument("--sql-file", metavar="FILE", help="从文件读取 SQL")
    parser.add_argument("--schema", default="", help="Schema 名称（PG/Oracle 等需要）")
    parser.add_argument("--limit", type=int, default=1000, help="最大返回行数，默认 1000")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS,
                        help=f"EXPLAIN 预估行数上限，超过则拒绝执行，默认 {DEFAULT_MAX_ROWS}")
    parser.add_argument("--format", choices=["json", "rows", "table"], default="rows",
                        help="输出格式：json/rows/table，默认 rows")
    parser.add_argument("--output", metavar="FILE", help="输出到文件（不指定则输出到 stdout）")
    args = parser.parse_args()

    if not args.host:
        print("错误：未指定 --host 或 ARCHERY_HOST", file=sys.stderr)
        sys.exit(1)
    if not args.user or not args.password:
        print("错误：未指定 --user / --password 或对应环境变量", file=sys.stderr)
        sys.exit(1)

    if args.sql_file:
        with open(args.sql_file, encoding="utf-8") as f:
            sql = f.read().strip()
    elif args.sql:
        sql = args.sql.strip()
    else:
        print("错误：需要 --sql 或 --sql-file 之一", file=sys.stderr)
        sys.exit(1)

    host = args.host.rstrip("/")

    try:
        opener, _ = _build_opener()
        csrf = login(opener, host, args.user, args.password)
        result = query_sql(
            opener, host, csrf,
            instance_name=args.instance,
            db_name=args.db,
            sql=sql,
            limit_num=args.limit,
            schema_name=args.schema,
            max_rows=args.max_rows,
        )
    except ValueError as e:
        # 安全拦截（非 SELECT、全表扫描、行数超限）
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    output = format_output(result, args.format)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"已写入 → {args.output}", file=sys.stderr)
    else:
        print(output)

    if result.get("status") != 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
