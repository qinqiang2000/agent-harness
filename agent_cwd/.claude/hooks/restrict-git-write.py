#!/usr/bin/env python3
"""PreToolUse hook：git 写操作仅在 /tmp/repair/** 目录放行。

deny 优先级高于 allow，所以 settings.json 的 deny 不再硬封 git 写，
改由本 hook 按命令上下文决定：
  - git 写命令（add/commit/push/checkout -b/branch -d/reset/rebase/stash/tag）
    且命令字符串含 /tmp/repair/ → allow
  - 其余 git 写 → deny
  - 危险操作（merge / push 主干 / merge_when_pipeline_succeeds）→ 永远 deny
  - 非 git 命令 → allow（交给其它规则）
"""
import json
import re
import sys

_REPAIR_PREFIX = "/tmp/repair/"

_WRITE_SUBCMDS = (
    "add",
    "commit",
    "push",
    "checkout -b",
    "branch -d",
    "branch -D",
    "reset",
    "rebase",
    "stash",
    "tag",
)

_DANGER_PATTERNS = (
    r"\bgit\s+merge\b",
    r"git\s+push[^\n]*\borigin\s+main\b",
    r"git\s+push[^\n]*\borigin\s+master\b",
    r"merge_when_pipeline_succeeds",
    r"\bgit\s+push[^\n]*\s(main|master)\b",
    # refspec / 冒号形式推主干：origin main / HEAD:main / fix:master / refs/heads/main
    r"git\s+push[^\n]*[:\s/](main|master)\b",
    # force push：--force / --force-with-lease / -f
    r"git\s+push[^\n]*(--force\b|--force-with-lease|\s-f\b)",
)


def _is_git_write(cmd: str) -> bool:
    if "git " not in cmd and not cmd.strip().startswith("git"):
        return False
    for sub in _WRITE_SUBCMDS:
        if re.search(rf"git\b[^\n]*\b{re.escape(sub)}", cmd):
            return True
    return False


def _is_scoped_to_repair(cmd: str) -> bool:
    """命令是否把 git 操作限定在 /tmp/repair/ 内。

    接受两种形式：
      - 用 `cd /tmp/repair/...` 切到修复目录（命令开头或 &&/;/| 之后）
      - 用 `git -C /tmp/repair/...` 指定工作目录
    仅靠字符串里出现 /tmp/repair/（如 echo/注释）不算。
    """
    if re.search(r"(?:^|[&;|])\s*cd\s+/tmp/repair/", cmd):
        return True
    if re.search(r"git\s+-C\s+/tmp/repair/", cmd):
        return True
    return False


def decide(cmd: str) -> str:
    """返回 'allow' 或 'deny'。"""
    cmd = str(cmd or "")

    for pat in _DANGER_PATTERNS:
        if re.search(pat, cmd):
            return "deny"

    if not _is_git_write(cmd):
        return "allow"

    if _is_scoped_to_repair(cmd):
        return "allow"
    return "deny"


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    if event.get("tool_name", "") != "Bash":
        return

    cmd = event.get("tool_input", {}).get("command", "")
    if decide(cmd) == "deny":
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "git 写操作仅允许在 /tmp/repair/** 修复目录执行，"
                    "且禁止 merge / 推主干 / 自动合并 MR。"
                ),
            }
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
