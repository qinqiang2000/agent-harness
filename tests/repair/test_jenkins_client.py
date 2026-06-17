import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _make_client(tmp_path, **kwargs):
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient

    store = JenkinsBuildStore(str(tmp_path / "jenkins.db"))
    client = JenkinsClient(
        base_url="http://jenkins:8080",
        user="u",
        api_token="t",
        cicd_job="cicd-pipeline",
        cicd_token="tok1",
        autotest_job="at-automated-test",
        autotest_token="tok2",
        build_store=store,
        cicd_poll_seconds=0,
        queue_poll_seconds=0,
        **kwargs,
    )
    return client, store


# ── trigger_build ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_build_cicd_success_triggers_autotest(tmp_path):
    """cicd 全部 SUCCESS 后自动触发 autotest，phase 落在 autotest_building。"""
    client, store = _make_client(tmp_path)

    post_calls = []

    async def fake_post(url, **kwargs):
        post_calls.append(url)
        resp = MagicMock()
        resp.status_code = 201
        if "autotest" in url:
            resp.headers = {"Location": "http://jenkins:8080/queue/item/99/"}
        else:
            resp.headers = {"Location": "http://jenkins:8080/queue/item/42/"}
        return resp

    get_responses = [
        # resolve queue → build_no
        {"executable": {"number": 100}},
        # poll cicd result
        {"building": False, "result": "SUCCESS"},
        # wait autotest queue → build_no
        {"executable": {"number": 200}},
    ]
    get_idx = [0]

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = get_responses[get_idx[0]]
        get_idx[0] += 1
        return resp

    with patch.object(client._http, "post", side_effect=fake_post), \
         patch.object(client._http, "get", side_effect=fake_get):
        token = await client.trigger_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")

    build = store.get_build(token)
    assert build["phase"] == "autotest_building"
    assert build["autotest_build_no"] == 200


@pytest.mark.asyncio
async def test_trigger_build_cicd_failure_stops_early(tmp_path):
    """cicd 失败直接落 done_cicd_failure，不触发 autotest。"""
    client, store = _make_client(tmp_path)

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/42/"}
        return resp

    get_responses = [
        {"executable": {"number": 100}},
        {"building": False, "result": "FAILURE"},
        # consoleText
    ]
    get_idx = [0]

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "consoleText" in url:
            resp.text = "BUILD FAILED"
            return resp
        resp.json.return_value = get_responses[get_idx[0]]
        get_idx[0] += 1
        return resp

    with patch.object(client._http, "post", side_effect=fake_post), \
         patch.object(client._http, "get", side_effect=fake_get):
        token = await client.trigger_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")

    build = store.get_build(token)
    assert build["phase"] == "done_cicd_failure"


@pytest.mark.asyncio
async def test_trigger_build_stores_linear_identifier(tmp_path):
    client, store = _make_client(tmp_path)

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/42/"}
        return resp

    get_responses = [
        {"executable": {"number": 100}},
        {"building": False, "result": "SUCCESS"},
        {"executable": {"number": 200}},
    ]
    get_idx = [0]

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = get_responses[get_idx[0]]
        get_idx[0] += 1
        return resp

    with patch.object(client._http, "post", side_effect=fake_post), \
         patch.object(client._http, "get", side_effect=fake_get):
        token = await client.trigger_build(
            repos=["piaozone/base/api-auth"], branch="fix/ENG-1", linear_identifier="INV-123"
        )

    build = store.get_build(token)
    assert build["linear_identifier"] == "INV-123"


# ── _advance_autotest_building ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_advance_autotest_building_success(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "building": False, "result": "SUCCESS",
            "testReport": {"passCount": 10, "failCount": 0},
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance_autotest_building(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"


@pytest.mark.asyncio
async def test_advance_autotest_building_failure(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "building": False, "result": "FAILURE",
            "testReport": {"passCount": 5, "failCount": 3},
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance_autotest_building(token)

    build = store.get_build(token)
    assert build["phase"] == "done_test_failure"


@pytest.mark.asyncio
async def test_advance_autotest_building_aborted(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": False, "result": "ABORTED"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance_autotest_building(token)

    build = store.get_build(token)
    assert build["phase"] == "done_test_aborted"


@pytest.mark.asyncio
async def test_advance_autotest_building_still_running(tmp_path):
    """building=True 时不改 phase。"""
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": True}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance_autotest_building(token)

    build = store.get_build(token)
    assert build["phase"] == "autotest_building"


# ── get_report_async ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_report_async_returns_none_while_building(tmp_path):
    """autotest 仍在运行时，_advance 后 phase 未变，返回 None。"""
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": True}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        result = await client.get_report_async(token)

    assert result is None


@pytest.mark.asyncio
async def test_get_report_async_returns_report_when_done(tmp_path):
    """autotest 完成后返回报告字典。"""
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "building": False, "result": "SUCCESS",
            "testReport": {"passCount": 8, "failCount": 0},
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        result = await client.get_report_async(token)

    assert result is not None
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_get_report_async_timeout(tmp_path):
    """超时时返回 timeout 报告。"""
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(
        token,
        phase="autotest_building",
        autotest_build_no=200,
        started_at=int(time.time()) - 86401,
    )

    result = await client.get_report_async(token)

    assert result is not None
    assert result["status"] == "timeout"


# ── artifacts download ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_autotest_success_downloads_report(tmp_path):
    mock_artifacts = MagicMock()
    mock_artifacts.download_latest_autotest_report = AsyncMock(return_value=True)
    client, store = _make_client(tmp_path, github_artifacts_client=mock_artifacts)

    token = store.create_build(
        repos=["piaozone/base/api-auth"], branch="fix/ENG-1", linear_identifier="INV-123"
    )
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "building": False, "result": "SUCCESS",
            "testReport": {"passCount": 10, "failCount": 0},
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance_autotest_building(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"
    assert build["report_path"] == f"/tmp/repair/reports/{token}-run.md"
    mock_artifacts.download_latest_autotest_report.assert_called_once_with(
        "INV-123", f"/tmp/repair/reports/{token}-run.md"
    )


@pytest.mark.asyncio
async def test_autotest_success_no_artifacts_client(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(
        repos=["piaozone/base/api-auth"], branch="fix/ENG-1", linear_identifier="INV-123"
    )
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "building": False, "result": "SUCCESS",
            "testReport": {"passCount": 8, "failCount": 0},
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance_autotest_building(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"
    assert build["report_path"] == ""
