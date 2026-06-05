"""prompts.py 状态映射与解析函数测试。

Run: python -m pytest tests/repair/test_prompts.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair import prompts


@pytest.mark.unit
def test_classify_state_review_to_developing():
    assert prompts.is_approval_state("In Progress") is True
    assert prompts.is_approval_state("开发中") is True
    assert prompts.is_approval_state("Backlog") is False
    assert prompts.is_approval_state("Triage") is False


@pytest.mark.unit
def test_parse_developer_output_extracts_branch_and_mr():
    text = """
    一些自审说明...
    【分支】fix/ENG-123
    【MR链接】http://gitlab/ai-agent/foo/-/merge_requests/7
    【复现测试】src/test/FooTest.java
    """
    parsed = prompts.parse_developer_output(text)
    assert parsed["branch"] == "fix/ENG-123"
    assert parsed["mr_url"] == "http://gitlab/ai-agent/foo/-/merge_requests/7"
    assert parsed["test_path"] == "src/test/FooTest.java"


@pytest.mark.unit
def test_parse_developer_output_missing_fields():
    parsed = prompts.parse_developer_output("没有结构化字段")
    assert parsed["branch"] == ""
    assert parsed["mr_url"] == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("【判定】已解决", "resolved"),
        ("【判定】代码错", "code_error"),
        ("【判定】根因错", "root_cause_error"),
        ("【判定】漏依赖", "missing_dependency"),
    ],
)
def test_parse_analyzer_verdict(verdict, expected):
    text = f"{verdict}\n【依据】xxx\n【后续动作】yyy"
    parsed = prompts.parse_analyzer_output(text)
    assert parsed["verdict"] == expected


@pytest.mark.unit
def test_parse_analyzer_unknown_verdict_defaults_code_error():
    parsed = prompts.parse_analyzer_output("乱七八糟没有判定")
    assert parsed["verdict"] == "code_error"


@pytest.mark.unit
def test_build_developer_prompt_contains_inputs():
    p = prompts.build_developer_prompt(
        identifier="ENG-123",
        root_cause="空指针",
        evidence="日志 X",
        repair_plan="加判空",
        repo="ai-agent/foo",
        branch="fix/ENG-123",
        is_retry=False,
        last_report="",
    )
    assert "ENG-123" in p
    assert "空指针" in p
    assert "加判空" in p
    assert "fix/ENG-123" in p
    assert "bug-fix-developer" in p


@pytest.mark.unit
def test_build_developer_prompt_retry_includes_report():
    p = prompts.build_developer_prompt(
        identifier="ENG-123",
        root_cause="空指针",
        evidence="日志 X",
        repair_plan="加判空",
        repo="ai-agent/foo",
        branch="fix/ENG-123",
        is_retry=True,
        last_report="测试仍失败：NPE at line 5",
    )
    assert "重修" in p
    assert "NPE at line 5" in p


@pytest.mark.unit
def test_build_analyzer_prompt_contains_report():
    p = prompts.build_analyzer_prompt(
        identifier="ENG-123",
        root_cause="空指针",
        repair_plan="加判空",
        report="3 passed, 0 failed",
    )
    assert "repair-report-analyzer" in p
    assert "3 passed" in p
    assert "ENG-123" in p
