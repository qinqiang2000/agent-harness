import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _make_client(tmp_path):
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
    )
    return client, store


@pytest.mark.asyncio
async def test_trigger_build_returns_token_and_creates_rows(tmp_path):
    client, store = _make_client(tmp_path)

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/42/"}
        return resp

    with patch.object(client._http, "post", side_effect=fake_post):
        token = await client.trigger_build(
            repos=["piaozone/base/api-auth"], branch="fix/ENG-1"
        )

    assert token
    build = store.get_build(token)
    assert build["phase"] == "cicd_queued"
    rows = store.list_cicd_builds(token)
    assert rows[0]["service"] == "api-auth"
    assert rows[0]["queue_id"] == "42"


@pytest.mark.asyncio
async def test_advance_cicd_queued_to_building(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", queue_id="42")

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"executable": {"number": 100}}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    rows = store.list_cicd_builds(token)
    assert rows[0]["build_no"] == 100
    build = store.get_build(token)
    assert build["phase"] == "cicd_building"


@pytest.mark.asyncio
async def test_advance_cicd_building_success_triggers_autotest(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="cicd_building")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=100, result="PENDING")

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": False, "result": "SUCCESS"}
        return resp

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/99/"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get), \
         patch.object(client._http, "post", side_effect=fake_post):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "autotest_queued"
    assert build["autotest_queue_id"] == "99"


@pytest.mark.asyncio
async def test_advance_cicd_building_failure_shortcircuits(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="cicd_building")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=100, result="PENDING")

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "consoleText" in url:
            resp.text = "BUILD FAILED: compilation error"
            return resp
        resp.json.return_value = {"building": False, "result": "FAILURE"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_cicd_failure"
    report = client.get_report(token)
    assert report["status"] == "failure"
    assert "[构建失败]" in report["summary"]


@pytest.mark.asyncio
async def test_advance_cicd_building_aborted_shortcircuits(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="cicd_building")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=100, result="PENDING")

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "consoleText" in url:
            resp.text = "Aborted by user"
            return resp
        resp.json.return_value = {"building": False, "result": "ABORTED"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_cicd_failure"


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
            "testReport": {"passCount": 10, "failCount": 0}
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"
    report = client.get_report(token)
    assert report["status"] == "success"


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
            "testReport": {"passCount": 5, "failCount": 3}
        }
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_test_failure"
    report = client.get_report(token)
    assert report["status"] == "failure"


@pytest.mark.asyncio
async def test_advance_autotest_aborted(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building", autotest_build_no=200)

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"building": False, "result": "ABORTED"}
        return resp

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_test_aborted"
    report = client.get_report(token)
    assert report["status"] == "failure"
    assert "[测试任务未正常完成]" in report["summary"]


@pytest.mark.asyncio
async def test_advance_timeout(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, started_at=int(time.time()) - 86401)

    await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_timeout"
    report = client.get_report(token)
    assert report["status"] == "timeout"


@pytest.mark.asyncio
async def test_advance_request_exception_does_not_change_phase(tmp_path):
    client, store = _make_client(tmp_path)
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", queue_id="42")

    async def fake_get(url, **kwargs):
        raise httpx.ConnectError("network down")

    with patch.object(client._http, "get", side_effect=fake_get):
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "cicd_queued"


def test_get_report_returns_none_when_not_done(tmp_path):
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient
    store = JenkinsBuildStore(str(tmp_path / "jenkins.db"))
    client = JenkinsClient(
        base_url="http://jenkins:8080", user="u", api_token="t",
        cicd_job="cicd-pipeline", cicd_token="tok1",
        autotest_job="at-automated-test", autotest_token="tok2",
        build_store=store,
    )
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    assert client.get_report(token) is None


@pytest.mark.asyncio
async def test_autotest_success_downloads_report(tmp_path):
    """autotest SUCCESS 时，有 github_artifacts_client 则下载报告并写 report_path。"""
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient

    store = JenkinsBuildStore(str(tmp_path / "jenkins.db"))

    mock_artifacts = MagicMock()
    mock_artifacts.download_latest_autotest_report = AsyncMock(return_value=True)

    client = JenkinsClient(
        base_url="http://jenkins:8080", user="u", api_token="t",
        cicd_job="cicd-pipeline", cicd_token="tok1",
        autotest_job="at-automated-test", autotest_token="tok2",
        build_store=store,
        github_artifacts_client=mock_artifacts,
    )
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
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"
    assert build["report_path"] == f"/tmp/repair/reports/{token}-run.md"
    report = client.get_report(token)
    assert report["report_path"] == build["report_path"]
    mock_artifacts.download_latest_autotest_report.assert_called_once_with("INV-123", f"/tmp/repair/reports/{token}-run.md")


@pytest.mark.asyncio
async def test_autotest_success_fallback_when_no_artifacts_client(tmp_path):
    """无 github_artifacts_client 时，report_path 为空，get_report 正常返回 success。"""
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient

    store = JenkinsBuildStore(str(tmp_path / "jenkins.db"))
    client = JenkinsClient(
        base_url="http://jenkins:8080", user="u", api_token="t",
        cicd_job="cicd-pipeline", cicd_token="tok1",
        autotest_job="at-automated-test", autotest_token="tok2",
        build_store=store,
    )
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
        await client._advance(token)

    build = store.get_build(token)
    assert build["phase"] == "done_success"
    assert build["report_path"] == ""
    report = client.get_report(token)
    assert report["status"] == "success"
    assert report["report_path"] == ""


@pytest.mark.asyncio
async def test_trigger_build_passes_linear_identifier(tmp_path):
    """trigger_build 传入 linear_identifier 后存入 jenkins_builds 表。"""
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient

    store = JenkinsBuildStore(str(tmp_path / "jenkins.db"))
    client = JenkinsClient(
        base_url="http://jenkins:8080", user="u", api_token="t",
        cicd_job="cicd-pipeline", cicd_token="tok1",
        autotest_job="at-automated-test", autotest_token="tok2",
        build_store=store,
    )

    async def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.headers = {"Location": "http://jenkins:8080/queue/item/42/"}
        return resp

    with patch.object(client._http, "post", side_effect=fake_post):
        token = await client.trigger_build(
            repos=["piaozone/base/api-auth"], branch="fix/ENG-1", linear_identifier="INV-123"
        )

    build = store.get_build(token)
    assert build["linear_identifier"] == "INV-123"
