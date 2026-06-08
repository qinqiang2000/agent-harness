"""
iERP 导出下载等待脚本
轮询检测浏览器下载目录中新文件的出现，返回下载完成的文件路径。

用法:
  python wait_for_download.py [--output-dir /tmp/ierp_export/] [--timeout 600]
"""

import argparse
import json
import os
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


def get_progress_text() -> str | None:
    """
    从页面中读取导出进度文字（如"共XXX张，已处理XXX张"）。

    Returns:
        进度文字字符串，未找到则返回 None
    """
    rc, result = run_browse(
        [
            "js",
            """
        (function() {
            for (const el of document.querySelectorAll('*')) {
                const t = el.textContent || '';
                if (t.includes('共') && t.includes('张') && t.includes('已处理'))
                    return t.trim().substring(0, 100);
            }
            return null;
        })()
        """,
        ]
    )
    if rc == 0 and result and result != "null":
        return result
    return None


def wait_for_download(output_dir: str, timeout: int = 600) -> str | None:
    """
    等待 iERP 导出文件下载完成。
    通过轮询页面进度文字和检测输出目录中的新文件来判断下载状态。

    Args:
        output_dir: 下载文件保存目录
        timeout: 最大等待秒数（默认600秒/10分钟）

    Returns:
        下载完成的文件路径，超时返回 None
    """
    os.makedirs(output_dir, exist_ok=True)

    # 记录等待前目录中已有的文件，用于识别新下载的文件
    existing_files = set(os.listdir(output_dir))

    start_time = time.time()
    last_progress = ""
    check_interval = 5

    print(f"⏳ 等待文件下载到 {output_dir}（最多 {timeout} 秒）...")

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            print(f"❌ 下载超时（{timeout} 秒），未检测到新文件", file=sys.stderr)
            return None

        # 检测新文件（排除 .crdownload 等临时文件）
        current_files = set(os.listdir(output_dir))
        new_files = current_files - existing_files
        completed_files = [
            f
            for f in new_files
            if not f.endswith(".crdownload")
            and not f.startswith(".")
            and (f.endswith(".xlsx") or f.endswith(".xls") or f.endswith(".csv"))
        ]

        if completed_files:
            file_path = os.path.join(output_dir, completed_files[0])
            size = os.path.getsize(file_path)
            print(f"✅ 文件下载完成: {file_path}")
            print(f"   文件大小: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
            return file_path

        # 打印进度（如有）
        progress = get_progress_text()
        if progress and progress != last_progress:
            print(f"   📊 进度: {progress}")
            last_progress = progress
        elif int(elapsed) % 30 == 0 and int(elapsed) > 0:
            print(f"   ⏳ 仍在等待...（已等待 {int(elapsed)} 秒）")

        time.sleep(check_interval)


def main():
    parser = argparse.ArgumentParser(description="等待 iERP 导出文件下载完成")
    parser.add_argument(
        "--output-dir",
        default="/tmp/ierp_export/",
        help="下载文件保存目录（默认 /tmp/ierp_export/）",
    )
    parser.add_argument(
        "--timeout", type=int, default=600, help="最大等待秒数（默认600秒）"
    )
    args = parser.parse_args()

    file_path = wait_for_download(args.output_dir, args.timeout)
    if file_path:
        # 输出文件路径到 stdout，供调用方捕获
        print(f"DOWNLOAD_PATH:{file_path}")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
