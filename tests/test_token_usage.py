"""token_usage_store 的归因与聚合逻辑测试。"""

import datetime
import os
import tempfile

import pytest


@pytest.fixture()
def store(monkeypatch):
    """每个用例使用独立的临时数据库，避免污染真实 data/token_usage.db。

    Args:
        monkeypatch: pytest 提供的环境变量补丁工具

    Returns:
        已指向临时目录的 token_usage_store 模块
    """
    monkeypatch.setenv("TOKEN_USAGE_DATA_DIR", tempfile.mkdtemp())
    monkeypatch.setenv("TOKEN_CHARS_PER_TOKEN", "3.0")
    from api.services import token_usage_store

    return token_usage_store


def _record(store, request_id, issue_key, skill, usage, total_turns, tools):
    """写入一次请求的用量与工具明细，简化用例样板代码。

    Args:
        store: token_usage_store 模块
        request_id: 请求唯一标识
        issue_key: issue identifier，可为 None
        skill: skill 名
        usage: SDK usage 字典
        total_turns: 主 agent 总轮次
        tools: 工具返回明细列表
    """
    store.record_session(
        request_id=request_id,
        session_id=f"sess-{request_id}",
        issue_key=issue_key,
        issue_id=None,
        skill=skill,
        tenant_id="t1",
        channel="linear",
        model="claude-agy-sonnet",
        usage=usage,
        cost_sdk_usd=None,
        num_turns=total_turns,
        total_turns=total_turns,
        duration_ms=1000,
        status="success",
    )
    store.record_tool_volume(request_id, tools)


def test_bucket_of_maps_tools():
    """工具名应被正确归一化到归因桶。"""
    from api.services.token_usage_store import bucket_of

    assert bucket_of("mcp__elastic__searchTraceOrKeyWordsLog") == "ELK日志"
    assert bucket_of("Read") == "源码读取"
    assert bucket_of("Grep") == "源码读取"
    assert bucket_of("Task") == "子agent"
    assert bucket_of("SomethingUnknown") == "其他"


def test_attribution_sums_to_real_total(store):
    """归因各桶之和必须恒等于真实计费 token，不允许凭空多算或漏算。"""
    buckets = store.attribute_buckets(
        [
            {"bucket": "源码读取", "result_chars": 30000, "turn_idx": 1, "total_turns": 5},
            {"bucket": "ELK日志", "result_chars": 15000, "turn_idx": 2, "total_turns": 5},
        ],
        input_tokens_total=200000,
        output_tokens_total=3000,
    )
    assert sum(buckets.values()) == 203000
    assert "系统底座" in buckets
    # 早出现的内容被重放更多轮，权重应更高
    assert buckets["源码读取"] > buckets["ELK日志"]


def test_attribution_scales_when_estimate_exceeds_real(store):
    """字符估算超过真实总量时应等比压缩，且总和仍然守恒。"""
    buckets = store.attribute_buckets(
        [{"bucket": "源码读取", "result_chars": 9_000_000, "turn_idx": 0, "total_turns": 10}],
        input_tokens_total=50000,
        output_tokens_total=0,
    )
    assert sum(buckets.values()) == 50000
    assert buckets["系统底座"] > 0


def test_attribution_without_tools_is_all_base(store):
    """没有任何工具调用时，输入应全部归入系统底座。"""
    buckets = store.attribute_buckets([], input_tokens_total=23585, output_tokens_total=6)
    assert buckets["系统底座"] == 23585
    assert buckets["模型输出"] == 6


def test_issue_aggregates_multiple_sessions(store):
    """同一 issue 的多次独立对话（诊断 + code-fix）应聚合为一笔账。"""
    usage = {
        "input_tokens": 10000,
        "output_tokens": 2000,
        "cache_creation_input_tokens": 5000,
        "cache_read_input_tokens": 80000,
    }
    _record(store, "req-a", "CNPRD-1276", "issue-diagnosis-billing", usage, 6,
            [{"tool_name": "Read", "target": "A.java", "result_chars": 20000,
              "turn_idx": 2, "is_subagent": False}])
    _record(store, "req-b", "CNPRD-1276", "code-fix", usage, 4,
            [{"tool_name": "Read", "target": "B.java", "result_chars": 10000,
              "turn_idx": 1, "is_subagent": False}])

    detail = store.issue_detail("CNPRD-1276")
    assert detail["totals"]["sessions"] == 2
    assert detail["totals"]["tokens"] == 2 * (10000 + 2000 + 5000 + 80000)
    assert sum(detail["buckets"].values()) == detail["totals"]["tokens"]


def test_channel_issue_binding_roundtrip(store):
    """渠道会话与 issue 的绑定应可写入并反查，支撑后续轮次归因。"""
    store.bind_channel_issue("linear", "agentsess-1", "CNPRD-1276", "uuid-1")
    assert store.lookup_channel_issue("linear", "agentsess-1") == {
        "issue_key": "CNPRD-1276",
        "issue_id": "uuid-1",
    }
    assert store.lookup_channel_issue("linear", "unknown")["issue_key"] is None


def test_summarize_day_ranks_issues_by_cost(store):
    """日聚合应按成本降序排列 issue，无 issue 的请求归入 _adhoc。"""
    big = {"input_tokens": 50000, "output_tokens": 10000,
           "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    small = {"input_tokens": 1000, "output_tokens": 100,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    _record(store, "r1", "CNPRD-1", "issue-diagnosis-billing", big, 3, [])
    _record(store, "r2", "CNPRD-2", "issue-diagnosis-billing", small, 2, [])
    _record(store, "r3", None, None, small, 1, [])

    today = datetime.date.today().strftime("%Y%m%d")
    summary = store.summarize_day(today)
    keys = [i["issue_key"] for i in summary["by_issue"]]
    assert keys[0] == "CNPRD-1"
    assert "_adhoc" in keys
    assert summary["totals"]["requests"] == 3


def test_summarize_empty_day_returns_placeholder(store):
    """没有数据的日期应返回空结构而非报错。"""
    summary = store.summarize_day("19990101")
    assert summary["totals"] == {}
    assert summary["by_issue"] == []
