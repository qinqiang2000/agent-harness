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
    dev_output = "【状态】完成\n【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java"
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
            "【状态】完成\n【分支】fix/ENG-1\n【MR链接】http://mr/2",
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
async def test_develop_comment_includes_summary(store, fake_linear):
    # 回写 Linear 的评论应附上 developer 输出的【说明】修复摘要
    _seed_pending(store)
    dev_output = (
        "【状态】完成\n【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java\n"
        "【说明】SUCCESS 状态不再作废已有任务，改为等待自然完成"
    )
    coord, agent, _ = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_development("issue-1")

    bodies = [body for _, body in fake_linear.comments]
    assert any("不再作废已有任务" in b for b in bodies)


@pytest.mark.unit
async def test_develop_not_completed_skips_build_and_rejects(store, fake_linear):
    # developer 未完成（卡批准/没按格式收尾，无【状态】完成）→ 不触发构建，落 REJECTED，回写 agent 输出
    _seed_pending(store)
    incomplete_output = (
        "修改内容说明：把 SUCCESS 分支改为不作废...\n请批准编辑以继续。"  # 无【状态】完成、无分支
    )
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [incomplete_output])

    await coord.start_development("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.REJECTED
    assert jenkins.triggered == []  # 关键：没触发构建
    bodies = [body for _, body in fake_linear.comments]
    assert any("请批准编辑以继续" in b for b in bodies)  # 回写了 agent 实际输出


@pytest.mark.unit
async def test_develop_completed_status_triggers_build(store, fake_linear):
    # developer 明确【状态】完成 + 有分支 → 正常触发构建
    _seed_pending(store)
    dev_output = "【状态】完成\n【分支】fix/ENG-1\n【MR链接】http://mr/1\n【复现测试】FooTest.java"
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_development("issue-1")

    run = store.get("issue-1")
    assert run.stage == Stage.BUILDING
    assert jenkins.triggered == [("ai-agent/foo", "fix/ENG-1")]


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


def _seed_manual(store, stage=Stage.PENDING_REVIEW):
    """人工修复单：handler 先 upsert 一条带 repo+repair_plan 的 run。"""
    store.upsert(
        RepairRun(
            linear_issue_id="manual-1",
            linear_identifier="ENG-M1",
            workspace_id="ws-1",
            stage=stage,
            repo="ai-agent/foo",
            root_cause="（人工单未填，按修复描述处理）",
            repair_plan="任务作废逻辑改为不作废，失败自动重试新增当天任务",
        )
    )


@pytest.mark.unit
async def test_start_manual_repair_happy_path(store, fake_linear):
    # 人工单 created 即开修：不要求 PENDING_REVIEW，直接 DEVELOPING→BUILDING
    _seed_manual(store)
    dev_output = "【状态】完成\n【分支】fix/ENG-M1\n【MR链接】http://mr/m1\n【复现测试】FooTest.java"
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_manual_repair("manual-1")

    run = store.get("manual-1")
    assert run.stage == Stage.BUILDING
    assert run.branch == "fix/ENG-M1"
    assert run.mr_url == "http://mr/m1"
    assert run.develop_session_id == "claude-sess-1"
    assert jenkins.triggered == [("ai-agent/foo", "fix/ENG-M1")]
    # developer 用的是 bug-fix-developer skill
    assert agent.calls[-1].skill == "bug-fix-developer"


@pytest.mark.unit
async def test_start_manual_repair_resolves_repo_from_agent_output(store, fake_linear):
    # 人工单 repo 留空 → agent 查表解析后在输出回填【仓库】→ coordinator 用它触发 Jenkins 并持久化
    store.upsert(
        RepairRun(
            linear_issue_id="manual-2",
            linear_identifier="ENG-M2",
            workspace_id="ws-1",
            stage=Stage.PENDING_REVIEW,
            repo="",  # 留空，交给 agent
            root_cause="（人工单）",
            repair_plan="api-elcinvoice-imputation 任务作废问题",
        )
    )
    dev_output = (
        "【状态】完成\n"
        "【仓库】piaozone/elc-integration/api-elc-invoice-imputation\n"
        "【分支】fix/ENG-M2\n【MR链接】http://mr/m2\n【复现测试】FooTest.java"
    )
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_manual_repair("manual-2")

    run = store.get("manual-2")
    assert run.repo == "piaozone/elc-integration/api-elc-invoice-imputation"
    assert jenkins.triggered == [
        ("piaozone/elc-integration/api-elc-invoice-imputation", "fix/ENG-M2")
    ]


@pytest.mark.unit
async def test_start_manual_repair_with_session_streams_to_session(store, fake_linear):
    # 带 Linear session_id 时：中间步骤 send_thought 进会话，最终结果 send_response 进会话，
    # 不再发 issue 评论
    _seed_manual(store)
    dev_output = "【状态】完成\n【分支】fix/ENG-M1\n【MR链接】http://mr/m1\n【说明】改为不作废"
    coord, agent, jenkins = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_manual_repair("manual-1", session_id="sess-9")

    run = store.get("manual-1")
    assert run.stage == Stage.BUILDING
    # 中间过程进会话 thought
    assert any(sid == "sess-9" for sid, _ in fake_linear.thoughts)
    # 最终结果进会话 response（含 MR）
    assert any(sid == "sess-9" and "http://mr/m1" in body for sid, body in fake_linear.responses)
    # 不再发 issue 评论
    assert fake_linear.comments == []


@pytest.mark.unit
async def test_start_manual_repair_without_session_uses_comment(store, fake_linear):
    # 不带 session_id（向后兼容）→ 仍走 issue 评论
    _seed_manual(store)
    dev_output = "【状态】完成\n【分支】fix/ENG-M1\n【MR链接】http://mr/m1\n【说明】改为不作废"
    coord, agent, _ = _make_coordinator(store, fake_linear, [dev_output])

    await coord.start_manual_repair("manual-1")

    assert len(fake_linear.comments) >= 1
    assert fake_linear.responses == []


@pytest.mark.unit
async def test_start_manual_repair_missing_run_is_noop(store, fake_linear):
    coord, agent, _ = _make_coordinator(store, fake_linear, ["unused"])
    await coord.start_manual_repair("does-not-exist")  # 不抛错
    assert len(agent.calls) == 0


@pytest.mark.unit
async def test_start_manual_repair_skips_when_already_building(store, fake_linear):
    # 已在流水线中（building）的 run 不重复开修，幂等保护
    _seed_manual(store, stage=Stage.BUILDING)
    coord, agent, _ = _make_coordinator(store, fake_linear, ["should not be used"])

    await coord.start_manual_repair("manual-1")

    assert len(agent.calls) == 0


@pytest.mark.unit
async def test_start_manual_repair_agent_failure_goes_rejected_with_comment(store, fake_linear):
    # agent 抛异常 → 落可见终态 REJECTED + 回写评论，不静默卡死
    _seed_manual(store)

    class BoomAgent:
        calls = []
        async def process_query(self, request, context_file_path=None):
            raise RuntimeError("boom")
            yield  # make it a generator

    from tests.repair.conftest import FakeJenkins

    coord = RepairCoordinator(
        agent_service=BoomAgent(),
        store=store,
        jenkins=FakeJenkins(ready=True),
        linear_client_factory=lambda ws: fake_linear,
    )
    await coord.start_manual_repair("manual-1")

    assert store.get("manual-1").stage == Stage.REJECTED
    assert len(fake_linear.comments) >= 1
