#!/usr/bin/env python3
"""
PreToolUse hook: 自动为 mcp__elastic__searchTraceOrKeyWordsLog 注入时间范围参数。
若调用参数中缺少 startTime 或 endTime，通过 hookSpecificOutput.updatedInput 返回修改后的参数。
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
                "updatedInput": tool_input
            }
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
