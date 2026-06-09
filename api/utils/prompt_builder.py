"""Prompt building utilities for AI Agent queries."""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# 仅供修复流水线 coordinator 内部调用的 skill：出现在入口自选清单时加括注，
# 防止入口把流水线内部 skill 当候选误选。
_COORDINATOR_ONLY_SKILLS = frozenset({"bug-fix-developer", "repair-report-analyzer"})
_COORDINATOR_ONLY_NOTE = "（仅供修复流水线内部调用，请勿自选）"


def _format_skill_choice(name: str) -> str:
    """格式化自选清单里的单个 skill 名，coordinator-only 的追加勿自选括注。"""
    if name in _COORDINATOR_ONLY_SKILLS:
        return f"{name}{_COORDINATOR_ONLY_NOTE}"
    return name


async def build_initial_prompt(
    tenant_id: str,
    user_prompt: str,
    skill: Optional[str] = None,
    default_skills: Optional[List[str]] = None,
    language: str = "中文",
    context_file_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    images: Optional[List[str]] = None,
) -> str:
    """
    Build generic initial prompt for any skill.

    Args:
        tenant_id: Tenant identifier
        user_prompt: User's query
        skill: Optional skill name to use
        language: Response language
        context_file_path: Path to saved context file
        metadata: Additional metadata passed from endpoint
        images: Optional list of image URLs (max 5)

    Returns:
        Formatted prompt string
    """
    parts = []

    # 核心任务
    parts.append("# 任务")
    if skill:
        parts.append(f"严格按skill: {skill} 执行任务")
    elif default_skills:
        skills_list = "、".join(_format_skill_choice(s) for s in default_skills)
        parts.append(f"根据用户请求，从以下 skill 中选择最合适的一个并严格按该 skill 执行任务: {skills_list}")
    parts.append(f"用户请求: {user_prompt}")

    # 上下文
    parts.append("\n# 上下文")
    if tenant_id:
        parts.append(f"租户ID: {tenant_id}")
    parts.append(f"响应语言: {language}")

    if context_file_path:
        parts.append(f"上下文文件: {context_file_path}")

    if metadata:
        for key, value in metadata.items():
            if value is not None:
                parts.append(f"{key}: {value}")

    if images:
        parts.append(f"\n# 用户上传的图片\n用户本轮附带 {len(images)} 张图片，已随消息一同送达，请直接识别分析其内容。")

    return "\n".join(parts)
