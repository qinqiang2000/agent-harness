#!/usr/bin/env python
"""
提案应用脚本 - 将人工审核通过的 SKILL.md 改进提案自动应用

Usage:
    python scripts/apply_proposal.py log/proposals/20260323_proposals.md

工作流:
    1. 解析 proposals.md，找到所有 "Action: APPROVE" 的提案
    2. 对每个提案，将 CURRENT_TEXT 替换为 PROPOSED_TEXT
    3. 更新 SKILL.md
    4. git commit（附带提案统计信息）

注意: 脚本只处理 "Action: APPROVE" 标注的提案
"""

import re
import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SKILL_MD_PATH = PROJECT_ROOT / "agent_cwd" / ".claude" / "skills" / "customer-service" / "SKILL.md"


def parse_approved_proposals(proposals_md: str) -> list[dict]:
    """解析提案文件，提取所有 APPROVE 的提案"""
    proposals = []

    # 按 Proposal 章节分割
    sections = re.split(r'\n## Proposal \d+:', proposals_md)

    for section in sections[1:]:  # 跳过第一个（概况部分）
        # 检查是否有 APPROVE 标记
        action_match = re.search(r'\*\*Action:\*\*[^\n]*APPROVE', section, re.IGNORECASE)
        if not action_match:
            continue

        # 提取各字段
        current_match = re.search(
            r'CURRENT_TEXT:\s*(.+?)(?=PROPOSED_TEXT:|$)',
            section,
            re.DOTALL
        )
        proposed_match = re.search(
            r'PROPOSED_TEXT:\s*(.+?)(?=RATIONALE:|CONFIDENCE:|Action:|$)',
            section,
            re.DOTALL
        )
        rationale_match = re.search(
            r'RATIONALE:\s*(.+?)(?=CONFIDENCE:|Action:|$)',
            section,
            re.DOTALL
        )

        if not current_match or not proposed_match:
            print(f"  警告: 提案格式不完整，跳过:\n{section[:200]}")
            continue

        current_text = current_match.group(1).strip()
        proposed_text = proposed_match.group(1).strip()
        rationale = rationale_match.group(1).strip() if rationale_match else ""

        # 去除可能的 markdown 代码块标记
        for text_var in [current_text, proposed_text]:
            if text_var.startswith("```") or text_var.startswith("`"):
                text_var = re.sub(r'^```[^\n]*\n?', '', text_var)
                text_var = re.sub(r'\n?```$', '', text_var)

        proposals.append({
            "current_text": current_text,
            "proposed_text": proposed_text,
            "rationale": rationale,
        })

    return proposals


def apply_proposals_to_skill(proposals: list[dict], skill_content: str) -> tuple[str, list[str]]:
    """将提案应用到 SKILL.md 内容"""
    applied = []
    failed = []
    updated = skill_content

    for i, p in enumerate(proposals, 1):
        current = p["current_text"]
        proposed = p["proposed_text"]

        if current in updated:
            updated = updated.replace(current, proposed, 1)
            applied.append(f"提案{i}: {current[:60]}...")
            print(f"  ✅ 提案{i} 应用成功")
        else:
            failed.append(f"提案{i}: 未找到目标文本 '{current[:60]}...'")
            print(f"  ❌ 提案{i} 失败: 未在 SKILL.md 中找到目标文本")
            print(f"     目标文本前50字: {current[:50]}")

    return updated, applied + (["失败: " + f for f in failed] if failed else [])


def git_commit_skill(applied_summaries: list[str], proposal_file: Path) -> bool:
    """git commit SKILL.md 变更"""
    try:
        # 暂存 SKILL.md
        subprocess.run(
            ["git", "add", str(SKILL_MD_PATH.relative_to(PROJECT_ROOT))],
            cwd=PROJECT_ROOT, check=True, capture_output=True
        )

        # 检查是否有变更
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        if not result.stdout.strip():
            print("  没有 SKILL.md 变更需要提交")
            return False

        # 构建提交信息
        date_str = datetime.now().strftime("%Y-%m-%d")
        summary_lines = "\n".join([f"  - {s}" for s in applied_summaries])
        commit_msg = (
            f"skill(customer-service): 应用 {len(applied_summaries)} 个改进提案 [{date_str}]\n\n"
            f"来源: {proposal_file.name}\n"
            f"改动:\n{summary_lines}\n\n"
            f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
        )

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=PROJECT_ROOT, check=True, capture_output=True
        )

        # 获取新的 commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        print(f"  ✅ git commit 完成: {hash_result.stdout.strip()}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"  ❌ git commit 失败: {e.stderr.decode() if e.stderr else e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="应用人工审核通过的 SKILL.md 改进提案")
    parser.add_argument("proposals_file", help="提案文件路径（proposals.md）")
    parser.add_argument("--dry-run", action="store_true", help="预览改动，不实际写入")
    args = parser.parse_args()

    proposals_path = Path(args.proposals_file)
    if not proposals_path.exists():
        print(f"错误: 文件不存在 {proposals_path}")
        sys.exit(1)

    if not SKILL_MD_PATH.exists():
        print(f"错误: SKILL.md 不存在 {SKILL_MD_PATH}")
        sys.exit(1)

    print(f"读取提案文件: {proposals_path.name}")
    proposals_md = proposals_path.read_text(encoding="utf-8")
    proposals = parse_approved_proposals(proposals_md)

    if not proposals:
        print("未找到 'Action: APPROVE' 的提案。")
        print("请在提案文件中将 [ ] APPROVE 改为 [x] APPROVE 或 Action: APPROVE")
        sys.exit(0)

    print(f"找到 {len(proposals)} 个待应用的提案\n")

    skill_content = SKILL_MD_PATH.read_text(encoding="utf-8")
    updated_content, summaries = apply_proposals_to_skill(proposals, skill_content)

    if args.dry_run:
        print("\n[DRY RUN] 预览改动（未写入文件）:")
        for s in summaries:
            print(f"  {s}")
        return

    # 写入 SKILL.md
    SKILL_MD_PATH.write_text(updated_content, encoding="utf-8")
    print(f"\nSKILL.md 已更新: {SKILL_MD_PATH}")

    # git commit
    applied = [s for s in summaries if not s.startswith("失败")]
    if applied:
        git_commit_skill(applied, proposals_path)

    print("\n下一步: 运行批量测试验证改进效果")
    print(f"  python tests/batch_test.py tests/dataset/golden_set.jsonl --concurrency 3")
    print(f"  python tests/score_results.py tests/results/golden_set_<timestamp>.json")


if __name__ == "__main__":
    main()
