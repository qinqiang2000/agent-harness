"""端到端集成测试：审核 webhook → 开发 → 轮询 → 分析 → 终态。
全部 mock 外部（Linear / Jenkins / AgentService）。

Run: python -m pytest tests/repair/test_integration.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.coordinator import RepairCoordinator
from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
from tests.repair.conftest import FakeAgentService, FakeJenkins, FakeLinearClient


@pytest.mark.integration
async def test_happy_path_end_to_end(tmp_path):
    store = RepairStore(str(tmp_path / "r.db"))
    store.upsert(
        RepairRun(
            linear_issue_id="issue-1",
            linear_identifier="ENG-1",
            workspace_id="ws-1",
            stage=Stage.PENDING_REVIEW,
            repo="ai-agent/foo",
            root_cause="空指针",
            repair_plan="判空",
        )
    )
    fake_linear = FakeLinearClient()
    agent = FakeAgentService(
        [
            "【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java",  # developer
            "【判定】已解决\n【依据】全绿\n【后续动作】无",  # analyzer
        ]
    )
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=FakeJenkins(ready=True),
        linear_client_factory=lambda ws: fake_linear,
    )

    await coord.start_development("issue-1")
    assert store.get("issue-1").stage == Stage.BUILDING
    await coord.poll_building_runs()

    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    assert run.mr_url == "http://mr/1"
    assert any(kw["state_id"] == "s-done" for _, kw in fake_linear.updated)


@pytest.mark.integration
async def test_code_error_retry_then_resolve(tmp_path):
    store = RepairStore(str(tmp_path / "r.db"))
    store.upsert(
        RepairRun(
            linear_issue_id="issue-1",
            linear_identifier="ENG-1",
            workspace_id="ws-1",
            stage=Stage.PENDING_REVIEW,
            repo="ai-agent/foo",
            root_cause="空指针",
            repair_plan="判空",
        )
    )
    fake_linear = FakeLinearClient()
    agent = FakeAgentService(
        [
            "【分支】fix/ENG-1\n【MR链接】http://mr/1",  # developer 首次
            "【判定】代码错\n【依据】NPE 仍在\n【后续动作】补判空",  # analyzer 第一轮
            "【分支】fix/ENG-1\n【MR链接】http://mr/2",  # developer 重修
            "【判定】已解决\n【依据】绿\n【后续动作】无",  # analyzer 第二轮
        ]
    )
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=FakeJenkins(ready=True),
        linear_client_factory=lambda ws: fake_linear,
    )

    await coord.start_development("issue-1")  # → building
    await coord.poll_building_runs()  # analyzer 代码错 → resume 重修 → building
    assert store.get("issue-1").fix_retry_count == 1
    assert store.get("issue-1").stage == Stage.BUILDING
    await coord.poll_building_runs()  # analyzer 已解决 → resolved

    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    dev_calls = [c for c in agent.calls if c.session_id]
    assert any(c.session_id == "claude-sess-1" for c in dev_calls)
