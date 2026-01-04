"""
发票云客服 Skill 测试执行器

执行 test_questions.py 中定义的测试用例，生成测试报告

用法:
    python tests/test_runner.py                    # 运行所有测试
    python tests/test_runner.py --category 产品识别  # 按类别运行
    python tests/test_runner.py --id PROD-001      # 运行单个测试
    python tests/test_runner.py --list             # 列出所有测试
    python tests/test_runner.py --quick            # 快速测试（每类别1个）
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from api.models.requests import QueryRequest
from api.services.agent_service import AgentService
from api.services.session_service import InMemorySessionService

from test_questions import (
    TEST_CASES,
    TestCase,
    TestCategory,
    get_test_cases_by_category,
    get_test_case_by_id,
)


class TestResult:
    """测试结果"""

    def __init__(self, test_case: TestCase):
        self.test_case = test_case
        self.response: str = ""
        self.tool_uses: list[dict] = []
        self.error: Optional[str] = None
        self.passed: bool = False
        self.evaluation: dict = {}
        self.duration_ms: int = 0


class SkillTestRunner:
    """Skill 测试执行器"""

    def __init__(self, verbose: bool = True):
        self.session_service = InMemorySessionService()
        self.agent_service = AgentService(self.session_service)
        self.results: list[TestResult] = []
        self.verbose = verbose

    async def run_test(self, test_case: TestCase) -> TestResult:
        """运行单个测试用例"""
        result = TestResult(test_case)
        start_time = datetime.now()

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"[{test_case.id}] {test_case.name}")
            print(f"{'='*70}")
            print(f"类别: {test_case.category.value}")
            print(f"输入: {test_case.query}")
            print(f"\n预期行为:")
            for behavior in test_case.expected_behaviors:
                print(f"  - {behavior}")
            print(f"\n{'─'*70}")
            print("实际响应:")

        # 创建请求
        request = QueryRequest(
            tenant_id="test-tenant",
            prompt=test_case.query,
            skill="customer-service",
            language="zh-CN"
        )

        try:
            async for event in self.agent_service.process_query(request):
                if event.get("type") == "assistant_message":
                    content = event.get("content", "")
                    if content:
                        if self.verbose:
                            print(content, end="", flush=True)
                        result.response += content

                elif event.get("type") == "tool_use":
                    tool_info = {
                        "tool": event.get("tool_name"),
                        "input": event.get("tool_input", {})
                    }
                    result.tool_uses.append(tool_info)

            # 计算耗时
            result.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            if self.verbose:
                print(f"\n{'─'*70}")
                if result.tool_uses:
                    print(f"工具调用 ({len(result.tool_uses)}):")
                    for tool in result.tool_uses:
                        print(f"  - {tool['tool']}")
                        if tool['tool'] == 'Grep':
                            print(f"    pattern: {tool['input'].get('pattern', '')}")
                            print(f"    path: {tool['input'].get('path', '')}")
                        elif tool['tool'] == 'Read':
                            print(f"    file: {tool['input'].get('file_path', '')}")
                print(f"\n耗时: {result.duration_ms}ms")

            # 自动评估
            result.evaluation = self._evaluate_result(test_case, result)
            result.passed = result.evaluation.get("passed", False)

            if self.verbose:
                self._print_evaluation(result)

        except Exception as e:
            result.error = str(e)
            if self.verbose:
                print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()

        self.results.append(result)
        return result

    def _evaluate_result(self, test_case: TestCase, result: TestResult) -> dict:
        """自动评估测试结果"""
        evaluation = {
            "passed": True,
            "checks": [],
            "warnings": []
        }

        response = result.response.lower()

        # 检查必须包含的内容
        for expected in test_case.expected_output_contains:
            if expected.lower() not in response:
                evaluation["checks"].append({
                    "type": "contains",
                    "expected": expected,
                    "passed": False
                })
                evaluation["passed"] = False
            else:
                evaluation["checks"].append({
                    "type": "contains",
                    "expected": expected,
                    "passed": True
                })

        # 检查不应包含的内容
        for not_expected in test_case.expected_output_not_contains:
            if not_expected.lower() in response:
                evaluation["checks"].append({
                    "type": "not_contains",
                    "not_expected": not_expected,
                    "passed": False
                })
                evaluation["passed"] = False
            else:
                evaluation["checks"].append({
                    "type": "not_contains",
                    "not_expected": not_expected,
                    "passed": True
                })

        # 检查目录搜索
        if test_case.expected_directory:
            dir_searched = False
            for tool in result.tool_uses:
                if tool['tool'] in ['Grep', 'Glob', 'Read']:
                    path = tool['input'].get('path', '') or tool['input'].get('file_path', '')
                    if test_case.expected_directory in path:
                        dir_searched = True
                        break
            if not dir_searched:
                evaluation["warnings"].append(
                    f"未搜索预期目录: {test_case.expected_directory}"
                )

        # 检查产品识别（如有标准话术要求，检查是否正确返回）
        if "标准话术" in str(test_case.expected_behaviors):
            if "抱歉" in response and "知识库没找到" in response:
                evaluation["checks"].append({
                    "type": "standard_reply",
                    "passed": True
                })
            else:
                evaluation["warnings"].append("未使用标准话术")

        # 如果没有任何检查项，标记为需人工验证
        if not evaluation["checks"]:
            evaluation["manual_review"] = True
            evaluation["passed"] = True  # 默认通过，但需人工审核

        return evaluation

    def _print_evaluation(self, result: TestResult):
        """打印评估结果"""
        eval = result.evaluation
        status = "✅ 通过" if result.passed else "❌ 失败"
        print(f"\n评估: {status}")

        if eval.get("checks"):
            print("  检查项:")
            for check in eval["checks"]:
                icon = "✓" if check["passed"] else "✗"
                if check["type"] == "contains":
                    print(f"    {icon} 包含 '{check['expected']}'")
                elif check["type"] == "not_contains":
                    print(f"    {icon} 不包含 '{check['not_expected']}'")
                elif check["type"] == "standard_reply":
                    print(f"    {icon} 使用标准话术")

        if eval.get("warnings"):
            print("  警告:")
            for warning in eval["warnings"]:
                print(f"    ⚠ {warning}")

        if eval.get("manual_review"):
            print("  📋 需人工审核")

    async def run_all(self, test_cases: Optional[list[TestCase]] = None):
        """运行所有测试"""
        cases = test_cases or TEST_CASES

        print(f"""
