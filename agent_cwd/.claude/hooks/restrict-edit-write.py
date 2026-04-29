#!/usr/bin/env python3
"""
PreToolUse hook: 拦截 Edit 和 Write 工具，只允许操作 data/issue-diagnosis/instincts/ 目录。
其他路径一律 deny，防止 Agent 修改 GitLab 源码或其他不允许的文件。
"""
import json
import sys

ALLOWED_PREFIXES = [
    "/data/issue-diagnosis/instincts/",
]


def is_allowed(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    return any(prefix in normalized for prefix in ALLOWED_PREFIXES)


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = event.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return

    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not is_allowed(file_path):
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"禁止修改文件：{file_path}。只允许记录问题定位经验记录。"
            }
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
