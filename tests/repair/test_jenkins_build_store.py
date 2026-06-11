import sys
import time
import threading
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
    import json
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
    store.update_build(token, phase="cicd_building")
    build = store.get_build(token)
    assert build["phase"] == "cicd_building"


def test_update_cicd_build_row(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.update_cicd_build(token, "piaozone/base/api-auth", build_no=123, result="SUCCESS")
    rows = store.list_cicd_builds(token)
    assert rows[0]["build_no"] == 123
    assert rows[0]["result"] == "SUCCESS"


def test_list_non_done_builds(store):
    t1 = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    t2 = store.create_build(repos=["piaozone/base/api-company"], branch="fix/ENG-2")
    store.update_build(t1, phase="done_success")
    pending = store.list_non_done_builds()
    tokens = [r["build_token"] for r in pending]
    assert t2 in tokens
    assert t1 not in tokens


def test_driver_acquire_exclusive(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    assert store.try_acquire_driver(token, owner="proc-A") is True
    assert store.try_acquire_driver(token, owner="proc-B") is False
    assert store.try_acquire_driver(token, owner="proc-A") is True


def test_driver_stale_heartbeat_reacquired(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    store.try_acquire_driver(token, owner="proc-A")
    store.update_build(token, driver_heartbeat=int(time.time()) - 400)
    assert store.try_acquire_driver(token, owner="proc-B", stale_seconds=300) is True


def test_concurrent_acquire(store):
    token = store.create_build(repos=["piaozone/base/api-auth"], branch="fix/ENG-1")
    results = []
    barrier = threading.Barrier(2)

    def try_acquire(name):
        barrier.wait()
        results.append(store.try_acquire_driver(token, owner=name))

    threads = [threading.Thread(target=try_acquire, args=(f"proc-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == 1
