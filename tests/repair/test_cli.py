"""cli.py create-issue 测试。

Run: python -m pytest tests/repair/test_cli.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair import cli


@pytest.mark.unit
def test_load_payload_reads_json(tmp_path):
    p = tmp_path / "payload.json"
    p.write_text(
        json.dumps(
            {
                "team_id": "team-1",
                "title": "bug: NPE",
                "root_cause": "空指针",
                "evidence": "日志",
                "repair_plan": "判空",
                "repo": "ai-agent/foo",
            }
        ),
        encoding="utf-8",
    )
    data = cli.load_payload(str(p))
    assert data["title"] == "bug: NPE"
    assert data["repo"] == "ai-agent/foo"


@pytest.mark.unit
def test_build_description_combines_fields():
    desc = cli.build_description(
        root_cause="空指针", evidence="日志 X", repair_plan="判空"
    )
    assert "空指针" in desc
    assert "日志 X" in desc
    assert "判空" in desc
    assert "根因" in desc


@pytest.mark.unit
async def test_create_issue_flow_writes_store_and_prints(tmp_path, capsys):
    payload = {
        "team_id": "team-1",
        "workspace_id": "ws-1",
        "title": "bug: NPE",
        "root_cause": "空指针",
        "evidence": "日志",
        "repair_plan": "判空",
        "repo": "ai-agent/foo",
    }
    pfile = tmp_path / "payload.json"
    pfile.write_text(json.dumps(payload), encoding="utf-8")

    fake_client = MagicMock()
    fake_client.create_issue = AsyncMock(
        return_value={"id": "issue-uuid", "identifier": "ENG-7", "url": "http://x"}
    )
    store = MagicMock()

    # _make_linear_client 真实返回 (client, workspace_id) 元组，mock 也遵守此契约
    with patch.object(
        cli, "_make_linear_client", return_value=(fake_client, "ws-1")
    ), patch.object(cli, "_make_store", return_value=store):
        await cli.create_issue_cmd(str(pfile))

    out = capsys.readouterr().out.strip().splitlines()[-1]
    result = json.loads(out)
    assert result["ok"] is True
    assert result["identifier"] == "ENG-7"
    assert result["issue_id"] == "issue-uuid"
    store.upsert.assert_called_once()


@pytest.mark.unit
def test_acquire_lock_success_prints_ok(tmp_path, capsys):
    from unittest.mock import MagicMock
    store = MagicMock()
    store.acquire_repos.return_value = (True, "")
    with patch.object(cli, "_make_store", return_value=store):
        cli.acquire_lock_cmd(
            issue_id="issue-uuid", identifier="ENG-7", repos_csv="repo/a,repo/b"
        )
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out == {"ok": True}
    store.acquire_repos.assert_called_once_with(
        "issue-uuid", "ENG-7", ["repo/a", "repo/b"]
    )


@pytest.mark.unit
def test_acquire_lock_blocked_prints_blocked_by(tmp_path, capsys):
    from unittest.mock import MagicMock
    store = MagicMock()
    store.acquire_repos.return_value = (False, "ENG-3")
    with patch.object(cli, "_make_store", return_value=store):
        cli.acquire_lock_cmd(
            issue_id="issue-uuid", identifier="ENG-7", repos_csv="repo/a"
        )
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out == {"ok": False, "blocked_by": "ENG-3"}


def test_retrigger_build_rejects_wrong_stage(tmp_path, monkeypatch):
    import json
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    db = str(tmp_path / "r.db")
    store = RepairStore(db)
    store.upsert(RepairRun(
        linear_issue_id="issue-1",
        linear_identifier="ENG-1",
        workspace_id="ws-1",
        stage=Stage.DEVELOPING,
        repo="ai-agent/foo",
        repos='["ai-agent/foo"]',
        branch="fix/ENG-1",
    ))
    monkeypatch.setenv("REPAIR_DB_PATH", db)

    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "plugins/bundled/repair/cli.py", "retrigger-build", "--issue", "issue-1"],
        capture_output=True, text=True,
        cwd="/Users/jinfan/code/git-agent/agent-harness",
    )
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "不可重跑" in output.get("error", "")


def test_retrigger_build_rejects_empty_branch(tmp_path, monkeypatch):
    import json
    from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
    db = str(tmp_path / "r.db")
    store = RepairStore(db)
    store.upsert(RepairRun(
        linear_issue_id="issue-2",
        linear_identifier="ENG-2",
        workspace_id="ws-1",
        stage=Stage.REJECTED,
        repo="ai-agent/foo",
        repos='["ai-agent/foo"]',
        branch="",
    ))
    monkeypatch.setenv("REPAIR_DB_PATH", db)

    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "plugins/bundled/repair/cli.py", "retrigger-build", "--issue", "issue-2"],
        capture_output=True, text=True,
        cwd="/Users/jinfan/code/git-agent/agent-harness",
    )
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "分支" in output.get("error", "")
