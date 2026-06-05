"""JenkinsClient 占位契约测试。

Run: python -m pytest tests/repair/test_jenkins_client.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.jenkins_client import JenkinsClient


@pytest.mark.unit
def test_trigger_build_returns_id():
    client = JenkinsClient()
    build_id = client.trigger_build(repo="ai-agent/foo", branch="fix/ENG-1")
    assert isinstance(build_id, str)
    assert build_id  # 非空


@pytest.mark.unit
def test_get_report_not_ready_returns_none():
    client = JenkinsClient(mock_ready=False)
    assert client.get_report("build-1") is None


@pytest.mark.unit
def test_get_report_ready_returns_dict():
    client = JenkinsClient(mock_ready=True)
    report = client.get_report("build-1")
    assert report is not None
    assert "status" in report
    assert "summary" in report
