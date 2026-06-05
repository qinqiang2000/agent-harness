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
