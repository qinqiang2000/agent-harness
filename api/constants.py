"""Global constants for the AI Agent Service."""

import os
from pathlib import Path

# Timeout for waiting on first message from Claude SDK (seconds)
FIRST_MESSAGE_TIMEOUT = int(os.getenv("CLAUDE_FIRST_MESSAGE_TIMEOUT", "120"))

# Directory paths
AGENTS_ROOT = Path(__file__).resolve().parent.parent  # /agents
DATA_DIR = AGENTS_ROOT / "data"                       # /agents/data (unified data directory)
TENANTS_DIR = DATA_DIR / "tenants"                    # /agents/data/tenants (tenant-specific data)
