#!/usr/bin/env python
"""
LLM 评分脚本 - 对 batch_test.py 生成的结果 JSON 进行质量评分

Usage:
    python tests/score_results.py tests/results/test_set_1_20260323_120000.json
    python tests/score_results.py tests/results/golden_set_20260323_*.json

评分维度（对应 SKILL.md 的 4 个 CHECK）:
    product_id       - 产品识别是否正确（Step 0）
    kb_grounded      - 答案有知识库依据、无幻觉（CHECK 1 + CHECK 4）
    accuracy         - 事实内容是否正确（CHECK 2）
    format           - 输出格式：结论前置、≤300字、无内部流程泄漏
    missing_handling - 知识库无答案时使用正确兜底话术

综合分 = 加权求和 / 10（0-10分），< 6.0 视为 bad case
"""

import asyncio
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

try:
    import anthropic
except ImportError:
    print("错误: 请安装 anthropic 包: pip install anthropic")
    sys.exit(1)


JUDGE_SYSTEM = "你是发票云客服AI的质量评估专家。严格按照评分标准评分，只输出JSON，不输出其他内容。"

JUDGE_PROMPT_TEMPLATE = """评估以下发票云客服AI的回答质量。

问题: {question}
产品上下文: {product}

AI回答:
---
{answer}
---
{gold_section}

请从以下5个维度打分，每维度0-3分（-1表示不适用）：

[product_id] 产品识别是否正确？
  3=正确识别产品并基于该产品作答/问题无歧义正确处理；2=轻微偏差；1=用错产品或不该问却问了；0=无视产品差异
  不适用(-1)：问题明确无产品歧义（如税务政策、通用API问题）

[kb_grounded] 答案是否有知识库依据（无幻觉）？
  3=包含具体文档链接(yuque等)；2=明显引用KB内容、有依据；1=模糊引用；0=无KB依据或编造内容

[accuracy] 事实内容是否正确？
  3=完全正确；2=基本正确有小错；1=部分正确；0=错误或误导
  {accuracy_note}

[format] 输出格式是否符合要求？
  要求：结论前置、简洁（≤300字）、无内部流程/CHECK标签泄漏到输出
  3=完全符合；2=1处问题；1=2处问题；0=3处或以上问题

[missing_handling] 当知识库无答案时，是否使用正确兜底话术？
  正确话术："抱歉,在发票云知识库没找到本答案,请联系发票云人工客服做支持。"
  3=使用了精确话术；2=适当拒绝但话术不标准；1=含糊应答；0=编造答案或给出不确定内容
  不适用(-1)：知识库有答案的情况

只输出JSON：
{{"product_id": N, "kb_grounded": N, "accuracy": N, "format": N, "missing_handling": N, "failure_reasons": ["原因1", "原因2"]}}
"""

FALLBACK_PHRASE = "抱歉,在发票云知识库没找到本答案"

WEIGHTS = {
    "kb_grounded": 3,
    "accuracy": 3,
    "product_id": 2,
    "format": 1,
    "missing_handling": 1,
}


def compute_quality_score(scores: dict) -> float:
    """加权计算综合分（0-10），跳过不适用维度（-1）"""
    total_weight = 0
    weighted_sum = 0
    for key, weight in WEIGHTS.items():
        score = scores.get(key, -1)
        if score >= 0:
            weighted_sum += score * weight
            total_weight += weight * 3  # 每维度满分 3
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight * 10, 2)


def build_judge_prompt(result: dict, golden_entry: dict | None) -> str:
    product = result.get("product_selected") or "未指定"
    answer = (result.get("answer") or "").strip()

    if golden_entry and golden_entry.get("gold_answer"):
        gold_section = f"标准答案:\n---\n{golden_entry['gold_answer']}\n---\n评估注意: {golden_entry.get('evaluation_notes', '')}"
        accuracy_note = "（有标准答案，请严格对比）"
    else:
        gold_section = "（无标准答案，请基于发票云领域知识和KB一致性判断）"
        accuracy_note = "（无标准答案，根据逻辑一致性和KB证据判断）"

    return JUDGE_PROMPT_TEMPLATE.format(
        question=result.get("question", ""),
        product=product,
        answer=answer[:3000],
        gold_section=gold_section,
        accuracy_note=accuracy_note,
    )


