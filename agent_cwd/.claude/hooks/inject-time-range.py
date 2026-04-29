#!/usr/bin/env python3
"""
PreToolUse hook: 自动为 mcp__elastic__searchTraceOrKeyWordsLog 的关键词查询注入时间范围参数。
仅对 searchWordList 查询生效，traceId 查询不注入时间范围（traceId 全量索引，无需时间过滤）。
注入时间后通过 additionalContext 告知 Agent，避免 Agent 误判"查不到"。
"""
import json
import sys
from datetime import datetime, timedelta


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = event.get("tool_name", "")
    if tool_name != "mcp__elastic__searchTraceOrKeyWordsLog":
        return

    tool_input = event.get("tool_input", {})
    req = tool_input.get("collectorLogRequest", {})

    # traceId 查询不注入时间范围
#     if req.get("traceId"):
#         return

    now = datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"

    modified = False
    if not req.get("startTime"):
        req["startTime"] = (now - timedelta(days=7)).strftime(fmt)
        modified = True
    if not req.get("endTime"):
        req["endTime"] = now.strftime(fmt)
        modified = True

    if modified:
        tool_input["collectorLogRequest"] = req
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": tool_input,
                "additionalContext": f"[系统已自动注入时间范围] startTime={req['startTime']}, endTime={req['endTime']}。若查询无结果，请考虑问题是否发生在此时间范围之外，可向用户确认具体时间后重新查询。"
            }
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
