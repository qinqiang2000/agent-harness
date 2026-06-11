"""测试通过后由 coordinator 调用，在修复单工作目录内用 git push options 建 MR。

不引入 GitLab REST 客户端（沿用现有 push options 方案）。push 用写权限
GITLAB_PUSH_TOKEN（回退 GITLAB_TOKEN）。runner 可注入便于测试。
"""

import logging
import re
import subprocess
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MR_URL_RE = re.compile(r"(https?://\S*/-/merge_requests/\d+)")


def parse_mr_url(git_output: str) -> str:
    """从 git push 的 remote 输出里解析 MR URL，无则返回空串。"""
    m = _MR_URL_RE.search(git_output)
    return m.group(1) if m else ""


def _default_runner(cmd: list, cwd: str, capture: bool = True) -> str:
    """实跑 git，返回合并后的 stdout+stderr（push 的 remote 行在 stderr）。"""
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=120
    )
    return (proc.stdout or "") + (proc.stderr or "")


class MRBuilder:
    """在 /tmp/repair/<identifier>/ 内 git push -o merge_request.create 建 MR。"""

    def __init__(self, runner: Optional[Callable] = None):
        self._run = runner or _default_runner

    def build_mr(self, identifier: str, branch: str, title: str) -> str:
        """push 修复分支并建 MR（target=test），返回解析到的 MR URL（失败返回空串）。"""
        work = f"/tmp/repair/{identifier}"
        cmd = [
            "git", "push",
            "-o", "merge_request.create",
            "-o", "merge_request.target=test",
            "-o", f"merge_request.title={title}",
            "origin", branch,
        ]
        try:
            output = self._run(cmd, work, True)
        except Exception:
            logger.error("[Repair] build_mr git push failed: %s", identifier, exc_info=True)
            return ""
        return parse_mr_url(output)
