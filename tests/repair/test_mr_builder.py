"""MRBuilder：测试通过后用 git push options 建 MR。

Run: python -m pytest tests/repair/test_mr_builder.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.mr_builder import MRBuilder, parse_mr_url


@pytest.mark.unit
def test_parse_mr_url_from_git_remote_output():
    out = (
        "remote:\n"
        "remote: View merge request for fix/ENG-1:\n"
        "remote:   http://gitlab.example/ai-agent/foo/-/merge_requests/42\n"
        "remote:\n"
    )
    assert parse_mr_url(out) == "http://gitlab.example/ai-agent/foo/-/merge_requests/42"


@pytest.mark.unit
def test_parse_mr_url_returns_empty_when_absent():
    assert parse_mr_url("everything up-to-date") == ""


@pytest.mark.unit
def test_build_mr_invokes_git_push_with_options():
    captured = {}

    def fake_run(cmd, cwd, capture):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return "remote:   http://gitlab.example/foo/-/merge_requests/7\n"

    builder = MRBuilder(runner=fake_run)
    url = builder.build_mr(
        identifier="ENG-1", branch="fix/ENG-1", title="fix(ENG-1): 修复空指针"
    )

    assert url == "http://gitlab.example/foo/-/merge_requests/7"
    assert captured["cwd"] == "/tmp/repair/ENG-1"
    joined = " ".join(captured["cmd"])
    assert "merge_request.create" in joined
    assert "merge_request.target=test" in joined
    assert "fix/ENG-1" in captured["cmd"]
