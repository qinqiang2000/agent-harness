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

# Plugin directories
PLUGINS_DIR = AGENTS_ROOT / "plugins"                  # /agents/plugins
BUNDLED_PLUGINS_DIR = PLUGINS_DIR / "bundled"          # /agents/plugins/bundled
INSTALLED_PLUGINS_DIR = PLUGINS_DIR / "installed"      # /agents/plugins/installed
PLUGIN_CONFIG_FILE = PLUGINS_DIR / "config.json"       # /agents/plugins/config.json


# 云之家推送消息统一前缀，便于在众多通知中一眼识别消息来源项目。
# 可用环境变量 NOTIFY_MSG_PREFIX 覆盖。
NOTIFY_MSG_PREFIX = os.getenv("NOTIFY_MSG_PREFIX", "【CodingAgent项目】")
