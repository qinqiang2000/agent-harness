#!/usr/bin/env python3
"""
PostToolUse hook: ELK 查询结果超过 Read 工具 token 上限时，自动转为 JSONL。
通过 additionalContext 告知 Agent 文件路径，Agent 按 log-analysis.md 规则继续处理。
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid


# Read 工具上限约 25000 tokens，按 4 字符/token 换算
SIZE_THRESHOLD = 100_000


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    if event.get("tool_name") != "mcp__elastic__searchTraceOrKeyWordsLog":
        return

    tool_response = event.get("tool_response", [])
    if not tool_response:
        return

    text = tool_response[0].get("text", "") if isinstance(tool_response[0], dict) else ""
    if not text or len(text) < SIZE_THRESHOLD:
        return

    tmp_input = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    tmp_input.write(text)
    tmp_input.close()

    output_path = os.path.join(os.path.dirname(tmp_input.name), f"elk_{uuid.uuid4().hex}.jsonl")

    script = os.path.normpath(os.path.join(
        os.path.dirname(__file__),
        "../skills/issue-diagnosis/scripts/parse_logs.py",
    ))

    try:
        subprocess.run(
            [sys.executable, script, "--input", tmp_input.name, "--output", output_path],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return
    finally:
        if os.path.exists(tmp_input.name):
            os.unlink(tmp_input.name)

    try:
        with open(output_path, encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
    except OSError:
        line_count = "未知"

    context = (
        f"[系统已自动将 ELK 查询结果转为 JSONL] 共 {line_count} 条日志，路径：{output_path}\n"
        f"请严格按 .claude/skills/issue-diagnosis/references/log-analysis.md 中的「查询后处理」和「日志读取规则」继续处理。"
    )

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
