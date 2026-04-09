#!/usr/bin/env python
"""
Bad Case 分析脚本 - 每周聚类分析并生成 SKILL.md 改进提案

Usage:
    # 分析过去 7 天的 bad cases，生成提案
    python scripts/analyze_bad_cases.py

    # 指定天数
    python scripts/analyze_bad_cases.py --days 14

    # 指定输出文件
    python scripts/analyze_bad_cases.py --output log/proposals/custom_proposals.md

输出: log/proposals/YYYYMMDD_proposals.md
人工审核后，运行: python scripts/apply_proposal.py <proposals_file>
"""

import asyncio
import json
import sys
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BAD_CASES_DIR = PROJECT_ROOT / "log" / "bad_cases"
PROPOSALS_DIR = PROJECT_ROOT / "log" / "proposals"
PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

SKILL_MD_PATH = PROJECT_ROOT / "agent_cwd" / ".claude" / "skills" / "customer-service" / "SKILL.md"

# 启发式标签 → 失败模式名称
HEURISTIC_PATTERN_MAP = {
    "no_doc_url_suspicious": "kb_hallucination",
    "answer_too_long": "format_violation",
    "answer_too_short": "empty_answer",
    "high_turn_count": "search_loop",
    "timeout": "timeout",
    "fallback_on_known_answerable": "wrong_fallback",
    "error_status": "system_error",
}

# 每个失败模式对应 SKILL.md 的哪个部分
PATTERN_TO_SKILL_SECTION = {
    "kb_hallucination": "CHECK 4（搜索策略执行）和 CHECK 2（能力结论）",
    "format_violation": "输出规范（≤300字限制）",
    "empty_answer": "CHECK 2（能力结论）和兜底话术",
    "search_loop": "搜索策略（最多2轮Grep，之后切换Agent）",
    "wrong_fallback": "兜底话术使用条件",
    "timeout": "搜索策略（并行工具调用）",
}

MIN_CASES_FOR_PROPOSAL = 3  # 同类 bad case 达到此数量才生成提案


def load_bad_cases(days: int) -> list[dict]:
    """加载过去 N 天的 bad case 候选"""
    cases = []
    for i in range(days):
        date = datetime.now() - timedelta(days=i+1)
        date_str = date.strftime("%Y%m%d")
        path = BAD_CASES_DIR / f"{date_str}_candidates.jsonl"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            cases.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
    return cases


def cluster_cases(cases: list[dict]) -> dict[str, list[dict]]:
    """按失败模式聚类"""
    clusters: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        flags = case.get("heuristic_flags", [])
        for flag in flags:
            pattern = HEURISTIC_PATTERN_MAP.get(flag, flag)
            clusters[pattern].append(case)
    return dict(clusters)


async def generate_proposal(
    client,
    pattern: str,
    cases: list[dict],
    skill_content: str,
) -> str | None:
    """用 LLM 为一个失败模式生成 SKILL.md 改进提案"""
    if len(cases) < MIN_CASES_FOR_PROPOSAL:
        return None

    # 取最有代表性的 5 个案例
    sample = cases[:5]
    cases_text = "\n".join([
        f"- Q: {c.get('question', '')[:100]}\n  A摘要: {(c.get('answer') or '')[:150]}...\n  标志: {c.get('heuristic_flags', [])}"
        for c in sample
    ])

    skill_section = PATTERN_TO_SKILL_SECTION.get(pattern, "相关部分")

    prompt = f"""你是发票云客服Skill的优化专家。请根据以下 bad case 分析，生成 SKILL.md 的具体改进建议。

失败模式: {pattern}
相关 SKILL.md 章节: {skill_section}
案例数量: {len(cases)} 个（以下展示 {len(sample)} 个代表性案例）

代表性 bad case:
{cases_text}

当前 SKILL.md 相关部分:
---
{skill_content[:3000]}
---

请生成最小化、具体可操作的改进建议。要求：
1. 只修改导致问题的具体段落，不做大改
2. 如果问题是规则不够具体，添加具体示例
3. 如果问题是顺序/优先级不对，调整顺序
4. 不要删除现有规则
5. 用中文输出

严格按照以下格式输出：

SECTION: [要修改的章节名称]
CURRENT_TEXT: [当前文本，引用原文]
PROPOSED_TEXT: [改进后的文本]
RATIONALE: [1-2句话解释为什么这样改能解决问题]
CONFIDENCE: [HIGH/MEDIUM/LOW]"""

    try:
        import anthropic
        msg = await client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"[生成失败: {e}]"


