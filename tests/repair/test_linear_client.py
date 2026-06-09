"""LinearClient 写方法测试（mock GraphQL）。

Run: python -m pytest tests/repair/test_linear_client.py -v
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.linear.linear_client import LinearClient


@pytest.mark.unit
async def test_create_issue_builds_mutation():
    client = LinearClient("token-x")
    fake_data = {
        "issueCreate": {
            "success": True,
            "issue": {"id": "uuid-9", "identifier": "ENG-9", "url": "http://x/ENG-9"},
        }
    }
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)) as q:
        result = await client.create_issue(
            team_id="team-1",
            title="bug: NPE",
            description="根因...",
        )

    assert result["id"] == "uuid-9"
    assert result["identifier"] == "ENG-9"
    assert result["url"] == "http://x/ENG-9"
    args, kwargs = q.call_args
    assert "issueCreate" in args[0]
    assert args[1]["input"]["teamId"] == "team-1"
    assert args[1]["input"]["title"] == "bug: NPE"


@pytest.mark.unit
async def test_create_comment_builds_mutation():
    client = LinearClient("token-x")
    fake_data = {"commentCreate": {"success": True, "comment": {"id": "c-1"}}}
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)) as q:
        cid = await client.create_comment("issue-1", "分析结果...")

    assert cid == "c-1"
    args, _ = q.call_args
    assert "commentCreate" in args[0]
    assert args[1]["input"]["issueId"] == "issue-1"
    assert args[1]["input"]["body"] == "分析结果..."


@pytest.mark.unit
async def test_get_issue_returns_label_names():
    client = LinearClient("token-x")
    fake_data = {
        "issue": {
            "id": "uuid-1",
            "identifier": "ENG-1",
            "title": "bug",
            "description": "desc",
            "team": {"id": "team-1", "name": "Eng"},
            "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
            "assignee": None,
            "delegate": None,
            "priority": 0,
            "priorityLabel": "No priority",
            "labels": {
                "nodes": [
                    {"id": "l1", "name": "auto-fix"},
                    {"id": "l2", "name": "bug"},
                ]
            },
        }
    }
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)) as q:
        issue = await client.get_issue("uuid-1")

    # GraphQL query 必须请求 labels
    args, _ = q.call_args
    assert "labels" in args[0]
    # 返回整理成 label_names 列表
    assert issue["label_names"] == ["auto-fix", "bug"]


@pytest.mark.unit
async def test_get_issue_label_names_empty_when_no_labels():
    client = LinearClient("token-x")
    fake_data = {
        "issue": {
            "id": "uuid-1",
            "identifier": "ENG-1",
            "title": "bug",
            "description": "desc",
            "team": {"id": "team-1", "name": "Eng"},
            "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
            "assignee": None,
            "delegate": None,
            "priority": 0,
            "priorityLabel": "No priority",
            "labels": {"nodes": []},
        }
    }
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)):
        issue = await client.get_issue("uuid-1")

    assert issue["label_names"] == []


@pytest.mark.unit
async def test_get_workflow_states_returns_list():
    client = LinearClient("token-x")
    fake_data = {
        "team": {
            "states": {
                "nodes": [
                    {"id": "s1", "name": "Backlog", "type": "backlog", "position": 0},
                    {"id": "s2", "name": "In Progress", "type": "started", "position": 1},
                ]
            }
        }
    }
    with patch.object(client, "_query", new=AsyncMock(return_value=fake_data)):
        states = await client.get_workflow_states("team-1")

    assert len(states) == 2
    assert states[1]["name"] == "In Progress"
