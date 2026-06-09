"""restrict-edit-write hook 单元测试（直接调 is_allowed 函数）。

Run: python -m pytest tests/repair/test_restrict_edit_write.py -v
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = ROOT / "agent_cwd" / ".claude" / "hooks"

_spec = importlib.util.spec_from_file_location(
    "restrict_edit_write", str(HOOK_DIR / "restrict-edit-write.py")
)
rew = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rew)


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/work/agent_cwd/data/issue-diagnosis/instincts/cases.md",
        "/tmp/repair/ARALGO-31/src/main/java/com/kingdee/handle/rpa/RPABaseHandle.java",
        "/tmp/repair/ENG-1/src/Foo.java",
        "/tmp/repair/ENG-1/test/FooTest.java",
    ],
)
def test_allows_instincts_and_repair_paths(path):
    assert rew.is_allowed(path) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/tmp/gitlab/src/foo.java",
        "/etc/passwd",
        "/work/agent_cwd/.env",
        "/tmp/other/file.txt",
        "",
    ],
)
def test_denies_other_paths(path):
    assert rew.is_allowed(path) is False
