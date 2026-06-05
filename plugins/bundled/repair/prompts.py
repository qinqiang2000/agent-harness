"""状态映射 + 各阶段 prompt 模板 + 输出解析（纯函数，易测）。"""

import os
import re
from typing import Dict


# ── Linear 状态名 → 是否「审核通过（进入开发）」────────────────────────────
# 用户在 Linear 把单子拖到「开发中」类状态即视为审核通过。
# 可通过 env REPAIR_APPROVAL_STATES 覆盖（逗号分隔，小写匹配）。
# 注意：以下默认项必须全部小写（匹配时按小写比较，不会再二次 lower）。
_DEFAULT_APPROVAL_STATES = ["in progress", "开发中", "in development", "开发"]


def _approval_states() -> list:
    raw = os.getenv("REPAIR_APPROVAL_STATES", "")
    if raw.strip():
        return [s.strip().lower() for s in raw.split(",") if s.strip()]
    return _DEFAULT_APPROVAL_STATES


def is_approval_state(state_name: str) -> bool:
    """判断某 Linear 状态名是否表示「用户已审核通过，可进入开发」。"""
    if not state_name:
        return False
    return state_name.strip().lower() in _approval_states()


# ── developer / analyzer prompt 模板 ───────────────────────────────────────

def build_developer_prompt(
    identifier: str,
    root_cause: str,
    evidence: str,
    repair_plan: str,
    repo: str,
    branch: str,
    is_retry: bool,
    last_report: str,
) -> str:
    """拼出调用 bug-fix-developer skill 的 prompt。"""
    parts = [
        f"严格按 skill: bug-fix-developer 执行 TDD 修复任务。",
        f"\n# 修复任务 {identifier}",
        f"目标仓库: {repo}",
        f"修复分支名（必须用此分支名）: {branch}",
        f"\n## 根因\n{root_cause}",
        f"\n## 证据\n{evidence}",
        f"\n## 修复计划\n{repair_plan}",
    ]
    if is_retry:
        parts.append(
            "\n## ⚠️ 这是同分支重修（上一轮修复未通过）\n"
            "在已有修复分支基础上继续修，先分析下方失败报告再改码。\n"
            f"\n### 上一轮失败报告\n{last_report}"
        )
    return "\n".join(parts)


def build_analyzer_prompt(
    identifier: str,
    root_cause: str,
    repair_plan: str,
    report: str,
) -> str:
    """拼出调用 repair-report-analyzer skill 的 prompt。"""
    return "\n".join(
        [
            "严格按 skill: repair-report-analyzer 执行三类归因分析。",
            f"\n# 待分析的修复 {identifier}",
            f"\n## 原根因\n{root_cause}",
            f"\n## 修复计划\n{repair_plan}",
            f"\n## 测试报告\n{report}",
            "\n请按 skill 要求输出【判定】【依据】【后续动作】结构化结果。",
        ]
    )


# ── 输出解析（纯函数）──────────────────────────────────────────────────────

def _extract(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def parse_developer_output(text: str) -> Dict[str, str]:
    """从 developer skill 输出解析分支、MR URL、测试路径。

    缺失字段返回空串。
    """
    return {
        "branch": _extract(r"【分支】\s*(\S+)", text),
        "mr_url": _extract(r"【MR链接】\s*(\S+)", text),
        "test_path": _extract(r"【复现测试】\s*(\S+)", text),
    }


_VERDICT_MAP = [
    ("已解决", "resolved"),
    ("代码错", "code_error"),
    ("根因错", "root_cause_error"),
    ("漏依赖", "missing_dependency"),
]


def parse_analyzer_output(text: str) -> Dict[str, str]:
    """从 analyzer skill 输出解析【判定】。

    解析不出明确判定时，保守归为 code_error（走同分支重修，
    绝不误判为已解决而关单）。
    """
    verdict_line = _extract(r"【判定】\s*([^\n]+)", text)
    verdict = "code_error"
    for zh, key in _VERDICT_MAP:
        if zh in verdict_line:
            verdict = key
            break
    return {
        "verdict": verdict,
        "raw": text,
    }
