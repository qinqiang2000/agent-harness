#!/usr/bin/env python
"""
从生产 interactions.log 提取多轮对话测试用例

Usage:
    # 提取今天的多轮对话
    python scripts/extract_test_cases.py

    # 指定日期
    python scripts/extract_test_cases.py --date 2026-04-10

    # 只提取包含 AskUserQuestion 的多轮对话
    python scripts/extract_test_cases.py --ask-user-only

    # 指定输出文件
    python scripts/extract_test_cases.py --output tests/dataset/prod_multi_turn.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "log"
DATASET_DIR = PROJECT_ROOT / "tests" / "dataset"


def load_interactions(log_path: Path) -> list[dict]:
    """加载 interactions.log，返回所有记录"""
    records = []
    if not log_path.exists():
        return records
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def find_log_files(target_date: date) -> list[Path]:
    """找到指定日期的 log 文件（当天用 interactions.log，历史用 interactions.log.YYYY-MM-DD）"""
    today = date.today()
    paths = []
    if target_date == today:
        p = LOG_DIR / "interactions.log"
        if p.exists():
            paths.append(p)
    else:
        p = LOG_DIR / f"interactions.log.{target_date.isoformat()}"
        if p.exists():
            paths.append(p)
    return paths


def extract_sessions(records: list[dict], target_date: date) -> dict[str, list[dict]]:
    """按 session_id 分组，过滤指定日期"""
    sessions: dict[str, list[dict]] = defaultdict(list)
    date_str = target_date.isoformat()
    for r in records:
        ts = r.get("timestamp", "")
        if not ts.startswith(date_str):
            continue
        sid = r.get("session_id")
        if not sid:
            continue
        sessions[sid].append(r)
    # 按时间排序
    for sid in sessions:
        sessions[sid].sort(key=lambda x: x.get("timestamp", ""))
    return sessions


def build_test_case(sid: str, turns: list[dict]) -> dict:
    """将一组 turns 转换为测试用例格式"""
    case_turns = []
    for t in turns:
        case_turns.append({
            "prompt": t.get("question", ""),
            "expected_ask_user": t.get("asked_user_question", False),
            # 保留原始元数据供参考
            "_meta": {
                "duration_ms": t.get("duration_ms"),
                "num_turns": t.get("num_turns"),
                "status": t.get("status"),
                "used_fallback_phrase": t.get("used_fallback_phrase"),
                "product_selected": t.get("product_selected"),
                "timestamp": t.get("timestamp"),
            }
        })
    return {
        "id": f"prod-{sid[:8]}",
        "session_id_ref": sid,
        "turns": case_turns,
        "source": "production",
        "date": turns[0].get("timestamp", "")[:10] if turns else "",
    }


def main():
    parser = argparse.ArgumentParser(description="从生产日志提取多轮对话测试用例")
    parser.add_argument("--date", default=date.today().isoformat(), help="目标日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--ask-user-only", action="store_true", help="只提取包含 AskUserQuestion 的多轮对话")
    parser.add_argument("--min-turns", type=int, default=1, help="最少轮数（默认1，即包含单轮）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 tests/dataset/prod_YYYY-MM-DD.jsonl）")
    args = parser.parse_args()

    try:
        target_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"日期格式错误: {args.date}，请使用 YYYY-MM-DD")
        sys.exit(1)

    log_files = find_log_files(target_date)
    if not log_files:
        print(f"未找到 {target_date} 的日志文件")
        sys.exit(1)

    all_records = []
    for p in log_files:
        all_records.extend(load_interactions(p))
    print(f"加载 {len(all_records)} 条记录（来自 {len(log_files)} 个文件）")

    sessions = extract_sessions(all_records, target_date)
    print(f"共 {len(sessions)} 个 session")

    # 过滤
    cases = []
    for sid, turns in sessions.items():
        # 排除 status=error 的单轮（噪音）
        if len(turns) == 1 and turns[0].get("status") == "error":
            continue
        if len(turns) < args.min_turns:
            continue
        if args.ask_user_only and not any(t.get("asked_user_question") for t in turns):
            continue
        cases.append(build_test_case(sid, turns))

    print(f"提取 {len(cases)} 个测试用例（多轮: {sum(1 for c in cases if len(c['turns']) > 1)}，单轮: {sum(1 for c in cases if len(c['turns']) == 1)}）")

    if not cases:
        print("没有符合条件的测试用例")
        sys.exit(0)

    # 输出
    output_path = Path(args.output) if args.output else DATASET_DIR / f"prod_{target_date.isoformat()}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"已保存: {output_path}")


if __name__ == "__main__":
    main()
