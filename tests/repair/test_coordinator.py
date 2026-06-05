"""RepairCoordinator 状态机 + 三类归因回转 + N/M 兜底测试。

Run: python -m pytest tests/repair/test_coordinator.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.coordinator import RepairCoordinator
from plugins.bundled.repair.store import RepairRun, Stage
from tests.repair.conftest import FakeAgentService, FakeJenkins


def _make_coordinator(store, fake_linear, agent_results, jenkins_ready=True):
    jenkins = FakeJenkins(ready=jenkins_ready)
    agent = FakeAgentService(agent_results)
    coord = RepairCoordinator(
        agent_service=agent,
        store=store,
        jenkins=jenkins,
        linear_client_factory=lambda ws: fake_linear,
        fix_retry_limit=3,
        rediagnose_limit=2,
    )
    return coord, agent, jenkins


def _seed_pending(store, stage=Stage.PENDING_REVIEW):
    store.upsert(
        RepairRun(
            linear_issue_id="issue-1",
            linear_identifier="ENG-1",
            workspace_id="ws-1",
            stage=stage,
            repo="ai-agent/foo",
            root_cause="空指针",
            repair_plan="加判空",
        )
    )


@pytest.mark.unit
async def test_start_development_happy_path(store, fake_linear):
    _seed_pending(store)
    dev_output = "【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java"
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_development("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.BUILDING
    assert run.branch == "fix/ENG-1"
    assert run.mr_url == "http://mr/1"
    assert run.develop_session_id == "claude-sess-1"
    assert jenkins.triggered == [("ai-agent/foo", "fix/ENG-1")]
    assert run.jenkins_build_id == "build-xyz"


@pytest.mark.unit
async def test_start_development_idempotent_when_not_pending(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(store, fake_linear, ["should not be used"])

    await coord.start_development("issue-1")

    assert len(agent.calls) == 0


@pytest.mark.unit
async def test_analyze_resolved_writes_done_and_comment(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", jenkins_build_id="build-xyz", branch="fix/ENG-1")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】已解决\n【依据】全绿\n【后续动作】无"]
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.RESOLVED
    assert any(kw["state_id"] == "s-done" for _, kw in fake_linear.updated)
    assert len(fake_linear.comments) >= 1


@pytest.mark.unit
async def test_analyze_code_error_resumes_and_increments(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", develop_session_id="claude-sess-1", branch="fix/ENG-1")
    coord, agent, jenkins = _make_coordinator(
        store,
        fake_linear,
        [
            "【判定】代码错\n【依据】NPE 仍在\n【后续动作】补判空",
            "【分支】fix/ENG-1\n【MR链接】http://mr/2",
        ],
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.fix_retry_count == 1
    assert run.stage == Stage.BUILDING
    dev_call = agent.calls[-1]
    assert dev_call.session_id == "claude-sess-1"


@pytest.mark.unit
async def test_code_error_exceeds_limit_goes_rejected(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", fix_retry_count=2, branch="fix/ENG-1", develop_session_id="s1")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】代码错\n【依据】还是错\n【后续动作】x"]
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.fix_retry_count == 3
    assert run.stage == Stage.REJECTED
    assert any(kw["state_id"] == "s-cancel" for _, kw in fake_linear.updated)
    assert len(agent.calls) == 1


@pytest.mark.unit
async def test_root_cause_error_rediagnoses_then_limit(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】根因错\n【依据】根因站不住\n【后续动作】回诊断"]
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.rediagnose_count == 1
    assert len(fake_linear.comments) >= 1


@pytest.mark.unit
async def test_root_cause_error_exceeds_limit_rejected(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", rediagnose_count=1)
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】根因错\n【依据】x\n【后续动作】y"]
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.rediagnose_count == 2
    assert run.stage == Stage.REJECTED


@pytest.mark.unit
async def test_missing_dependency_creates_child_issue(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(
        store,
        fake_linear,
        ["【判定】漏依赖\n【依据】需改上游服务\n【后续动作】建子单：修上游 X"],
    )

    await coord.analyze_report("issue-1")

    assert len(fake_linear.created_issues) >= 1
    assert len(fake_linear.comments) >= 1


@pytest.mark.unit
async def test_analyze_skips_when_jenkins_not_ready(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    store.update("issue-1", jenkins_build_id="build-xyz")
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["should not run"], jenkins_ready=False
    )

    await coord.analyze_report("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.BUILDING
    assert len(agent.calls) == 0


@pytest.mark.unit
async def test_missing_dependency_sets_blocked_stage(store, fake_linear):
    _seed_pending(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(
        store, fake_linear, ["【判定】漏依赖\n【依据】需改上游\n【后续动作】建子单：修上游 X"]
    )

    await coord.analyze_report("issue-1")

    assert store.get("issue-1").stage == Stage.BLOCKED


@pytest.mark.unit
async def test_analyze_report_missing_run_is_noop(store, fake_linear):
    coord, agent, _ = _make_coordinator(store, fake_linear, ["unused"])
    await coord.analyze_report("does-not-exist")  # 不抛错
    assert len(agent.calls) == 0


@pytest.mark.unit
async def test_start_development_rolls_back_on_agent_failure(store, fake_linear):
    # agent 抛异常 → 回退 PENDING_REVIEW
    _seed_pending(store)

    class BoomAgent:
        calls = []
        async def process_query(self, request, context_file_path=None):
            raise RuntimeError("boom")
            yield  # make it a generator

    from plugins.bundled.repair.coordinator import RepairCoordinator
    from tests.repair.conftest import FakeJenkins

    coord = RepairCoordinator(
        agent_service=BoomAgent(),
        store=store,
        jenkins=FakeJenkins(ready=True),
        linear_client_factory=lambda ws: fake_linear,
    )
    await coord.start_development("issue-1")

    assert store.get("issue-1").stage == Stage.PENDING_REVIEW