async def generate_proposals(clusters: dict[str, list[dict]], skill_content: str) -> list[dict]:
    """为所有达到阈值的失败模式生成提案"""
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
        import anthropic
        client = anthropic.AsyncAnthropic()
    except ImportError:
        print("警告: anthropic 包未安装，跳过 LLM 提案生成")
        return []

    proposals = []
    for pattern, cases in sorted(clusters.items(), key=lambda x: -len(x[1])):
        if len(cases) < MIN_CASES_FOR_PROPOSAL:
            print(f"  跳过 {pattern}: {len(cases)} 个案例（不足 {MIN_CASES_FOR_PROPOSAL} 个）")
            continue

        print(f"  生成提案: {pattern} ({len(cases)} 个案例)...")
        proposal_text = await generate_proposal(client, pattern, cases, skill_content)
        if proposal_text:
            proposals.append({
                "pattern": pattern,
                "case_count": len(cases),
                "proposal_text": proposal_text,
                "representative_cases": [c.get("question", "") for c in cases[:3]],
            })

    return proposals


def write_proposals_md(proposals: list[dict], clusters: dict, output_path: Path):
    """将提案写入人工可审核的 Markdown 文件"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_cases = sum(len(v) for v in clusters.values())

    lines = [
        f"# SKILL.md 改进提案 - {now}",
        "",
        "## 概况",
        f"- 分析 bad case 总数: {total_cases}",
        f"- 发现失败模式: {len(clusters)} 种",
        f"- 生成提案数: {len(proposals)} 个（每种 ≥{MIN_CASES_FOR_PROPOSAL} 个案例才生成）",
        "",
        "## 审核说明",
        "请在每个提案末尾标注决定：",
        "- `Action: APPROVE` - 接受，将由 apply_proposal.py 自动应用",
        "- `Action: REJECT` - 拒绝",
        "- `Action: MODIFY: <你的修改>` - 手动修改后再接受",
        "",
        "审核完成后运行:",
        f"```bash",
        f"python scripts/apply_proposal.py {output_path}",
        f"```",
        "",
        "---",
        "",
    ]

    if not proposals:
        lines.append("本次分析未发现达到阈值的失败模式，无需修改 SKILL.md。")
    else:
        for i, p in enumerate(proposals, 1):
            pattern = p["pattern"]
            count = p["case_count"]
            cases_preview = p["representative_cases"]
            proposal_text = p["proposal_text"]

            lines += [
                f"## Proposal {i}: {pattern} ({count} 个 bad case)",
                "",
                "**代表性问题:**",
            ]
            for q in cases_preview:
                lines.append(f"- {q[:80]}")

            lines += [
                "",
                "**LLM 分析与建议:**",
                "",
                proposal_text,
                "",
                "**Action:** [ ] APPROVE  [ ] REJECT  [ ] MODIFY:",
                "",
                "---",
                "",
            ]

    # 附录：各模式统计
    lines += [
        "## 附录：失败模式统计",
        "",
        "| 模式 | 案例数 | 相关SKILL章节 |",
        "|------|-------|--------------|",
    ]
    for pattern, cases in sorted(clusters.items(), key=lambda x: -len(x[1])):
        section = PATTERN_TO_SKILL_SECTION.get(pattern, "-")
        lines.append(f"| {pattern} | {len(cases)} | {section} |")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✅ 提案已保存: {output_path}")
    print(f"   请人工审核后运行: python scripts/apply_proposal.py {output_path}")


async def main_async(days: int, output_path: Path | None):
    print(f"加载过去 {days} 天的 bad case 候选...")
    cases = load_bad_cases(days)
    print(f"共加载 {len(cases)} 个 bad case\n")

    if not cases:
        print("无 bad case 数据。请先运行: python scripts/detect_bad_cases.py")
        return

    clusters = cluster_cases(cases)
    print(f"失败模式聚类结果:")
    for pattern, c in sorted(clusters.items(), key=lambda x: -len(x[1])):
        print(f"  {pattern}: {len(c)} 个")

    # 读取 SKILL.md
    skill_content = ""
    if SKILL_MD_PATH.exists():
        skill_content = SKILL_MD_PATH.read_text(encoding="utf-8")

    print(f"\n生成提案...")
    proposals = await generate_proposals(clusters, skill_content)

    if not output_path:
        date_str = datetime.now().strftime("%Y%m%d")
        output_path = PROPOSALS_DIR / f"{date_str}_proposals.md"

    write_proposals_md(proposals, clusters, output_path)


def main():
    parser = argparse.ArgumentParser(description="分析 bad case 并生成 SKILL.md 改进提案")
    parser.add_argument("--days", type=int, default=7, help="分析天数（默认7天）")
    parser.add_argument("--output", help="输出文件路径（默认: log/proposals/YYYYMMDD_proposals.md）")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else None
    asyncio.run(main_async(args.days, output_path))


if __name__ == "__main__":
    main()
