"""RepairChannelPlugin 构造与 singleton 注册测试。

Run: python -m pytest tests/repair/test_plugin.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair import coordinator as coord_mod
from plugins.bundled.repair.plugin import RepairChannelPlugin


def _make_api(tmp_path):
    api = MagicMock()
    api.config = {
        "repair_db_path": str(tmp_path / "repair.db"),
        "poll_interval_seconds": 60,
        "fix_retry_limit": 3,
        "rediagnose_limit": 2,
    }
    api.agent_service = MagicMock()
    return api


@pytest.mark.unit
def test_plugin_registers_singleton(tmp_path):
    coord_mod.set_coordinator(None)
    api = _make_api(tmp_path)

    plugin = RepairChannelPlugin(api)

    assert coord_mod.get_coordinator() is not None
    assert plugin.get_meta().id == "repair"


@pytest.mark.unit
async def test_on_start_without_poll_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("REPAIR_POLL_ENABLED", "false")
    api = _make_api(tmp_path)
    plugin = RepairChannelPlugin(api)

    await plugin.on_start()
    await plugin.on_stop()


@pytest.mark.unit
def test_create_router_has_webhook(tmp_path):
    api = _make_api(tmp_path)
    plugin = RepairChannelPlugin(api)
    router = plugin.create_router()
    paths = [r.path for r in router.routes]
    assert any("/repair/gitlab/webhook" in p for p in paths)
