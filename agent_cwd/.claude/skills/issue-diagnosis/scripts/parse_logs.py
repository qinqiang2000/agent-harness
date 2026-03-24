#!/usr/bin/env python3
"""将 MCP 工具 mcp__elastic__searchTraceOrKeyWordsLog 返回的大 JSON 转换为 JSONL。

MCP 返回格式：
  {"content": [{"type": "text", "text": "<日志JSON字符串>"}], "isError": false}

输出格式：每条日志占一行（JSONL），写入指定文件或 stdout。

用法：
  # 从文件读取 MCP 返回内容，输出到临时文件
  python3 scripts/parse_logs.py --input /tmp/mcp_raw.json --output /tmp/logs.jsonl

  # 从 stdin 读取，输出到文件
  echo '<mcp json>' | python3 scripts/parse_logs.py --output /tmp/logs.jsonl

  # 输出到 stdout（不指定 --output）
  python3 scripts/parse_logs.py --input /tmp/mcp_raw.json
"""

import argparse
import json
import sys


def parse(raw: str) -> list:
    """从 MCP 返回的原始字符串中提取日志列表。"""
    outer = json.loads(raw)

    # MCP tool-result 格式：[{"type": "text", "text": "<日志JSON字符串>"}, ...]
    if isinstance(outer, list) and outer and isinstance(outer[0], dict) and "text" in outer[0]:
        logs = []
        for item in outer:
            inner = json.loads(item["text"])
            if isinstance(inner, list):
                logs.extend(inner)
            else:
                logs.append(inner)
        return logs

    # 旧格式兼容：{"content": [{"type": "text", "text": "..."}], ...}
    if isinstance(outer, dict) and "content" in outer:
        text = outer["content"][0]["text"]
        inner = json.loads(text)
        if isinstance(inner, list):
            return inner
        raise ValueError(f"日志内容应为列表，实际类型：{type(inner)}")

    # 直接就是日志列表
    if isinstance(outer, list):
        return outer

    raise ValueError(f"无法识别的格式，顶层类型：{type(outer)}")


def main():
    parser = argparse.ArgumentParser(description="MCP 日志 JSON → JSONL 转换工具")
    parser.add_argument("--input", metavar="FILE", help="MCP 返回内容的文件路径（不指定则从 stdin 读取）")
    parser.add_argument("--output", metavar="FILE", help="输出 JSONL 文件路径（不指定则输出到 stdout）")
    args = parser.parse_args()

    raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()

    try:
        logs = parse(raw)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    lines = [json.dumps(entry, ensure_ascii=False) for entry in logs]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"已写入 {len(logs)} 条日志 → {args.output}", file=sys.stderr)
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
