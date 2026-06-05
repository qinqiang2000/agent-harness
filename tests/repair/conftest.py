"""repair 测试共享 fixture：临时 store、fake LinearClient、fake JenkinsClient、
fake AgentService。"""

import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.store import RepairStore


@pytest.fixture
def store(tmp_path):
    return RepairStore(str(tmp_path / "repair_runs.db"))


class FakeLinearClient:
    """记录所有写操作，便于断言。"""

    def __init__(self):
        self.updated = []  # (issue_id, kwargs)
        self.comments = []  # (issue_id, body)
        self.created_issues = []  # input dicts
        self._next_issue = {"id": "child-uuid", "identifier": "ENG-CHILD", "url": "http://x"}
        self._states = [
            {"id": "s-backlog", "name": "Backlog", "type": "backlog", "position": 0},
            {"id": "s-prog", "name": "In Progress", "type": "started", "position": 1},
            {"id": "s-done", "name": "Done", "type": "completed", "position": 2},
            {"id": "s-cancel", "name": "Canceled", "type": "canceled", "position": 3},
        ]

    async def update_issue(self, issue_id, state_id=None, delegate_id=None, description=None):
        self.updated.append((issue_id, {"state_id": state_id, "description": description}))

    async def create_comment(self, issue_id, body):
        self.comments.append((issue_id, body))
        return "comment-id"

    async def create_issue(self, team_id, title, description="", state_id=None, delegate_id=None):
        self.created_issues.append(
            {"team_id": team_id, "title": title, "description": description}
        )
        return dict(self._next_issue)

    async def get_workflow_states(self, team_id):
        return list(self._states)

    async def get_issue(self, issue_id):
        return {"id": issue_id, "identifier": "ENG-1", "team": {"id": "team-1"}}


class FakeJenkins:
    def __init__(self, ready=True):
        self.ready = ready
        self.triggered = []

    def trigger_build(self, repo, branch):
        self.triggered.append((repo, branch))
        return "build-xyz"

    def get_report(self, build_id):
        if not self.ready:
            return None
        return {"status": "success", "summary": "3 passed", "failures": []}


class FakeAgentService:
    """按预设脚本逐次返回 result 文本。process_query 是 async generator。"""

    def __init__(self, scripted_results):
        # scripted_results: list[str]，每次 process_query 弹一个
        self._results = list(scripted_results)
        self.calls = []  # 记录每次 QueryRequest

    async def process_query(self, request, context_file_path=None):
        self.calls.append(request)
        text = self._results.pop(0) if self._results else ""
        yield {"type": "session_created", "data": {"session_id": "claude-sess-1"}}
        yield {"type": "result", "data": {"result": text}}


@pytest.fixture
def fake_linear():
    return FakeLinearClient()


@pytest.fixture
def fake_jenkins():
    return FakeJenkins(ready=True)
