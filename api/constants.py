"""Global constants for the AI Agent Service."""

import os
from pathlib import Path

# Timeout for waiting on first message from Claude SDK (seconds)
FIRST_MESSAGE_TIMEOUT = int(os.getenv("CLAUDE_FIRST_MESSAGE_TIMEOUT", "120"))

# Directory paths
AGENTS_ROOT = Path(__file__).resolve().parent.parent  # /agents

# Agent working directory (supports AGENT_CWD env var, defaults to AGENTS_ROOT for backward compatibility)
_agent_cwd_env = os.getenv("AGENT_CWD", "")
if _agent_cwd_env:
    # If AGENT_CWD is set, resolve relative paths relative to AGENTS_ROOT
    _agent_cwd_path = Path(_agent_cwd_env)
    AGENT_CWD = _agent_cwd_path if _agent_cwd_path.is_absolute() else (AGENTS_ROOT / _agent_cwd_path).resolve()
else:
    AGENT_CWD = AGENTS_ROOT

DATA_DIR = AGENT_CWD / "data"                         # /agents/data (unified data directory)
TENANTS_DIR = DATA_DIR / "tenants"                    # /agents/data/tenants (tenant-specific data)
