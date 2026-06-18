#!/usr/bin/env python3
"""
PostToolUse hook: ELK 查询完成后自动将大结果转为 JSONL。
两种场景统一处理：
1. 结果直接返回且超过阈值 → 写临时文件后转换
2. 结果被 persisted-output 截断 → 直接读 tool-results 文件转换
转换后通过 updatedToolOutput 替换 Agent 收到的内容，输出 JSONL 与原始文件同目录。
"""

import json
import logging
import os
import subprocess
import sys
import uuid

LOG_FILE = "/tmp/auto-parse-elk-result.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Read 工具上限约 25000 tokens，按 4 字符/token 换算
SIZE_THRESHOLD = 100_000
MCP_RESULT_PREFIX = "mcp-elastic-searchTraceOrKeyWordsLog-"


def find_elk_result_file(transcript_path: str, session_id: str) -> str | None:
    """从 tool-results 目录找 ELK 结果文件，优先按文件名前缀匹配，退路用 mtime 最新。"""
    tool_results_dir = os.path.join(
        os.path.dirname(transcript_path), session_id, "tool-results"
    )
    if not os.path.isdir(tool_results_dir):
        return None
    named = [
        os.path.join(tool_results_dir, f)
        for f in os.listdir(tool_results_dir)
        if f.startswith(MCP_RESULT_PREFIX)
    ]
    if named:
        return max(named, key=os.path.getmtime)
    all_files = [
        os.path.join(tool_results_dir, f)
        for f in os.listdir(tool_results_dir)
        if f.endswith((".txt", ".json"))
    ]
    return max(all_files, key=os.path.getmtime) if all_files else None


def convert_to_jsonl(
    input_path: str, output_path: str, script: str, session_id: str
) -> int | str:
    """调用 parse_logs.py 转换，返回行数或 '未知'。"""
    try:
        subprocess.run(
            [sys.executable, script, "--input", input_path, "--output", output_path],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        logging.error("parse_logs.py failed: %s, session=%s", e, session_id)
        return 0
    try:
        with open(output_path, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return "未知"


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        logging.error("failed to parse hook event JSON")
        return

    if event.get("tool_name") != "mcp__elastic__searchTraceOrKeyWordsLog":
        return

    session_id = event.get("session_id", "")
    transcript_path = event.get("transcript_path", "")

    tool_response = event.get("tool_response", [])
    text = ""
    if tool_response and isinstance(tool_response[0], dict):
        text = tool_response[0].get("text", "")

    log_event = {k: v for k, v in event.items() if k != "tool_response"}
    log_event["tool_response_text_len"] = len(text)
    log_event["tool_response_text_preview"] = text[:200]
    logging.info("hook triggered: %s", json.dumps(log_event, ensure_ascii=False))

    is_truncated = not text or "persisted-output" in text or "Output too large" in text

    script = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "../skills/issue-diagnosis-billing/scripts/parse_logs.py",
        )
    )

    if is_truncated:
        # 结果被截断：从 tool-results 找原始文件直接转换
        input_path = find_elk_result_file(transcript_path, session_id)
        if not input_path:
            logging.warning(
                "persisted-output detected but tool-results file not found, session=%s",
                session_id,
            )
            return
        output_path = os.path.join(
            os.path.dirname(input_path), f"{uuid.uuid4().hex}.jsonl"
        )
        logging.info(
            "persisted-output detected, input=%s, session=%s", input_path, session_id
        )
        line_count = convert_to_jsonl(input_path, output_path, script, session_id)
    else:
        # 结果直接返回：按长度判断是否需要转换
        if len(text) < SIZE_THRESHOLD:
            logging.info(
                "result size=%d below threshold, skip. session=%s",
                len(text),
                session_id,
            )
            return
        # 写临时输入文件，输出放到 tool-results 目录
        tool_results_dir = os.path.join(
            os.path.dirname(transcript_path), session_id, "tool-results"
        )
        os.makedirs(tool_results_dir, exist_ok=True)
        input_path = os.path.join(tool_results_dir, f"elk_raw_{uuid.uuid4().hex}.json")
        output_path = os.path.join(tool_results_dir, f"{uuid.uuid4().hex}.jsonl")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(text)
        line_count = convert_to_jsonl(input_path, output_path, script, session_id)
        if os.path.exists(input_path):
            os.unlink(input_path)

    if not line_count:
        return

    logging.info(
        "converted to JSONL: lines=%s, output=%s, session=%s",
        line_count,
        output_path,
        session_id,
    )

    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "updatedToolOutput": [
                        {
                            "type": "text",
                            "text": (
                                f"[系统已自动将 ELK 查询结果转为 JSONL，无需再次运行 parse_logs.py] 共 {line_count} 条日志，路径：{output_path}\n"
                                f"请直接按 .claude/skills/issue-diagnosis-billing/references/log-analysis.md 中的「日志读取规则」规则分析日志文件，日志条数少时直接读取即可,多的时候用 Bash grep 对上述 JSONL 文件进行分析。"
                            ),
                        }
                    ],
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
