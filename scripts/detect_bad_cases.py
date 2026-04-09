#!/usr/bin/env python
"""
Bad Case 探测脚本 - 每日从生产交互日志中识别质量问题

Usage:
    # 探测昨天的交互
    python scripts/detect_bad_cases.py

    # 探测指定日期
    python scripts/detect_bad_cases.py --date 20260323

    # 探测指定日期范围
    python scripts/detect_bad_cases.py --date 20260317 --days 7

    # 同时用 LLM 评分（消耗 API 配额，可选）
    python scripts/detect_bad_cases.py --llm-score

输出: log/bad_cases/YYYYMMDD_candidates.jsonl
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INTERACTIONS_LOG = PROJECT_ROOT / "log" / "interactions.log"
BAD_CASES_DIR = PROJECT_ROOT / "log" / "bad_cases"
BAD_CASES_DIR.mkdir(parents=True, exist_ok=True)

GOLDEN_SET_PATH = PROJECT_ROOT / "tests" / "dataset" / "golden_set.jsonl"

# 已知可回答的问题（从 golden_set.jsonl 加载，expected_product_ask=False 且产品无关的题）
def load_known_answerable() -> set[str]:
    questions = set()
    if not GOLDEN_SET_PATH.exists():
        return questions
    with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if not entry.get("expected_product_ask") and entry.get("product") is None:
                    questions.add(entry["question"])
            except json.JSONDecodeError:
                pass
    return questions


# 启发式规则：每条规则返回 (flag_name, True/False)
def apply_heuristics(r: dict, known_answerable: set[str]) -> list[str]:
    flags = []
    status = r.get("status", "success")
    answer = r.get("answer") or ""
    answer_len = r.get("answer_length", len(answer))
    num_turns = r.get("num_turns", 0)
    has_doc = r.get("has_doc_url", False)
    used_fallback = r.get("used_fallback_phrase", False)
    has_product = bool(r.get("product_selected") or r.get("asked_product_question"))
    skill = r.get("skill", "")

    # 只检测 customer-service skill
    if skill and skill != "customer-service":
        return []

    if status == "timeout":
        flags.append("timeout")

    if status == "error":
        flags.append("error_status")

    if status == "success" and answer_len < 50:
        flags.append("answer_too_short")

    if answer_len > 600:
        flags.append("answer_too_long")  # 违反 ≤300字规则

    if not has_doc and not used_fallback and has_product and status == "success" and answer_len > 50:
        flags.append("no_doc_url_suspicious")  # 疑似幻觉

    if num_turns > 12:
        flags.append("high_turn_count")  # 搜索死循环

    question = r.get("question", "")
    if used_fallback and question in known_answerable:
        flags.append("fallback_on_known_answerable")  # 可回答的问题却触发兜底

    return flags


def load_interactions(date_str: str) -> list[dict]:
    # 当天：interactions.log；历史：interactions.log.YYYY-MM-DD
    dt = datetime.strptime(date_str, "%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    if date_str == today_str:
        path = INTERACTIONS_LOG
    else:
        path = INTERACTIONS_LOG.with_suffix(f".log.{dt.strftime('%Y-%m-%d')}")
    if not path.exists():
        return []
    interactions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    interactions.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return interactions


def detect_for_date(date_str: str, known_answerable: set[str], llm_score: bool = False) -> int:
    interactions = load_interactions(date_str)
    if not interactions:
        print(f"  {date_str}: 无交互记录")
        return 0

    candidates = []
    for r in interactions:
        flags = apply_heuristics(r, known_answerable)
        if flags:
            candidates.append({
                **r,
                "heuristic_flags": flags,
                "detected_at": datetime.now().isoformat(),
            })

    print(f"  {date_str}: {len(interactions)} 条交互 → {len(candidates)} 个候选 bad case")

    if not candidates:
        return 0

    # 可选：用 LLM 评分进一步确认
    if llm_score and candidates:
        try:
            candidates = _llm_score_candidates(candidates)
        except Exception as e:
            print(f"  LLM 评分失败: {e}，仅使用启发式结果")

    out_path = BAD_CASES_DIR / f"{date_str}_candidates.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  → 已保存: {out_path.name}")
    return len(candidates)


def _llm_score_candidates(candidates: list[dict]) -> list[dict]:
    """用 LLM 对候选 bad case 评分（可选加强）"""
    import asyncio
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        import anthropic
    except ImportError:
        print("  警告: anthropic 包未安装，跳过 LLM 评分")
        return candidates

    # 复用 score_results 的逻辑
    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    from score_results import score_single_result, load_golden_set

    golden = load_golden_set(PROJECT_ROOT / "tests" / "dataset" / "golden_set.jsonl")

    async def _score_all():
        client = anthropic.AsyncAnthropic()
        results = []
        for c in candidates:
            scored = await score_single_result(client, c, golden.get(c.get("question")))
            c["llm_quality_score"] = scored.get("quality_score", -1)
            c["llm_failure_reasons"] = scored.get("failure_reasons", [])
            c["llm_confirmed_bad"] = scored.get("is_bad_case", True)
            results.append(c)
        return results

    return asyncio.run(_score_all())


def main():
    parser = argparse.ArgumentParser(description="探测生产交互中的 bad case 候选")
    parser.add_argument("--date", help="探测日期 (YYYYMMDD)，默认昨天")
    parser.add_argument("--days", type=int, default=1, help="探测天数（从 --date 往前，默认1）")
    parser.add_argument("--llm-score", action="store_true", help="同时用 LLM 评分（消耗 API 配额）")
    args = parser.parse_args()

    if args.date:
        start_date = datetime.strptime(args.date, "%Y%m%d")
    else:
        start_date = datetime.now() - timedelta(days=1)

    known_answerable = load_known_answerable()
    print(f"已知可回答题目: {len(known_answerable)} 条")
    print(f"探测日期: {args.days} 天\n")

    total_bad = 0
    for i in range(args.days):
        date = start_date - timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        total_bad += detect_for_date(date_str, known_answerable, args.llm_score)

    print(f"\n{'='*40}")
    print(f"探测完成，共发现 {total_bad} 个候选 bad case")
    print(f"结果保存在: {BAD_CASES_DIR}")
    print(f"下一步: python scripts/analyze_bad_cases.py  (每周运行)")


if __name__ == "__main__":
    main()
