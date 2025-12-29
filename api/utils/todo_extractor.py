"""Todo extraction utilities from Claude SDK tool blocks."""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def extract_todos_from_tool(tool_block) -> Optional[List[Dict[str, Any]]]:
    """
    Extract todos array from TodoWrite tool input.

    Args:
        tool_block: ToolUseBlock from Claude SDK

    Returns:
        List of todo objects or None if not a TodoWrite block
    """
    if tool_block.name == "TodoWrite" and isinstance(tool_block.input, dict):
        return tool_block.input.get("todos", [])
    return None
