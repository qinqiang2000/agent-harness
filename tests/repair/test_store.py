"""repair_runs SQLite 表测试。

Run: python -m pytest tests/repair/test_store.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.store import RepairStore, RepairRun, Stage


@pytest.fixture
def store(tmp_path):
    return RepairStore(str(tmp_path / "repair_runs.db"))


@pytest.mark.unit
def test_create_and_get(store):
    # Arrange
    run = RepairRun(
        linear_issue_id="uuid-1",
        linear_identifier="ENG-1",
        workspace_id="ws-1",
        stage=Stage.PENDING_REVIEW,
        repo="ai-agent/foo",
        root_cause="空指针",
        repair_plan="加判空",
    )

    # Act
    store.upsert(run)
    fetched = store.get("uuid-1")

    # Assert
    assert fetched is not None
    assert fetched.linear_identifier == "ENG-1"
    assert fetched.stage == Stage.PENDING_REVIEW
    assert fetched.fix_retry_count == 0
    assert fetched.rediagnose_count == 0


@pytest.mark.unit
def test_get_missing_returns_none(store):
    assert store.get("nope") is None


@pytest.mark.unit
def test_upsert_is_idempotent(store):
    # Arrange
    run = RepairRun(linear_issue_id="uuid-1", workspace_id="ws-1", stage=Stage.PENDING_REVIEW)

    # Act: 重复 upsert 不应抛错且不产生第二行
    store.upsert(run)
    first = store.get("uuid-1")
    store.upsert(run)
    second = store.get("uuid-1")

    # Assert
    assert second is not None
    assert len(store.list_by_stage(Stage.PENDING_REVIEW)) == 1
    # created_at 在重复 upsert 后保持稳定
    assert second.created_at == first.created_at


@pytest.mark.unit
def test_update_stage_and_counters(store):
    # Arrange
    store.upsert(RepairRun(linear_issue_id="uuid-1", workspace_id="ws-1", stage=Stage.DEVELOPING))

    # Act
    store.update("uuid-1", stage=Stage.BUILDING, branch="fix/eng-1", mr_url="http://mr/1")
    store.increment_fix_retry("uuid-1")

    # Assert
    fetched = store.get("uuid-1")
    assert fetched.stage == Stage.BUILDING
    assert fetched.branch == "fix/eng-1"
    assert fetched.mr_url == "http://mr/1"
    assert fetched.fix_retry_count == 1


@pytest.mark.unit
def test_list_by_stage(store):
    # Arrange
    store.upsert(RepairRun(linear_issue_id="a", workspace_id="w", stage=Stage.BUILDING))
    store.upsert(RepairRun(linear_issue_id="b", workspace_id="w", stage=Stage.BUILDING))
    store.upsert(RepairRun(linear_issue_id="c", workspace_id="w", stage=Stage.RESOLVED))

    # Act
    building = store.list_by_stage(Stage.BUILDING)

    # Assert
    assert {r.linear_issue_id for r in building} == {"a", "b"}


@pytest.mark.unit
def test_acquire_repos_empty_succeeds(store):
    ok, blocker = store.acquire_repos("issue-1", "ENG-1", ["repo/a", "repo/b"])
    assert ok is True
    assert blocker == ""
    locks = {r["repo"]: r["holder_issue_id"] for r in store.list_locks()}
    assert locks == {"repo/a": "issue-1", "repo/b": "issue-1"}


@pytest.mark.unit
def test_acquire_repos_any_held_fails_whole_group(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/b"])
    ok, blocker = store.acquire_repos("issue-2", "ENG-2", ["repo/a", "repo/b"])
    assert ok is False
    assert blocker == "ENG-1"
    repos_held = {r["repo"] for r in store.list_locks()}
    assert repos_held == {"repo/b"}


@pytest.mark.unit
def test_acquire_repos_same_holder_reentrant(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/a"])
    ok, blocker = store.acquire_repos("issue-1", "ENG-1", ["repo/a", "repo/c"])
    assert ok is True
    assert blocker == ""
    repos_held = {r["repo"] for r in store.list_locks()}
    assert repos_held == {"repo/a", "repo/c"}


@pytest.mark.unit
def test_release_repos_is_idempotent(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/a", "repo/b"])
    store.release_repos("issue-1")
    assert store.list_locks() == []
    store.release_repos("issue-1")
    assert store.list_locks() == []


@pytest.mark.unit
def test_acquire_repos_empty_list_is_noop_success(store):
    ok, blocker = store.acquire_repos("issue-1", "ENG-1", [])
    assert ok is True
    assert blocker == ""
    assert store.list_locks() == []


@pytest.mark.unit
def test_release_repos_only_own_holder(store):
    store.acquire_repos("issue-1", "ENG-1", ["repo/a"])
    store.acquire_repos("issue-2", "ENG-2", ["repo/b"])
    store.release_repos("issue-1")
    repos_held = {r["repo"]: r["holder_issue_id"] for r in store.list_locks()}
    assert repos_held == {"repo/b": "issue-2"}


@pytest.mark.unit
def test_repos_field_persisted(store):
    import json
    from plugins.bundled.repair.store import RepairRun, Stage
    run = RepairRun(
        linear_issue_id="issue-multi",
        workspace_id="ws-1",
        stage=Stage.PENDING_REVIEW,
        repo="piaozone/base/api-auth",
        repos=json.dumps(["piaozone/base/api-auth", "piaozone/base/api-company"]),
    )
    store.upsert(run)
    loaded = store.get("issue-multi")
    assert loaded.repos == json.dumps(["piaozone/base/api-auth", "piaozone/base/api-company"])


@pytest.mark.unit
def test_acquire_repos_concurrent_only_one_wins(tmp_path):
    import threading
    db = str(tmp_path / "concurrent.db")
    RepairStore(db)  # init schema once

    results = {}
    barrier = threading.Barrier(2)

    def worker(issue, ident):
        s = RepairStore(db)  # own connection (separate, like separate processes)
        barrier.wait()  # maximize overlap
        results[issue] = s.acquire_repos(issue, ident, ["repo/shared"])

    t1 = threading.Thread(target=worker, args=("issue-A", "ENG-A"))
    t2 = threading.Thread(target=worker, args=("issue-B", "ENG-B"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    oks = [r[0] for r in results.values()]
    assert sorted(oks) == [False, True]  # exactly one wins
    # the loser's result names the winner's identifier as blocker
    winner = [i for i, r in results.items() if r[0]][0]
    winner_ident = "ENG-A" if winner == "issue-A" else "ENG-B"
    loser_blocker = [r[1] for r in results.values() if not r[0]][0]
    assert loser_blocker == winner_ident
    # exactly one holder in the table
    final = RepairStore(db)
    holders = {row["holder_issue_id"] for row in final.list_locks()}
    assert holders == {winner}
