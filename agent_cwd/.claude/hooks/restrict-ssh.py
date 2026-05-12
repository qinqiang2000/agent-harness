#!/usr/bin/env python3
"""
PreToolUse hook: 拦截所有包含 ssh 的 Bash 命令，只允许执行白名单内的远程命令。
白名单从同目录下的 ssh-allowlist.conf 读取（每行一个正则）。

工作原理:
  Claude 执行 Bash 工具前，本 hook 检查命令内容。
  如果是 SSH 命令，提取远程执行的部分，逐行匹配白名单。
  不在白名单内的命令直接 deny，SSH 命令根本不会发出去。
"""
import json
import re
import sys
from pathlib import Path

# 白名单文件路径（和本脚本同目录）
ALLOWLIST_FILE = Path(__file__).parent / "ssh-allowlist.conf"

# 加载白名单正则
def load_allowlist():
    if not ALLOWLIST_FILE.exists():
        return []
    patterns = []
    for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def extract_remote_commands(bash_command: str) -> list[str]:
    """从 SSH 命令中提取远程执行的命令行。"""
    lines = []

    # heredoc 模式: ssh ... bash -s << 'EOF' ... EOF
    heredoc_match = re.search(
        r"<<\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\1",
        bash_command,
        re.DOTALL
    )
    if heredoc_match:
        remote_block = heredoc_match.group(2)
        lines = remote_block.splitlines()
    else:
        # 直接命令模式: ssh user@host "command"
        # 提取最后的引号内容或 user@host 之后的部分
        quoted = re.findall(r'"([^"]+)"', bash_command)
        if quoted:
            lines = quoted[-1].splitlines()
        else:
            # ssh user@host command args
            parts = bash_command.split()
            host_idx = None
            for i, p in enumerate(parts):
                if "@" in p and not p.startswith("-"):
                    host_idx = i
                    break
            if host_idx is not None and host_idx + 1 < len(parts):
                lines = [" ".join(parts[host_idx + 1:])]

    return lines


def is_line_allowed(line: str, patterns: list[str]) -> bool:
    """检查单行命令是否匹配白名单。"""
    stripped = line.strip()

    # 跳过空行、注释、echo、变量赋值、流程控制
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith("echo "):
        return True
    if re.match(r'^[A-Z_][A-Z_0-9]*=', stripped):
        return True
    if stripped in ("then", "fi", "else", "done", "do", "esac"):
        return True
    if re.match(r'^(if |elif |for |while |case )', stripped):
        return True

    # 匹配白名单
    for pattern in patterns:
        if re.search(pattern, stripped):
            return True
    return False


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = event.get("tool_name", "")
    if tool_name != "Bash":
        return

    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    # 只拦截 SSH 命令
    if "ssh " not in command and "ssh\t" not in command:
        return

    patterns = load_allowlist()
    if not patterns:
        # 没有白名单文件，放行（降级为不拦截）
        return

    remote_lines = extract_remote_commands(command)
    if not remote_lines:
        # 无法解析远程命令，保守拒绝
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "无法解析 SSH 远程命令内容，拒绝执行。"
            }
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
        return

    # 逐行检查
    for line in remote_lines:
        if not is_line_allowed(line, patterns):
            result = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"SSH 命令被拒绝，不在白名单内: {line.strip()}"
                }
            }
            sys.stdout.write(json.dumps(result, ensure_ascii=False))
            return

    # 全部通过，不输出任何内容（放行）


if __name__ == "__main__":
    main()
