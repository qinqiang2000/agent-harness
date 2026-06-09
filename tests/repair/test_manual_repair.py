"""人工修复单入口分流测试：

- prompts.parse_repo_from_description：从单描述解析 repo（纯函数）
- handler._try_manual_repair：带 autofix label 的 created 事件 → 登记 run + 开修；
  缺 repo → 回写提示不开修；无 label / 无 coordinator → 不拦截，走普通流程。

Run: python -m pytest tests/repair/test_manual_repair.py -v
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.linear.handler import LinearSessionHandler
from plugins.bundled.repair import coordinator as coord_mod
from plugins.bundled.repair import prompts
from plugins.bundled.repair.store import RepairStore, Stage


# ── 纯函数：repo 解析 ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_parse_repo_from_description_basic():
    desc = "任务作废逻辑有问题。\nrepo: ai-agent/api-elcinvoice-imputation\n修复方式：改为不作废。"
    assert prompts.parse_repo_from_description(desc) == "ai-agent/api-elcinvoice-imputation"


@pytest.mark.unit
def test_parse_repo_from_description_chinese_label_and_fullwidth_colon():
    desc = "仓库：ai-agent/foo\n描述..."
    assert prompts.parse_repo_from_description(desc) == "ai-agent/foo"


@pytest.mark.unit
def test_parse_repo_from_description_multi_segment_path():
    # 完整 project_id 是多级路径，不能被截断
    desc = "repo: piaozone/elc-integration/api-elc-invoice-imputation\n描述"
    assert (
        prompts.parse_repo_from_description(desc)
        == "piaozone/elc-integration/api-elc-invoice-imputation"
    )


@pytest.mark.unit
def test_parse_repo_from_description_bare_service_name():
    # 人工只写服务名（无斜杠），也接受，由 agent 查表解析成完整路径
    desc = "服务: api-elc-invoice-imputation\n全量发票查询增量任务作废问题"
    assert prompts.parse_repo_from_description(desc) == "api-elc-invoice-imputation"


@pytest.mark.unit
def test_parse_repo_from_description_missing_returns_empty():
    assert prompts.parse_repo_from_description("没有写仓库的描述") == ""
    assert prompts.parse_repo_from_description("") == ""


# ── 分类解析（纯函数）：是否「要改代码的 bug」，拿不准默认 True ─────────────────

@pytest.mark.unit
def test_parse_is_code_bug_true():
    assert prompts.parse_is_code_bug("【是否代码bug】是\n【理由】逻辑缺陷") is True


@pytest.mark.unit
def test_parse_is_code_bug_false():
    assert prompts.parse_is_code_bug("【是否代码bug】否\n【理由】这是咨询") is False


@pytest.mark.unit
def test_parse_is_code_bug_defaults_true_when_unparseable():
    # 拿不准/解析不出 → 默认 True（倒向修复）
    assert prompts.parse_is_code_bug("模型乱答没按格式") is True
    assert prompts.parse_is_code_bug("") is True


# ── handler 分流 ─────────────────────────────────────────────────────────────

def _make_handler():
    ts = MagicMock()
    ts.get_token.return_value = "tok"
    ts.get_first_workspace_id.return_value = "ws-1"
    return LinearSessionHandler(
        agent_service=MagicMock(),
        token_store=ts,
        config={},
    )


def _fake_client(label_names, description):
    client = MagicMock()
    client.get_issue = AsyncMock(
        return_value={
            "id": "issue-1",
            "identifier": "ENG-1",
            "description": description,
            "team": {"id": "team-1"},
            "label_names": label_names,
        }
    )
    client.send_thought = AsyncMock()
    client.send_response = AsyncMock()
    client.create_comment = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def _reset_coordinator():
    yield
    coord_mod.set_coordinator(None)


@pytest.mark.unit
async def test_try_manual_repair_classified_bug_registers_and_starts(tmp_path):
    # @agent 进来 → 分类判为代码 bug → 登记 + 开修（不再看 label）
    store = RepairStore(str(tmp_path / "r.db"))
    fake_coord = MagicMock()
    fake_coord.store = store
    fake_coord.start_manual_repair = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    handler._classify_is_repair = AsyncMock(return_value=True)
    client = _fake_client([], "repo: ai-agent/foo\n改为不作废")

    with patch("plugins.bundled.linear.handler.LinearClient", return_value=client):
        handled = await handler._try_manual_repair(
            session_id="sess-1", issue_id="issue-1", workspace_id="ws-1", trace_id="t1"
        )

    assert handled is True
    run = store.get("issue-1")
    assert run is not None
    assert run.repo == "ai-agent/foo"
    assert run.stage == Stage.PENDING_REVIEW
    fake_coord.start_manual_repair.assert_awaited_once_with("issue-1")


@pytest.mark.unit
async def test_try_manual_repair_nl_bug_starts_with_empty_repo(tmp_path):
    # 纯自然语言 bug 描述（无 repo: 标签）→ 仍登记并开修，repo 留空交给 agent 查表
    store = RepairStore(str(tmp_path / "r.db"))
    fake_coord = MagicMock()
    fake_coord.store = store
    fake_coord.start_manual_repair = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    handler._classify_is_repair = AsyncMock(return_value=True)
    nl_desc = "api-elcinvoice-imputation 项目全量发票查询增量任务会作废之前的任务，需改为不作废"
    client = _fake_client([], nl_desc)

    with patch("plugins.bundled.linear.handler.LinearClient", return_value=client):
        handled = await handler._try_manual_repair(
            session_id="sess-1", issue_id="issue-1", workspace_id="ws-1", trace_id="t1"
        )

    assert handled is True
    run = store.get("issue-1")
    assert run is not None
    assert run.repo == ""
    assert run.repair_plan == nl_desc
    fake_coord.start_manual_repair.assert_awaited_once_with("issue-1")


@pytest.mark.unit
async def test_try_manual_repair_not_a_bug_falls_through(tmp_path):
    # 分类判为非代码 bug（咨询/诊断）→ 不拦截，返回 False 走普通流程
    store = RepairStore(str(tmp_path / "r.db"))
    fake_coord = MagicMock()
    fake_coord.store = store
    fake_coord.start_manual_repair = AsyncMock()
    coord_mod.set_coordinator(fake_coord)

    handler = _make_handler()
    handler._classify_is_repair = AsyncMock(return_value=False)
    client = _fake_client([], "请帮我查一下这个订单为什么没开票")

    with patch("plugins.bundled.linear.handler.LinearClient", return_value=client):
        handled = await handler._try_manual_repair(
            session_id="sess-1", issue_id="issue-1", workspace_id="ws-1", trace_id="t1"
        )

    assert handled is False
    assert store.get("issue-1") is None
    fake_coord.start_manual_repair.assert_not_awaited()


@pytest.mark.unit
async def test_try_manual_repair_no_coordinator_falls_through():
    coord_mod.set_coordinator(None)
    handler = _make_handler()
    handler._classify_is_repair = AsyncMock(return_value=True)
    client = _fake_client([], "repo: ai-agent/foo")

    with patch("plugins.bundled.linear.handler.LinearClient", return_value=client):
        handled = await handler._try_manual_repair(
            session_id="sess-1", issue_id="issue-1", workspace_id="ws-1", trace_id="t1"
        )

    assert handled is False

