#!/usr/bin/env python
"""
双环境并行测试脚本 - 同一批问题同时跑测试环境和正式环境，自动评分并对比

Usage:
    python tests/compare_envs.py
    python tests/compare_envs.py --no-score   # 只跑测试，跳过评分和对比
"""

import asyncio
import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from tests.batch_test import (
    parse_test_questions,
    run_batch_tests,
    save_results,
    MarkdownWriter,
)


async def run_env(label: str, url: str, path: str, questions: list[str],
                  concurrency: int, timeout: float, output_dir: Path) -> Path:
    print(f"\n[{label}] 开始测试 {len(questions)} 条问题 → {url}{path}")
    md_writer = MarkdownWriter(output_dir, f"qa_{label}")
    results = await run_batch_tests(
        questions=questions,
        concurrency=concurrency,
        timeout=timeout,
        md_writer=md_writer,
        url=url,
        path=path,
    )
    json_path = save_results(results, output_dir, f"qa_{label}", md_writer=md_writer)
    print(f"[{label}] 结果已保存: {json_path}")
    return json_path


def score_file(json_path: Path) -> Path:
    scored_path = json_path.with_suffix("").with_suffix(".scored.json")
    if scored_path.exists():
        print(f"跳过评分（已存在）: {scored_path.name}")
        return scored_path
    print(f"\n评分: {json_path.name}")
    subprocess.run(
        [sys.executable, "tests/score_results.py", str(json_path)],
        check=True,
        cwd=PROJECT_ROOT,
    )
    return scored_path


def compare(baseline: Path, candidate: Path):
    print()
    subprocess.run(
        [sys.executable, "tests/compare_runs.py", str(baseline), str(candidate)],
        check=True,
        cwd=PROJECT_ROOT,
    )


async def main():
    STAGING_URL  = "http://123.207.158.7:9123"
    PROD_URL     = "https://ai-tmp.piaozone.com"
    API_PATH     = "/zhichi/ask"
    INPUT_FILE   = "tests/qa/qa_questions.md"
    CONCURRENCY  = 1
    TIMEOUT      = 600.0
    OUTPUT_DIR   = "tests/results"

    parser = argparse.ArgumentParser(description="双环境并行测试 + 自动对比")
    parser.add_argument("--no-score", action="store_true", help="跳过评分和对比步骤")
    args = parser.parse_args()

    input_path = PROJECT_ROOT / INPUT_FILE
    if not input_path.exists():
        print(f"错误: 问题文件不存在 {input_path}")
        sys.exit(1)

    questions = parse_test_questions(str(input_path))
    if not questions:
        print("错误: 未找到有效问题")
        sys.exit(1)

    output_dir = PROJECT_ROOT / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"问题数: {len(questions)}")
    print(f"测试环境: {STAGING_URL}")
    print(f"正式环境: {PROD_URL}")
    print(f"并发数: {CONCURRENCY}")

    # 两个环境并行跑
    staging_json, prod_json = await asyncio.gather(
        run_env("staging", STAGING_URL, API_PATH, questions, CONCURRENCY, TIMEOUT, output_dir),
        run_env("prod",    PROD_URL,    API_PATH, questions, CONCURRENCY, TIMEOUT, output_dir),
    )

    if args.no_score:
        print(f"\n结果文件:\n  staging: {staging_json}\n  prod:    {prod_json}")
        return

    # 评分（串行，避免 LLM 并发过高）
    staging_scored = score_file(staging_json)
    prod_scored    = score_file(prod_json)

    # 对比（staging 为基准，prod 为候选）
    compare(staging_scored, prod_scored)


if __name__ == "__main__":
    asyncio.run(main())
