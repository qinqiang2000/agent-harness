"""linear handler Issue 事件委派测试。

Run: python -m pytest tests/repair/test_linear_issue_event.py -v
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.linear.handler import LinearSessionHandler
from plugins.bundled.repair import coordinator as coord_mod


def _make_handler():
    return LinearSessionHandler(
        agent_service=MagicMock(),
        token_store=MagicMock(),
        config={},
    )


@pytest.mark.unit
async def test_issue_event_approval_triggers_start_development():
    fake_coord = MagicMock()
    fake_coord.start_development = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {
            "id": "issue-1",
            "state": {"name": "In Progress", "type": "started"},
        },
    }

    await handler.handle_issue_event(payload)

    fake_coord.start_development.assert_awaited_once_with("issue-1")


@pytest.mark.unit
async def test_issue_event_non_approval_state_ignored():
    fake_coord = MagicMock()
    fake_coord.start_development = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {"id": "issue-1", "state": {"name": "Backlog", "type": "backlog"}},
    }

    await handler.handle_issue_event(payload)

    fake_coord.start_development.assert_not_awaited()


@pytest.mark.unit
async def test_issue_event_no_coordinator_is_safe():
    coord_mod.set_coordinator(None)
    handler = _make_handler()
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {"id": "issue-1", "state": {"name": "In Progress", "type": "started"}},
    }
    await handler.handle_issue_event(payload)
