"""
云之家通知脚本（委托版）
实际逻辑由 yunzhijia-notify skill 的 notify.py 提供，此文件仅做参数转换后委托调用。

用法:
  python notify_yzj.py --image <截图路径> [--retry <次数>] [--title <标题>]
  python notify_yzj.py --text <消息内容> [--complete]
"""

import argparse
import subprocess
import sys
from pathlib import Path


def _notify_script() -> Path:
    """定位 yunzhijia-notify skill 的 notify.py 路径"""
    # 相对路径：ierp-kbc/scripts -> skills/ -> yunzhijia-notify/scripts/notify.py
    candidate = (
        Path(__file__).parent.parent.parent
        / "yunzhijia-notify"
        / "scripts"
        / "notify.py"
    )
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"找不到 yunzhijia-notify/scripts/notify.py，请确认 yunzhijia-notify skill 已安装。\n"
        f"查找路径: {candidate}"
    )


def _run(args: list[str]) -> bool:
    """
    在 yunzhijia-notify/scripts/ 目录下调用 notify.py。
    切换到该目录确保 notify.py 能找到自己的 config.json。

    Args:
        args: 传递给 notify.py 的参数列表

    Returns:
        True 表示执行成功
    """
    try:
        notify_script = _notify_script()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return False

    scripts_dir = Path(__file__).parent
    venv_python = scripts_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else "python3"

    result = subprocess.run(
        [python_cmd, str(notify_script)] + args,
        capture_output=True,
        text=True,
        cwd=str(notify_script.parent),
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode == 0


def send_qrcode(image_path: str, retry_count: int = 0, title: str = None) -> bool:
    """
    发送二维码图片到云之家。

    Args:
        image_path: 二维码截图文件路径
        retry_count: 当前是第几次刷新（0 表示首次）
        title: 自定义消息标题，None 时自动生成

    Returns:
        True 表示发送成功
    """
    if title is None:
        title = (
            "🔐 iERP 需要登录"
            if retry_count == 0
            else f"🔐 iERP 需要重新登录（第{retry_count + 1}次生成二维码）"
        )
    return _run(["--image", image_path, "--title", title])


def send_text(text: str, complete: bool = False) -> bool:
    """
    发送文字消息到云之家。

    Args:
        text: 消息内容
        complete: True 时发送给 complete_user_ids

    Returns:
        True 表示发送成功
    """
    args = ["--text", text]
    if complete:
        args.append("--complete")
    return _run(args)


def main():
    parser = argparse.ArgumentParser(
        description="发送云之家通知（委托 yunzhijia-notify）"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", help="二维码截图路径")
    group.add_argument("--text", help="文字消息内容")
    parser.add_argument("--retry", type=int, default=0, help="刷新次数（0表示首次）")
    parser.add_argument("--title", default=None, help="自定义消息标题")
    parser.add_argument(
        "--complete", action="store_true", help="发送给流程完成通知接收人"
    )
    args = parser.parse_args()

    if args.image:
        success = send_qrcode(args.image, args.retry, args.title)
    else:
        success = send_text(args.text, args.complete)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
