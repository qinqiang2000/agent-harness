"""Prompt building utilities for AI Agent queries."""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from api.constants import TENANTS_DIR

logger = logging.getLogger(__name__)


def build_initial_prompt(
    tenant_id: str,
    user_prompt: str,
    skill: Optional[str] = None,
    language: str = "中文",
    context_file_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build generic initial prompt for any skill.
    Business logic is defined in skill.md files.

    Args:
        tenant_id: Tenant identifier
        user_prompt: User's query
        skill: Optional skill name to use
        language: Response language
        context_file_path: Path to saved context file
        metadata: Additional metadata passed from endpoint

    Returns:
        Formatted prompt string
    """
    parts = []

    # 核心任务
    parts.append("# 任务")
    if skill:
        parts.append(f"执行 skill: {skill}")
    parts.append(f"用户请求: {user_prompt}")

    # 上下文
    parts.append("\n# 上下文")
    parts.append(f"租户ID: {tenant_id}")
    parts.append(f"响应语言: {language}")

    if context_file_path:
        parts.append(f"上下文文件: {context_file_path}")

    if metadata:
        for key, value in metadata.items():
            if value is not None:
                parts.append(f"{key}: {value}")

    # 数据访问约束 (通用)
    parts.append("\n# 数据访问约束")
    parts.append("可访问目录:")
    parts.append("- 公共知识库: ./data/kb/")
    parts.append(f"- 租户数据: ./data/tenants/{tenant_id}/")

    return "\n".join(parts)
