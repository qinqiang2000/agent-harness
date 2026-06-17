import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore


@pytest.fixture
def store(tmp_path):
    return JenkinsBuildStore(str(tmp_path / "jenkins.db"))


def test_create_build(store):
    token = store.create_build(
        repos=["piaozone/base/api-auth", "piaozone/base/api-company"],
        branch="fix/ENG-1",
    )
    assert token
    build = store.get_build(token)
    assert build is not None
    assert build["phase"] == "cicd_queued"
    assert build["branch"] == "fix/ENG-1"
    assert json.loads(build["repos_json"]) == ["piaozone/base/api-auth", "piaozone/base/api-company"]


def test_create_cicd_build_rows(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    rows = store.list_cicd_builds(token)
    assert len(rows) == 1
    assert rows[0]["repo"] == "piaozone/base/api-auth"
    assert rows[0]["service"] == "api-auth"
    assert rows[0]["result"] == "PENDING"


def test_update_build_phase(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building")
    build = store.get_build(token)
    assert build["phase"] == "autotest_building"


def test_update_cicd_build_row(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=123, result="SUCCESS")
    rows = store.list_cicd_builds(token)
    assert rows[0]["build_no"] == 123
    assert rows[0]["result"] == "SUCCESS"


def test_is_done_false_when_building(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="autotest_building")
    assert store.is_done(token) is False


def test_is_done_true_when_success(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_build(token, phase="done_success")
    assert store.is_done(token) is True


def test_is_done_true_for_unknown_token(store):
    assert store.is_done("nonexistent") is True


def test_schema_has_no_driver_columns(store):
    """driver_owner / driver_heartbeat 列不应存在于新建的 DB。"""
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    build = store.get_build(token)
    assert "driver_owner" not in build
    assert "driver_heartbeat" not in build
