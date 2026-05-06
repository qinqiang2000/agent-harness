#!/usr/bin/env python
"""
issue-diagnosis skill 集成测试脚本

对 agent 发送真实问题，验证：
1. 回复内容包含/不包含预期关键词
2. cases.md 在用户确认/否定后被正确更新

Usage:
    # 运行全部用例
    python tests/test_issue_diagnosis.py

    # 运行单条用例
    python tests/test_issue_diagnosis.py --id id-001

    # 调整超时（默认 360 秒）
    python tests/test_issue_diagnosis.py --timeout 600

结果保存在 tests/results/issue_diagnosis_*.md
"""

import asyncio
import json
import re
import sys
import argparse
import shutil
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from api.dependencies import get_agent_service
from api.models.requests import QueryRequest

CASES_MD = PROJECT_ROOT / "agent_cwd/data/issue-diagnosis/instincts/cases.md"
DATASET = PROJECT_ROOT / "tests/dataset/issue_diagnosis_test.jsonl"
RESULTS_DIR = PROJECT_ROOT / "tests/results"

CASE_FIELD_RE = re.compile(r"^- ([\w_]+): (.+)$", re.MULTILINE)
CASE_BLOCK_RE = re.compile(r"## (Case #\d+)\n(.*?)(?=\n## Case #|\Z)", re.DOTALL)


# ---------------------------------------------------------------------------
# cases.md 读取工具
# ---------------------------------------------------------------------------

def read_cases(path: Path) -> dict[str, dict]:
    """返回 {case_id: {字段: 值}} 字典。"""
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    result = {}
    for m in CASE_BLOCK_RE.finditer(content):
        case_id = m.group(1)
        fields = dict(CASE_FIELD_RE.findall(m.group(2)))
        result[case_id] = {
            "answer_confidence": float(fields.get("answer_confidence", 0)),
            "confirmed_count": int(fields.get("confirmed_count", 0)),
            "last_confirmed": fields.get("last_confirmed", "null").strip(),
            "状态": fields.get("状态", "pending_review").strip(),
        }
    return result