╭──────────────────────────────────────────────────────────────────────╮
│ 发票云客服 Skill 测试套件                                            │
│ 共 {len(cases):2d} 个测试用例                                                   │
╰──────────────────────────────────────────────────────────────────────╯
        """)

        for i, test_case in enumerate(cases, 1):
            print(f"\n[{i}/{len(cases)}] 运行测试...")
            await self.run_test(test_case)

        self.print_summary()

    def print_summary(self):
        """打印测试摘要"""
        print(f"\n\n{'='*70}")
        print("测试摘要")
        print(f"{'='*70}")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        errors = sum(1 for r in self.results if r.error)
        manual_review = sum(1 for r in self.results if r.evaluation.get("manual_review"))

        print(f"总测试数: {total}")
        print(f"  ✅ 通过: {passed}")
        print(f"  ❌ 失败: {failed}")
        print(f"  💥 异常: {errors}")
        print(f"  📋 需人工审核: {manual_review}")

        avg_duration = sum(r.duration_ms for r in self.results) / total if total else 0
        print(f"\n平均耗时: {avg_duration:.0f}ms")

        # 按类别统计
        print(f"\n按类别统计:")
        for category in TestCategory:
            cat_results = [r for r in self.results if r.test_case.category == category]
            if cat_results:
                cat_passed = sum(1 for r in cat_results if r.passed)
                print(f"  {category.value}: {cat_passed}/{len(cat_results)}")

        # 失败的测试
        failed_results = [r for r in self.results if not r.passed]
        if failed_results:
            print(f"\n失败的测试:")
            for r in failed_results:
                print(f"  ❌ [{r.test_case.id}] {r.test_case.name}")
                if r.error:
                    print(f"     错误: {r.error}")

    def export_report(self, filepath: str):
        """导出测试报告"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.passed),
                "failed": sum(1 for r in self.results if not r.passed),
                "errors": sum(1 for r in self.results if r.error),
            },
            "results": []
        }

        for r in self.results:
            report["results"].append({
                "id": r.test_case.id,
                "name": r.test_case.name,
                "category": r.test_case.category.value,
                "query": r.test_case.query,
                "passed": r.passed,
                "response": r.response[:500] + "..." if len(r.response) > 500 else r.response,
                "tool_uses": r.tool_uses,
                "evaluation": r.evaluation,
                "error": r.error,
                "duration_ms": r.duration_ms
            })

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n报告已导出: {filepath}")


def list_tests():
    """列出所有测试用例"""
    print(f"\n{'='*70}")
    print("发票云客服 Skill 测试用例列表")
    print(f"{'='*70}")
    print(f"共 {len(TEST_CASES)} 个测试用例\n")

    for category in TestCategory:
        cases = get_test_cases_by_category(category)
        if cases:
            print(f"\n[{category.value}] ({len(cases)} 个)")
            for tc in cases:
                print(f"  {tc.id}: {tc.name}")
                print(f"       Q: {tc.query[:50]}{'...' if len(tc.query) > 50 else ''}")


async def main():
    parser = argparse.ArgumentParser(description="发票云客服 Skill 测试执行器")
    parser.add_argument("--list", action="store_true", help="列出所有测试用例")
    parser.add_argument("--id", type=str, help="运行指定ID的测试用例")
    parser.add_argument("--category", type=str, help="运行指定类别的测试用例")
    parser.add_argument("--quick", action="store_true", help="快速测试（每类别1个）")
    parser.add_argument("--report", type=str, help="导出报告到指定文件")
    parser.add_argument("--quiet", action="store_true", help="静默模式")

    args = parser.parse_args()

    if args.list:
        list_tests()
        return

    runner = SkillTestRunner(verbose=not args.quiet)

    # 确定要运行的测试用例
    test_cases = None

    if args.id:
        tc = get_test_case_by_id(args.id)
        if tc:
            test_cases = [tc]
        else:
            print(f"错误: 未找到测试用例 {args.id}")
            sys.exit(1)

    elif args.category:
        try:
            category = TestCategory(args.category)
            test_cases = get_test_cases_by_category(category)
            if not test_cases:
                print(f"错误: 类别 '{args.category}' 中没有测试用例")
                sys.exit(1)
        except ValueError:
            print(f"错误: 无效的类别 '{args.category}'")
            print(f"有效类别: {[c.value for c in TestCategory]}")
            sys.exit(1)

    elif args.quick:
        # 每个类别取第一个
        test_cases = []
        for category in TestCategory:
            cases = get_test_cases_by_category(category)
            if cases:
                test_cases.append(cases[0])

    # 运行测试
    await runner.run_all(test_cases)

    # 导出报告
    if args.report:
        runner.export_report(args.report)
    else:
        # 默认导出到 tests/reports/
        report_dir = Path(__file__).parent / "reports"
        report_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"test_report_{timestamp}.json"
        runner.export_report(str(report_path))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被中断")
        sys.exit(0)
