#!/usr/bin/env python
"""非交互式 eval 运行脚本，用于测试 issue-diagnosis skill"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv('.env')

from api.dependencies import get_agent_service
from cli.state import REPLState

logging.disable(logging.CRITICAL)

SKILL = "issue-diagnosis"
OUTPUT_BASE = Path("agent_cwd/.claude/skills/issue-diagnosis-workspace/iteration-7")

EVALS = [
    {
        "id": 15,
        "name": "traceid-compliance-check",
        "prompt": "测试环境，traceid：116fac6019e35720，帮我看下对应校验了哪些税务和名单",
    },
]


async def run_eval(eval_item: dict, with_skill: bool):
    agent_service = get_agent_service()
    state = REPLState(skill=SKILL if with_skill else "")

    tag = "with_skill" if with_skill else "without_skill"
    out_dir = OUTPUT_BASE / eval_item["name"] / tag / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    request = state.build_request(eval_item["prompt"])

    output_parts = []
    tool_calls = []

    print(f"\n{'='*60}")
    print(f"[{tag}] 场景 {eval_item['id']}: {eval_item['name']}")
    print(f"{'='*60}")

    try:
        async for message in agent_service.process_query(request):
            event_type = message.get("event")
            data = message.get("data")

            if event_type == "heartbeat":
                continue

            try:
                data_obj = json.loads(data) if isinstance(data, str) else data
            except (json.JSONDecodeError, TypeError):
                data_obj = {"raw": data}

            if event_type == "assistant_message":
                content = data_obj.get("content", "")
                if content:
                    print(content, end="", flush=True)
                    output_parts.append(content)

            elif event_type == "tool_use":
                tool_name = data_obj.get("name", "")
                tool_calls.append(tool_name)
                print(f"\n[工具调用: {tool_name}]", flush=True)

            elif event_type == "result":
                print(f"\n[完成]", flush=True)

            elif event_type == "error":
                print(f"\n[错误: {data_obj}]", flush=True)

    except Exception as e:
        print(f"\n[异常: {e}]", flush=True)

    # 保存输出
    full_output = "".join(output_parts)
    transcript = f"# {tag} - 场景 {eval_item['id']}: {eval_item['name']}\n\n"
    transcript += f"## 用户问题\n{eval_item['prompt']}\n\n"
    transcript += f"## 工具调用\n" + "\n".join(f"- {t}" for t in tool_calls) + "\n\n"
    transcript += f"## 最终输出\n{full_output}\n"

    (out_dir / "output.md").write_text(full_output, encoding="utf-8")
    (out_dir / "transcript.md").write_text(transcript, encoding="utf-8")
    print(f"\n已保存到 {out_dir}")


async def main():
    target = next((e for e in EVALS if e["id"] == 15), None)
    if target:
        await run_eval(target, with_skill=True)


if __name__ == "__main__":
    asyncio.run(main())