def load_golden_set(golden_path: Path) -> dict:
    """加载 golden set，返回 question -> entry 字典"""
    golden = {}
    if not golden_path.exists():
        return golden
    with open(golden_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    golden[entry["question"]] = entry
                except json.JSONDecodeError:
                    pass
    return golden


async def score_single_result(
    client: "anthropic.AsyncAnthropic",
    result: dict,
    golden_entry: dict | None,
) -> dict:
    """对单个结果进行 LLM 评分"""
    # 无答案直接给 0 分
    if not result.get("answer") and result.get("status") in ("error", "timeout"):
        scores = {"product_id": 0, "kb_grounded": 0, "accuracy": 0, "format": 0, "missing_handling": 0}
        return {
            **result,
            "scores": scores,
            "quality_score": 0.0,
            "failure_reasons": [f"status={result.get('status')}, 无答案"],
            "is_bad_case": True,
        }

    prompt = build_judge_prompt(result, golden_entry)

    try:
        msg = await client.messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # 处理 markdown 代码块包裹
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        scores_raw = json.loads(raw.strip())
        failure_reasons = scores_raw.pop("failure_reasons", [])
        quality_score = compute_quality_score(scores_raw)
        return {
            **result,
            "scores": scores_raw,
            "quality_score": quality_score,
            "failure_reasons": failure_reasons,
            "is_bad_case": quality_score < 6.0,
        }
    except Exception as e:
        return {
            **result,
            "scores": {},
            "quality_score": -1.0,
            "failure_reasons": [f"评分错误: {e}"],
            "is_bad_case": True,
        }


async def score_file(input_path: Path, concurrency: int = 3) -> Path:
    """对一个结果 JSON 文件进行批量评分"""
    print(f"\n📊 评分: {input_path.name}")

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    # 支持带 _meta 的格式和纯列表格式
    meta = {}
    if isinstance(data, dict):
        meta = data.get("_meta", {})
        results = data.get("results", [])
    else:
        results = data

    print(f"  题目数: {len(results)}")

    # 加载 golden set（可选）
    golden_path = input_path.parent.parent / "dataset" / "golden_set.jsonl"
    golden = load_golden_set(golden_path)
    if golden:
        print(f"  Golden set: {len(golden)} 条（有标准答案的题目将更精准评分）")

    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(concurrency)

    async def score_with_sem(idx: int, result: dict) -> dict:
        async with semaphore:
            golden_entry = golden.get(result.get("question"))
            scored = await score_single_result(client, result, golden_entry)
            q_short = (result.get("question") or "")[:45]
            qs = scored["quality_score"]
            score_str = f"{qs:.1f}" if qs >= 0 else "ERR"
            bad_mark = " ⚠" if scored["is_bad_case"] else ""
            print(f"  [{idx+1:2d}] {score_str}/10{bad_mark}  {q_short}...")
            return scored

    scored_results = await asyncio.gather(
        *[score_with_sem(i, r) for i, r in enumerate(results)]
    )

    # 统计
    valid = [r for r in scored_results if r["quality_score"] >= 0]
    bad = [r for r in valid if r["is_bad_case"]]
    avg_score = sum(r["quality_score"] for r in valid) / len(valid) if valid else 0

    print(f"\n  {'='*40}")
    print(f"  平均分: {avg_score:.2f}/10")
    print(f"  Bad cases: {len(bad)}/{len(valid)} ({len(bad)/len(valid)*100:.0f}%)" if valid else "  无有效结果")

    # 按维度统计
    for dim in ["product_id", "kb_grounded", "accuracy", "format", "missing_handling"]:
        dim_scores = [r["scores"].get(dim, -1) for r in valid if r.get("scores")]
        applicable = [s for s in dim_scores if s >= 0]
        if applicable:
            avg_dim = sum(applicable) / len(applicable)
            print(f"  {dim:<20}: {avg_dim:.2f}/3")

    # 保存
    output = {
        "_meta": {
            **meta,
            "scored_at": datetime.now().isoformat(),
            "avg_quality_score": avg_score,
            "bad_case_count": len(bad),
            "total": len(scored_results),
        },
        "results": list(scored_results),
    }
    out_path = input_path.with_suffix("").with_suffix(".scored.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ 已保存: {out_path.name}")
    return out_path


async def main():
    parser = argparse.ArgumentParser(description="对 batch_test 结果进行 LLM 质量评分")
    parser.add_argument("input_files", nargs="+", help="结果 JSON 文件路径")
    parser.add_argument("--concurrency", "-c", type=int, default=3, help="并发评分数（默认3）")
    args = parser.parse_args()

    for file_str in args.input_files:
        p = Path(file_str)
        if p.suffix == ".json" and ".scored" not in p.name:
            await score_file(p, args.concurrency)
        else:
            print(f"跳过: {file_str}（已是 scored 文件或非 JSON）")


if __name__ == "__main__":
    asyncio.run(main())
