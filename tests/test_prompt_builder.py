"""build_initial_prompt 的 skill 自选清单测试：

coordinator-only skill（bug-fix-developer / repair-report-analyzer）出现在自选清单时，
必须带「勿自选」括注，防止入口把流水线内部 skill 当候选误选。

Run: python -m pytest tests/test_prompt_builder.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.utils.prompt_builder import build_initial_prompt


@pytest.mark.unit
async def test_coordinator_only_skills_get_no_self_select_note():
    prompt = await build_initial_prompt(
        tenant_id="",
        user_prompt="某个 bug",
        skill=None,
        default_skills=[
            "customer-service",
            "issue-diagnosis",
            "issue-diagnosis-external",
            "bug-fix-developer",
            "repair-report-analyzer",
        ],
        language="中文",
    )
    # coordinator-only skill 必须带括注
    assert "bug-fix-developer（" in prompt
    assert "repair-report-analyzer（" in prompt
    # 面向用户的 skill 不带括注
    assert "customer-service（" not in prompt
    assert "issue-diagnosis（" not in prompt


@pytest.mark.unit
async def test_self_select_note_mentions_coordinator_only():
    prompt = await build_initial_prompt(
        tenant_id="",
        user_prompt="x",
        skill=None,
        default_skills=["customer-service", "bug-fix-developer"],
        language="中文",
    )
    # 括注语义：仅供流水线/coordinator 内部调用，勿自选
    assert "勿自选" in prompt or "请勿" in prompt


@pytest.mark.unit
async def test_explicit_skill_bypasses_self_select_list():
    # 显式指定 skill 时不走自选清单，原样按 skill 执行
    prompt = await build_initial_prompt(
        tenant_id="",
        user_prompt="x",
        skill="bug-fix-developer",
        default_skills=None,
        language="中文",
    )
    assert "严格按skill: bug-fix-developer" in prompt
    assert "从以下 skill" not in prompt