def count_cases(path: Path) -> int:
    if not path.exists():
        return 0
    return len(CASE_BLOCK_RE.findall(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    passed: bool
    message: str


@dataclass
class TurnResult:
    prompt: str
    answer: str
    duration_ms: float = 0


@dataclass
class CaseResult:
    id: str
    description: str
    turns: list[TurnResult] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    status: str = "pending"  # success / fail / error / timeout
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "success"

    @property
    def full_answer(self) -> str:
        return "\n---\n".join(t.answer for t in self.turns)


# ---------------------------------------------------------------------------
# Agent 调用
# ---------------------------------------------------------------------------

async def run_turns(agent_service, turns: list[dict], skill: str = "issue-diagnosis") -> list[TurnResult]:
    session_id = None
    results = []

    for i, turn in enumerate(turns):
        prompt = turn["prompt"]
        request = QueryRequest(
            tenant_id="integration-test",
            prompt=prompt,
            skill=skill,
            language="中文" if i == 0 else None,
            session_id=session_id,
            metadata={"source": "integration-test"},
        )

        answer_parts = []
        duration_ms = 0

        async for message in agent_service.process_query(request):
            event_type = message.get("event")
            data = message.get("data")
            try:
                data_obj = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError:
                data_obj = {"raw": data}

            if event_type == "session_created":
                session_id = data_obj.get("session_id")
            elif event_type == "assistant_message":
                content = data_obj.get("content", "")
                if content:
                    answer_parts.append(content)
            elif event_type == "result":
                duration_ms = data_obj.get("duration_ms", 0)
            elif event_type == "error":
                raise RuntimeError(data_obj.get("message", str(data_obj)))

        results.append(TurnResult(
            prompt=prompt,
            answer="".join(answer_parts),
            duration_ms=duration_ms,
        ))

    return results


# ---------------------------------------------------------------------------
# 校验逻辑
# ---------------------------------------------------------------------------

def run_checks(
    case_spec: dict,
    turn_results: list[TurnResult],
    cases_before: dict[str, dict],
    cases_after: dict[str, dict],
    count_before: int,
    count_after: int,
) -> list[CheckResult]:
    checks_spec = case_spec.get("checks", {})
    results = []
    full_answer = "\n".join(t.answer for t in turn_results)

    for keyword in checks_spec.get("should_contain", []):
        ok = keyword in full_answer
        results.append(CheckResult(
            passed=ok,
            message=f"should_contain '{keyword}': {'✓' if ok else '✗ 未找到'}",
        ))

    for keyword in checks_spec.get("should_not_contain", []):
        ok = keyword not in full_answer
        results.append(CheckResult(
            passed=ok,
            message=f"should_not_contain '{keyword}': {'✓' if ok else '✗ 出现了'}",
        ))

    case_update = checks_spec.get("case_update")
    if case_update:
        case_id = case_update["case_id"]
        before = cases_before.get(case_id, {})
        after = cases_after.get(case_id, {})

        if "confirmed_count_gte" in case_update:
            expected = case_update["confirmed_count_gte"]
            actual = after.get("confirmed_count", 0)
            ok = actual >= expected
            results.append(CheckResult(
                passed=ok,
                message=f"{case_id} confirmed_count >= {expected}: {'✓' if ok else f'✗ 实际={actual}'}",
            ))

        if case_update.get("answer_confidence_decreased"):
            before_ac = before.get("answer_confidence", 0)
            after_ac = after.get("answer_confidence", 0)
            ok = after_ac < before_ac or after.get("状态") == "rejected"
            results.append(CheckResult(
                passed=ok,
                message=f"{case_id} answer_confidence 降低: {'✓' if ok else f'✗ before={before_ac} after={after_ac}'}",
            ))

    if checks_spec.get("new_case_created"):
        ok = count_after > count_before
        results.append(CheckResult(
            passed=ok,
            message=f"新 case 已创建: {'✓' if ok else f'✗ before={count_before} after={count_after}'}",
        ))

    if "new_case_answer_confidence" in checks_spec:
        expected_ac = checks_spec["new_case_answer_confidence"]
        new_ids = set(cases_after.keys()) - set(cases_before.keys())
        if new_ids:
            actual_ac = cases_after[list(new_ids)[0]].get("answer_confidence", -1)
            ok = abs(actual_ac - expected_ac) < 0.05
            results.append(CheckResult(
                passed=ok,
                message=f"新 case answer_confidence={expected_ac}: {'✓' if ok else f'✗ 实际={actual_ac}'}",
            ))
        else:
            results.append(CheckResult(
                passed=False,
                message=f"新 case answer_confidence={expected_ac}: ✗ 未找到新 case",
            ))

    return results


# ---------------------------------------------------------------------------
# 单条用例执行
# ---------------------------------------------------------------------------

async def run_case(agent_service, spec: dict, timeout: float) -> CaseResult:
    case_id = spec["id"]
    result = CaseResult(id=case_id, description=spec["description"])

    cases_before = read_cases(CASES_MD)
    count_before = count_cases(CASES_MD)

    try:
        turn_results = await asyncio.wait_for(
            run_turns(agent_service, spec["turns"]),
            timeout=timeout,
        )
        result.turns = turn_results

        cases_after = read_cases(CASES_MD)
        count_after = count_cases(CASES_MD)

        result.checks = run_checks(
            spec, turn_results, cases_before, cases_after, count_before, count_after
        )
        all_passed = all(c.passed for c in result.checks)
        result.status = "success" if all_passed else "fail"

    except asyncio.TimeoutError:
        result.status = "timeout"
        result.error = f"超时 ({timeout}s)"
    except Exception as e:
        result.status = "error"
        result.error = str(e)

    return result


# ---------------------------------------------------------------------------
# 结果输出
# ---------------------------------------------------------------------------

def print_result(r: CaseResult):
    icon = {"success": "✓", "fail": "✗", "error": "!", "timeout": "⏱"}.get(r.status, "?")
    print(f"\n{icon} [{r.id}] {r.description}")
    for c in r.checks:
        print(f"    {'✓' if c.passed else '✗'} {c.message}")
    if r.error:
        print(f"    错误: {r.error}")


def save_report(results: list[CaseResult], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"issue_diagnosis_{timestamp}.md"

    total = len(results)
    passed = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status in ("error", "timeout"))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Issue-Diagnosis 集成测试报告\n\n")
        f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**总计: {total} | 通过: {passed} | 失败: {failed} | 异常: {errors}**\n\n")
        f.write("---\n\n")

        for r in results:
            icon = {"success": "✓", "fail": "✗", "error": "!", "timeout": "⏱"}.get(r.status, "?")
            f.write(f"## {icon} [{r.id}] {r.description}\n\n")
            if r.checks:
                f.write("**校验结果：**\n\n")
                for c in r.checks:
                    f.write(f"- {'✓' if c.passed else '✗'} {c.message}\n")
                f.write("\n")
            if r.error:
                f.write(f"**错误：** {r.error}\n\n")
            if r.turns:
                f.write("<details><summary>对话内容</summary>\n\n")
                for i, t in enumerate(r.turns, 1):
                    f.write(f"**第{i}轮输入：** {t.prompt}\n\n")
                    f.write(f"**第{i}轮回复：**\n\n{t.answer}\n\n")
                f.write("</details>\n\n")
            f.write("---\n\n")

    print(f"\n📄 报告已保存: {md_path}")
    return md_path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="issue-diagnosis skill 集成测试")
    parser.add_argument("--id", help="只运行指定 id 的用例（如 id-001）")
    parser.add_argument("--timeout", "-t", type=float, default=360.0)
    parser.add_argument("--no-backup", action="store_true", help="不备份 cases.md")
    args = parser.parse_args()

    specs = []
    with open(DATASET, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                specs.append(json.loads(line))

    if args.id:
        specs = [s for s in specs if s["id"] == args.id]
        if not specs:
            print(f"未找到用例: {args.id}")
            sys.exit(1)

    print(f"共 {len(specs)} 条用例，超时 {args.timeout}s/条\n")

    # 备份 cases.md，测试结束后恢复
    backup_path = None
    if not args.no_backup and CASES_MD.exists():
        backup_path = CASES_MD.with_suffix(".md.bak")
        shutil.copy2(CASES_MD, backup_path)
        print(f"📦 已份 cases.md → {backup_path.name}\n")

    agent_service = get_agent_service()
    results = []

    try:
        for spec in specs:
            print(f"▶ [{spec['id']}] {spec['description'][:60]}...")
            r = await run_case(agent_service, spec, args.timeout)
            results.append(r)
            print_result(r)
    finally:
        if backup_path and backup_path.exists():
            shutil.copy2(backup_path, CASES_MD)
            backup_path.unlink()
            print(f"\n♻️  已恢复 cases.md")

    total = len(results)
    passed = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status in ("error", "timeout"))

    print(f"\n{'='*50}")
    print(f"总计: {total} | ✓ 通过: {passed} | ✗ 失败: {failed} | ! 异常: {errors}")
    print(f"{'='*50}")

    save_report(results, RESULTS_DIR)
    sys.exit(0 if failed == 0 and errors == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
