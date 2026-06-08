"""
云之家通知脚本（委托版）
实际逻辑由 yunzhijia-notify skill 的 notify.py 提供，此文件仅做参数转换后委托调用。

用法（与原版相同）:
  python notify_yzj.py --image <截图路径> [--retry <次数>] [--title <标题>]
"""

import argparse
import subprocess
import sys
from pathlib import Path


def _notify_script() -> Path:
    """定位 yunzhijia-notify skill 的 notify.py 路径"""
    # 相对路径：ierp-login/scripts -> skills/ -> yunzhijia-notify/scripts/notify.py
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


def send_qrcode(image_path: str, retry_count: int = 0, title: str = None) -> bool:
    """
    发送二维码图片到云之家（委托给 yunzhijia-notify）。

    Args:
        image_path: 二维码截图文件路径
        retry_count: 当前是第几次刷新（0 表示首次）
        title: 自定义消息标题，None 时自动生成

    Returns:
        True 表示发送成功，False 表示失败
    """
    try:
        notify_script = _notify_script()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return False

    # 构建标题
    if title is None:
        if retry_count == 0:
            title = "🔐 iERP 需要登录"
        else:
            title = f"🔐 iERP 需要重新登录（第{retry_count + 1}次生成二维码）"

    # 使用 yunzhijia-notify skill 的 config.json（从 ierp-login/scripts 向上找）
    # notify.py 会从自己的同级目录找 config.json
    scripts_dir = Path(__file__).parent
    venv_python = scripts_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else "python3"

    result = subprocess.run(
        [python_cmd, str(notify_script), "--image", image_path, "--title", title],
        capture_output=True,
        text=True,
        # 在 yunzhijia-notify/scripts/ 目录下运行，使其找到自己的 config.json
        cwd=str(notify_script.parent),
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="发送二维码到云之家（委托 yunzhijia-notify）"
    )
    parser.add_argument("--image", required=True, help="二维码截图路径")
    parser.add_argument("--retry", type=int, default=0, help="刷新次数（0表示首次）")
    parser.add_argument("--title", default=None, help="自定义消息标题")
    args = parser.parse_args()

    success = send_qrcode(args.image, args.retry, args.title)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
