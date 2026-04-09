#!/usr/bin/env python
"""
A/B 对比脚本 - 比较两次 score_results.py 处理后的结果

Usage:
    python tests/compare_runs.py tests/results/baseline.scored.json tests/results/candidate.scored.json

决策规则（接受 SKILL.md 改动的条件）:
    ✅ 综合分提升 >= 0.5 分
    ✅ Bad case 数量不增加
    ❌ 无重大回归（任何题目分数下降 > 1.5）
"""

import json
import sys
from pathlib import Path

DIMENSION_NAMES = {
    "product_id": "产品识别",
    "kb_grounded": "KB依据",
    "accuracy": "答案准确性",
    "format": "输出格式",
    "missing_handling": "兜底处理",
}


def load_scored(path: Path) -> tuple[dict, list]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("_meta", {}), data.get("results", [])
    return {}, data


def avg_dim(results: list, dim: str) -> float | None:
    vals = [r.get("scores", {}).get(dim, -1) for r in results]
    valid = [v for v in vals if v >= 0]
    return sum(valid) / len(valid) if valid else None


def main():
    if len(sys.argv) < 3:
        print("Usage: python tests/compare_runs.py <baseline.scored.json> <candidate.scored.json>")
        sys.exit(1)

    baseline_path = Path(sys.argv[1])
    candidate_path = Path(sys.argv[2])

    for p in (baseline_path, candidate_path):
        if not p.exists():
            print(f"文件不存在: {p}")
            sys.exit(1)

    b_meta, b_results = load_scored(baseline_path)
    c_meta, c_results = load_scored(candidate_path)

    print(f"\n{'='*60}")
    print(f"A/B 对比报告")
    print(f"  基准:  {baseline_path.name}")
    b_ver = b_meta.get("skill_version", "unknown")
    c_ver = c_meta.get("skill_version", "unknown")
    print(f"         skill版本={b_ver}, 平均分={b_meta.get('avg_quality_score', '?')}")
    print(f"  候选:  {candidate_path.name}")
    print(f"         skill版本={c_ver}, 平均分={c_meta.get('avg_quality_score', '?')}")

    if b_ver != c_ver and b_ver != "unknown":
        print(f"\n  Skill 变更: {b_ver} → {c_ver}")

    print(f"\n{'维度':<14} {'基准':>8} {'候选':>8} {'变化':>14}")
    print("-" * 48)

    for dim, name in DIMENSION_NAMES.items():
        b_avg = avg_dim(b_results, dim)
        c_avg = avg_dim(c_results, dim)
        if b_avg is None or c_avg is None:
            print(f"{name:<14} {'N/A':>8} {'N/A':>8}")
            continue
        delta = c_avg - b_avg
        pct = delta / b_avg * 100 if b_avg > 0 else 0
        marker = " ★★" if abs(delta) > 0.3 else ""
        sign = "+" if delta >= 0 else ""
        print(f"{name:<14} {b_avg:>8.2f} {c_avg:>8.2f} {sign}{delta:>6.2f} ({pct:+.0f}%){marker}")

    # 综合分
    b_valid = [r for r in b_results if r.get("quality_score", -1) >= 0]
    c_valid = [r for r in c_results if r.get("quality_score", -1) >= 0]
    b_avg_q = sum(r["quality_score"] for r in b_valid) / len(b_valid) if b_valid else 0
    c_avg_q = sum(r["quality_score"] for r in c_valid) / len(c_valid) if c_valid else 0
    delta_q = c_avg_q - b_avg_q
    b_bad = sum(1 for r in b_results if r.get("is_bad_case"))
    c_bad = sum(1 for r in c_results if r.get("is_bad_case"))

    print("-" * 48)
    sign = "+" if delta_q >= 0 else ""
    print(f"{'综合分':<14} {b_avg_q:>8.2f} {c_avg_q:>8.2f} {sign}{delta_q:>6.2f}/10")
    print(f"{'Bad cases':<14} {b_bad:>8} {c_bad:>8} {c_bad-b_bad:>+8}")

    # 决策建议
    print(f"\n{'='*60}")
    print("决策建议:")
    accepts = []
    rejects = []

    if delta_q >= 0.5:
        accepts.append(f"综合分提升 {delta_q:+.2f}")
    elif delta_q < -0.3:
        rejects.append(f"综合分下降 {delta_q:.2f}")

    if c_bad < b_bad:
        accepts.append(f"Bad case 减少 {b_bad - c_bad} 个")
    elif c_bad > b_bad + 2:
        rejects.append(f"Bad case 增加 {c_bad - b_bad} 个")

    if rejects:
        print(f"  ❌ REJECT - {'; '.join(rejects)}")
    elif len(accepts) >= 1 and c_bad <= b_bad:
        print(f"  ✅ ACCEPT - {'; '.join(accepts)}")
    else:
        print(f"  ⚠️  REVIEW - 变化不显著，需人工确认")
        if accepts:
            print(f"    好的信号: {'; '.join(accepts)}")

    # 回归分析
    b_by_q = {r["question"]: r for r in b_results if r.get("question")}
    c_by_q = {r["question"]: r for r in c_results if r.get("question")}
    common = set(b_by_q.keys()) & set(c_by_q.keys())

    regressions = []
    improvements = []
    for q in common:
        b_s = b_by_q[q].get("quality_score", -1)
        c_s = c_by_q[q].get("quality_score", -1)
        if b_s < 0 or c_s < 0:
            continue
        diff = c_s - b_s
        if diff < -1.5:
            regressions.append((q, b_s, c_s, diff))
        elif diff > 1.5:
            improvements.append((q, b_s, c_s, diff))

    if regressions:
        print(f"\n  ⚠️  回归警告 (候选比基准下降 > 1.5 分):")
        for q, b_s, c_s, diff in sorted(regressions, key=lambda x: x[3])[:5]:
            print(f"     [{b_s:.1f} → {c_s:.1f} ({diff:+.1f})] {q[:55]}...")

    if improvements:
        print(f"\n  ✨ 明显改进 (候选比基准提升 > 1.5 分):")
        for q, b_s, c_s, diff in sorted(improvements, key=lambda x: -x[3])[:5]:
            print(f"     [{b_s:.1f} → {c_s:.1f} ({diff:+.1f})] {q[:55]}...")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
