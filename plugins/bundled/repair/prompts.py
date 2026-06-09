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


# ── 人工修复单：从单描述解析目标 repo / 服务名 ──────────────────────────────
# 约定单描述里有一行形如 `repo: xxx` / `仓库：xxx` / `服务: xxx`（半/全角冒号均可）。
# 值可以是：
#   - 完整 project_id 多级路径，如 piaozone/elc-integration/api-elc-invoice-imputation
#   - 两段路径，如 ai-agent/foo
#   - 单段服务名，如 api-elc-invoice-imputation（由 bug-fix-developer 查 service-repo-map 解析）
# 解析不到返回空串。
_REPO_PATTERN = re.compile(
    r"(?:repo|仓库|服务名?)\s*[:：]\s*([A-Za-z0-9._/\-]+)",
    re.IGNORECASE,
)


def parse_repo_from_description(description: str) -> str:
    """从人工单描述里解析 `repo:` / `仓库:` / `服务:` 后的目标仓库或服务名。

    返回原始 token（完整路径或裸服务名），解析不到返回空串。
    服务名→完整 project_id 的映射由 bug-fix-developer 查 service-repo-map 完成。
    """
    if not description:
        return ""
    m = _REPO_PATTERN.search(description)
    return m.group(1).strip().rstrip("/") if m else ""


# ── created 事件分类：是否「要改代码的 bug」───────────────────────────────────
# @agent 关联到 issue 即触发 created；先判断这是不是一个要改代码的 bug 修复请求。
# 是 → 进自动修复流程；否（诊断/咨询/查数据）→ 走普通 skill 自选。

def build_classify_prompt(description: str) -> str:
    """拼出判断 issue 是否「要改代码修复的 bug」的极简分类 prompt。"""
    return "\n".join(
        [
            "判断下面这个 Linear issue 是不是一个【需要修改某个服务源码来修复的代码 bug】。",
            "- 是：明确指向某服务的逻辑缺陷/错误行为，且修复手段是改代码（如「任务作废逻辑需改为不作废」）。",
            "- 否：纯咨询、使用指导、数据查询、现象排查诊断（尚未定位到要改的代码）、需求讨论等。",
            "拿不准时判「是」。",
            f"\n# Issue 描述\n{description}",
            "\n只按以下格式输出，不要其它内容：",
            "【是否代码bug】是 或 否",
            "【理由】一句话",
        ]
    )


def parse_is_code_bug(text: str) -> bool:
    """从分类输出解析是否代码 bug。拿不准/解析不出 → 默认 True（倒向修复）。"""
    verdict = _extract(r"【是否代码bug】\s*([^\n]+)", text)
    if not verdict:
        return True
    # 命中明确否定才返回 False，其余一律 True
    return "否" not in verdict and "不是" not in verdict


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
    repo_line = (
        f"目标仓库: {repo}"
        if repo
        else "目标仓库: （未指定，请从下方修复计划/描述中识别服务名，"
        "再查 service-repo-map.md 解析成完整 project_id）"
    )
    parts = [
        f"严格按 skill: bug-fix-developer 执行 TDD 修复任务。",
        f"\n# 修复任务 {identifier}",
        repo_line,
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
    """从 developer skill 输出解析仓库、分支、MR URL、测试路径。

    缺失字段返回空串。`repo` 是 agent 实际解析/使用的完整 project_id，
    用于人工单 repo 留空时由 agent 查表解析后回填，供 Jenkins 触发。
    """
    return {
        "repo": _extract(r"【仓库】\s*(\S+)", text),
        "branch": _extract(r"【分支】\s*(\S+)", text),
        "mr_url": _extract(r"【MR链接】\s*(\S+)", text),
        "test_path": _extract(r"【复现测试】\s*(\S+)", text),
        "summary": _extract(r"【说明】\s*([^\n]+)", text),
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
