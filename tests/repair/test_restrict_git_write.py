"""restrict-git-write hook 单元测试（直接调 decide 函数）。

Run: python -m pytest tests/repair/test_restrict_git_write.py -v
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = ROOT / "agent_cwd" / ".claude" / "hooks"

_spec = importlib.util.spec_from_file_location(
    "restrict_git_write", str(HOOK_DIR / "restrict-git-write.py")
)
rgw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rgw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        "cd /tmp/repair/ENG-1 && git add -A",
        "git -C /tmp/repair/ENG-1 commit -m 'fix'",
        "cd /tmp/repair/ENG-1 && git checkout -b fix/ENG-1",
        "cd /tmp/repair/ENG-1 && git push -o merge_request.create origin fix/ENG-1",
    ],
)
def test_allows_git_write_in_repair_dir(cmd):
    assert rgw.decide(cmd) == "allow"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        "git add -A",
        "cd /tmp/gitlab/src/foo && git commit -m x",
        "git checkout -b feature/x",
    ],
)
def test_denies_git_write_outside_repair(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        "cd /tmp/repair/ENG-1 && git merge main",
        "cd /tmp/repair/ENG-1 && git push origin main",
        "cd /tmp/repair/ENG-1 && git push origin master",
        "cd /tmp/repair/ENG-1 && git push -o merge_request.merge_when_pipeline_succeeds origin fix/x",
    ],
)
def test_denies_dangerous_even_in_repair_dir(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
def test_non_git_command_is_allow():
    assert rgw.decide("ls -la /tmp/repair/ENG-1") == "allow"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        # refspec 形式推主干，必须 deny（即便在 repair 目录）
        "cd /tmp/repair/ENG-1 && git push origin HEAD:main",
        "cd /tmp/repair/ENG-1 && git push origin fix:master",
        "cd /tmp/repair/ENG-1 && git push origin HEAD:refs/heads/main",
        "cd /tmp/repair/ENG-1 && git push origin +HEAD:main",
    ],
)
def test_denies_refspec_push_to_trunk(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        # /tmp/repair/ 只出现在无关位置（echo/注释），真实 git 在别处 → deny
        "echo /tmp/repair/ ; cd /important && git push origin feature",
        "echo see /tmp/repair/ for notes && git -C /important commit -m x",
        "# /tmp/repair/ENG-1\ngit add -A",
    ],
)
def test_denies_when_git_not_scoped_to_repair(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd",
    [
        # force push 即便在 repair 目录也 deny（可能改写远端已建 MR 分支历史）
        "cd /tmp/repair/ENG-1 && git push --force origin fix/ENG-1",
        "cd /tmp/repair/ENG-1 && git push -f origin fix/ENG-1",
        "cd /tmp/repair/ENG-1 && git push --force-with-lease origin fix/ENG-1",
    ],
)
def test_denies_force_push(cmd):
    assert rgw.decide(cmd) == "deny"


@pytest.mark.unit
def test_decide_handles_none_and_empty():
    assert rgw.decide(None) == "allow"   # 非字符串/空 → 不拦截（交给其它规则），且不崩溃
    assert rgw.decide("") == "allow"
