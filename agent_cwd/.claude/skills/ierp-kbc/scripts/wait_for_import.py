"""
cosmic-pro 导入等待脚本
轮询页面检测导入完成状态（成功提示或 loading 消失）。

用法:
  python wait_for_import.py [--timeout 120]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run_browse(args: list[str]) -> tuple[int, str]:
    """
    调用 browse CLI 执行一条命令。

    Args:
        args: browse 命令参数列表

    Returns:
        (returncode, stdout) 元组
    """
    browse_bin = Path.home() / ".claude/skills/gstack/browse/dist/browse"
    cmd = str(browse_bin) if browse_bin.exists() else "agent-browser"
    try:
        result = subprocess.run(
            [cmd] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout.strip()
    except Exception as e:
        return 1, str(e)


def check_import_complete() -> tuple[bool, str | None]:
    """
    检测页面是否出现导入完成的提示文字。

    Returns:
        (是否完成, 提示文字或 None)
    """
    rc, result = run_browse(
        [
            "js",
            """
        (function() {
            const keywords = ['导入成功', '上传成功', '处理完成', '导入完成', '成功导入'];
            for (const el of document.querySelectorAll('*')) {
                if (!el.offsetParent) continue;
                const t = (el.textContent || '').trim();
                for (const kw of keywords) {
                    if (t.includes(kw) && t.length < 100) return t;
                }
            }
            return null;
        })()
        """,
        ]
    )
    if rc == 0 and result and result != "null":
        return True, result
    return False, None


def check_loading_gone() -> bool:
    """
    检测页面 loading/进度条是否已消失（表示导入处理结束）。

    Returns:
        True 表示 loading 已消失
    """
    rc, result = run_browse(
        [
            "js",
            """
        (function() {
            const loading = document.querySelector(
                '.loading, .progress, [class*="loading"], [class*="progress"], [class*="spin"]'
            );
            if (!loading) return 'gone';
            return loading.offsetParent !== null ? 'visible' : 'gone';
        })()
        """,
        ]
    )
    return rc == 0 and result == "gone"


def wait_for_import(timeout: int = 120) -> bool:
    """
    等待 cosmic-pro 导入完成。
    优先检测成功提示文字，其次检测 loading 消失。

    Args:
        timeout: 最大等待秒数

    Returns:
        True 表示检测到导入完成，False 表示超时
    """
    start_time = time.time()
    check_interval = 5

    print(f"⏳ 等待导入处理完成（最多 {timeout} 秒）...")

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            print(f"⚠️  等待超时（{timeout} 秒），请手动确认导入状态", file=sys.stderr)
            return False

        # 优先检测成功提示
        done, msg = check_import_complete()
        if done:
            print(f"✅ 导入完成：{msg}")
            return True

        # 其次检测 loading 消失
        if elapsed > 10 and check_loading_gone():
            print(f"✅ 导入处理完成（loading 已消失，等待了 {int(elapsed)} 秒）")
            return True

        if int(elapsed) % 15 == 0 and int(elapsed) > 0:
            print(f"   ⏳ 仍在等待...（已等待 {int(elapsed)} 秒）")

        time.sleep(check_interval)


def main():
    parser = argparse.ArgumentParser(description="等待 cosmic-pro 导入完成")
    parser.add_argument(
        "--timeout", type=int, default=120, help="最大等待秒数（默认120）"
    )
    args = parser.parse_args()

    success = wait_for_import(args.timeout)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
