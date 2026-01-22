"""Enhanced logging for Claude SDK messages."""

import json
import logging
import os
import sys
from typing import Any, Dict, Optional


class Colors:
    """ANSI color codes (only used when TTY detected)"""
    RESET = '\033[0m'
    CYAN = '\033[96m'      # SystemMessage
    GREEN = '\033[92m'     # AssistantMessage text
    MAGENTA = '\033[95m'   # Tools (general)
    YELLOW = '\033[93m'    # Tools (read/search)
    BLUE = '\033[94m'      # ResultMessage
    RED = '\033[91m'       # Errors
    BOLD = '\033[1m'
    DIM = '\033[2m'


def _should_use_colors() -> bool:
    """Check if colored output should be enabled"""
    # Check environment variable first
    force_color = os.getenv('FORCE_COLOR', '').lower()
    if force_color in ('1', 'true', 'yes', 'on'):
        return True
    elif force_color in ('0', 'false', 'no', 'off'):
        return False

    # Auto-detect: use colors if stderr is a TTY
    return sys.stderr.isatty()


# Global flag for color usage
USE_COLORS = _should_use_colors()


def _colorize(text: str, color: str) -> str:
    """Apply color to text if colors are enabled"""
    if USE_COLORS:
        return f"{color}{text}{Colors.RESET}"
    return text


def _format_tool_input(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format tool input based on tool type"""

    # Special formatting for common tools
    if tool_name == "Read":
        file_path = tool_input.get('file_path', 'N/A')
        return f'file_path="{file_path}"'

    elif tool_name == "TodoWrite":
        todos = tool_input.get('todos', [])
        return f"todos: {len(todos)} items"

    elif tool_name == "AskUserQuestion":
        questions = tool_input.get('questions', [])
        return f"questions: {len(questions)} items"

    elif tool_name in ("Grep", "WebSearch"):
        pattern = tool_input.get('pattern') or tool_input.get('query', '')
        return f'pattern="{pattern}"'

    elif tool_name == "Bash":
        cmd = tool_input.get('command', '')
        return f'command="{cmd}"'

    elif tool_name in ("Write", "Edit"):
        file_path = tool_input.get('file_path', 'N/A')
        return f'file_path="{file_path}"'

    elif tool_name == "Glob":
        pattern = tool_input.get('pattern', '')
        path = tool_input.get('path', '.')
        return f'pattern="{pattern}", path="{path}"'

    elif tool_name == "Skill":
        skill = tool_input.get('skill', '')
        args = tool_input.get('args', '')
        if args:
            return f'skill="{skill}", args="{args}"'
        return f'skill="{skill}"'

    # Default: show full JSON
    json_str = json.dumps(tool_input, ensure_ascii=False)
    return json_str


class SDKLogger:
    """Enhanced logger for Claude SDK messages"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_system_message(self, msg):
        """Log SystemMessage"""
        subtype = getattr(msg, 'subtype', None)
        data = getattr(msg, 'data', {})

        if subtype:
            prefix = _colorize(f"[SystemMessage:{subtype}]", Colors.CYAN)

            if subtype == 'init' and isinstance(data, dict):
                session_id = data.get('session_id', 'N/A')
                self.logger.info(f"{prefix} Session initialized - session_id: {session_id}")
            else:
                self.logger.info(f"{prefix} {data}")
        else:
            prefix = _colorize("[SystemMessage]", Colors.CYAN)
            self.logger.debug(f"{prefix} {data}")

    def log_text_block(self, block):
        """Log TextBlock from AssistantMessage"""
        # Replace newlines with space for better log readability
        text_display = block.text.replace('\n', ' ')
        prefix = _colorize("[AssistantMessage]", Colors.GREEN)
        self.logger.info(f'{prefix} Text: "{text_display}"')

    def log_tool_use(self, block) -> Optional[str]:
        """
        Log ToolUseBlock from AssistantMessage

        Returns:
            Tool name for special handling by caller
        """
        # Use yellow for read/search tools, magenta for others
        tool_color = Colors.YELLOW if block.name in ('Read', 'Grep', 'Glob', 'WebSearch') else Colors.MAGENTA
        prefix = _colorize(f"[Tool:{block.name}]", tool_color)

        formatted_input = _format_tool_input(block.name, block.input)
        self.logger.info(f"{prefix} {formatted_input}")

        return block.name

    def log_result_message(self, msg):
        """Log ResultMessage"""
        prefix = _colorize("[ResultMessage]", Colors.BLUE)

        # Log completion status
        if msg.is_error:
            status = _colorize("✗ ERROR", Colors.RED)
        else:
            status = _colorize("✓", Colors.GREEN)

        self.logger.info(
            f"{prefix} {status} Session {msg.session_id} completed - "
            f"duration={msg.duration_ms}ms, turns={msg.num_turns}, error={msg.is_error}"
        )

        # Log result content if present
        if msg.result:
            result_len = len(msg.result)
            self.logger.info(f"{prefix} Result: {result_len} chars")
