"""
发票云客服 Skill 人工评估工具

用于人工审核测试结果并评分

用法:
    python tests/test_evaluator.py reports/test_report_xxx.json
"""

import argparse
import json
import sys
from pathlib import Path


class ManualEvaluator:
    """人工评估器"""

    RATING_SCALE = {
        5: "完美 - 完全正确，无需改进",
        4: "良好 - 基本正确，有小问题",
        3: "及格 - 部分正确，需改进",
        2: "较差 - 大部分错误",
        1: "失败 - 完全错误",
    }

    CRITERIA = [
        ("product_match", "产品匹配 - 回答是否针对正确的产品线"),
        ("content_accuracy", "内容准确 - 回答内容是否正确"),
        ("source_citation", "来源引用 - 是否正确引用来源"),
        ("rule_compliance", "规则遵循 - 是否遵循标准话术等规则"),
        ("completeness", "完整性 - 是否完整回答了问题"),
    ]

    def __init__(self, report_path: str):
        self.report_path = report_path
        self.report = self._load_report()
        self.evaluations = []

    def _load_report(self) -> dict:
        """加载测试报告"""
        with open(self.report_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_result(self, result: dict) -> dict:
        """评估单个测试结果"""
        print(f"\n{'='*70}")
        print(f"[{result['id']}] {result['name']}")
        print(f"{'='*70}")
        print(f"类别: {result['category']}")
        print(f"问题: {result['query']}")
        print(f"\n{'─'*70}")
        print(f"Agent 回答:")
        print(f"{'─'*70}")
        print(result['response'])
        print(f"{'─'*70}")

        # 显示工具使用
        if result.get('tool_uses'):
            print(f"\n工具使用 ({len(result['tool_uses'])} 次):")
            for tool in result['tool_uses'][:5]:  # 只显示前5个
                print(f"  - {tool['tool']}")

        # 显示自动评估结果
        auto_eval = result.get('evaluation', {})
        if auto_eval.get('checks'):
            print(f"\n自动检查:")
            for check in auto_eval['checks']:
                icon = "✓" if check.get('passed') else "✗"
                print(f"  {icon} {check}")

        # 收集人工评分
        print(f"\n{'─'*70}")
        print("请评分 (1-5):")
        for value, desc in sorted(self.RATING_SCALE.items(), reverse=True):
            print(f"  {value}: {desc}")
        print(f"{'─'*70}")

        ratings = {}
        for key, description in self.CRITERIA:
            while True:
                try:
                    score = input(f"{description} [1-5, s=跳过]: ").strip()
                    if score.lower() == 's':
                        break
                    score = int(score)
                    if 1 <= score <= 5:
                        ratings[key] = score
                        break
                    else:
                        print("请输入 1-5 之间的数字")
                except ValueError:
                    print("请输入有效数字或 's' 跳过")

        # 收集评论
        comment = input("\n评论 (可选): ").strip()

        # 总体评分
        if ratings:
            avg_score = sum(ratings.values()) / len(ratings)
            passed = avg_score >= 3
        else:
            avg_score = None
            passed = result.get('passed', False)

        evaluation = {
            "id": result['id'],
            "ratings": ratings,
            "avg_score": avg_score,
            "passed": passed,
            "comment": comment,
        }

        self.evaluations.append(evaluation)
        return evaluation

    def run_interactive(self):
        """交互式评估"""
        results = self.report.get('results', [])
        total = len(results)

        print(f"""
╭──────────────────────────────────────────────────────────────────────╮
│ 发票云客服 Skill 人工评估工具                                        │
│ 共 {total:2d} 个测试结果待评估                                              │
│                                                                      │
│ 操作说明:                                                            │
│   输入 1-5 评分                                                      │
│   输入 s 跳过某项                                                    │
│   输入 q 退出并保存                                                  │
│   输入 n 跳过整个用例                                                │
╰──────────────────────────────────────────────────────────────────────╯
        """)

        for i, result in enumerate(results, 1):
            print(f"\n[{i}/{total}]")

            action = input("评估此用例? [y/n/q]: ").strip().lower()
            if action == 'q':
                break
            elif action == 'n':
                continue

            self.evaluate_result(result)

        self.save_evaluations()
        self.print_summary()

    def save_evaluations(self):
        """保存评估结果"""
        output_path = Path(self.report_path).with_suffix('.eval.json')

        eval_report = {
            "source_report": self.report_path,
            "evaluations": self.evaluations,
            "summary": self._calculate_summary()
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(eval_report, f, ensure_ascii=False, indent=2)

        print(f"\n评估结果已保存: {output_path}")

    def _calculate_summary(self) -> dict:
        """计算评估摘要"""
        if not self.evaluations:
            return {}

        total = len(self.evaluations)
        passed = sum(1 for e in self.evaluations if e.get('passed'))

        # 按维度统计平均分
        criteria_scores = {key: [] for key, _ in self.CRITERIA}
        for e in self.evaluations:
            for key, score in e.get('ratings', {}).items():
                if key in criteria_scores:
                    criteria_scores[key].append(score)

        criteria_avg = {}
        for key, scores in criteria_scores.items():
            if scores:
                criteria_avg[key] = sum(scores) / len(scores)

        return {
            "total_evaluated": total,
            "passed": passed,
            "pass_rate": passed / total if total else 0,
            "criteria_averages": criteria_avg
        }

    def print_summary(self):
        """打印评估摘要"""
        summary = self._calculate_summary()

        if not summary:
            print("\n没有评估数据")
            return

        print(f"\n{'='*70}")
        print("评估摘要")
        print(f"{'='*70}")
        print(f"评估数量: {summary['total_evaluated']}")
        print(f"通过数量: {summary['passed']}")
        print(f"通过率: {summary['pass_rate']*100:.1f}%")

        if summary.get('criteria_averages'):
            print(f"\n各维度平均分:")
            for key, desc in self.CRITERIA:
                avg = summary['criteria_averages'].get(key)
                if avg:
                    bar = "█" * int(avg) + "░" * (5 - int(avg))
                    print(f"  {desc.split(' - ')[0]}: {bar} {avg:.1f}")


def main():
    parser = argparse.ArgumentParser(description="发票云客服 Skill 人工评估工具")
    parser.add_argument("report", help="测试报告文件路径")

    args = parser.parse_args()

    if not Path(args.report).exists():
        print(f"错误: 文件不存在 {args.report}")
        sys.exit(1)

    evaluator = ManualEvaluator(args.report)
    evaluator.run_interactive()


if __name__ == "__main__":
    main()
