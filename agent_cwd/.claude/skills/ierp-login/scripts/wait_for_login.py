"""
iERP 扫码登录等待脚本
通过轮询 browse skill 检测登录状态，每 30 秒自动刷新二维码并重新通知。

用法:
  python wait_for_login.py [--timeout 180] [--qrcode-interval 30] [--check-interval 3]
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
        args: browse 命令参数列表，如 ["url"] 或 ["screenshot", "/tmp/qr.png"]

    Returns:
        (returncode, stdout) 元组
    """
    try:
        result = subprocess.run(
            ["agent-browser"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except FileNotFoundError:
        # 兼容 browse 二进制名称差异
        try:
            result = subprocess.run(
                ["browse"] + args,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout.strip()
        except Exception as e:
            return 1, str(e)
    except Exception as e:
        return 1, str(e)


def send_qrcode(image_path: str, retry_count: int) -> bool:
    """
    调用 notify_yzj.py 发送二维码通知。

    Args:
        image_path: 二维码截图路径
        retry_count: 当前刷新次数

    Returns:
        True 表示发送成功
    """
    scripts_dir = Path(__file__).parent
    venv_python = scripts_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else "python3"

    result = subprocess.run(
        [
            python_cmd,
            str(scripts_dir / "notify_yzj.py"),
            "--image",
            image_path,
            "--retry",
            str(retry_count),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode == 0


def capture_qrcode(image_path: str) -> bool:
    """
    截取登录页二维码区域。
    优先通过 iframe#qr-code 元素边界框定位，定位失败则降级使用固定区域。

    Args:
        image_path: 截图保存路径

    Returns:
        True 表示截图成功
    """
    # 尝试通过 JS 获取 iframe 边界框，动态定位二维码区域
    rc, output = run_browse(
        [
            "js",
            "JSON.stringify(document.querySelector('iframe#qr-code')?.getBoundingClientRect() || {})",
        ]
    )
    clip_arg = None
    if rc == 0 and output and '"width"' in output:
        try:
            import json

            rect = json.loads(output)
            x = int(rect.get("left", 0))
            y = int(rect.get("top", 0))
            w = int(rect.get("width", 0))
            h = int(rect.get("height", 0))
            if w > 0 and h > 0:
                # 加 10px padding
                clip_arg = f"{max(0, x-10)},{max(0, y-10)},{w+20},{h+20}"
        except Exception:
            pass

    if clip_arg:
        rc, _ = run_browse(["screenshot", image_path, "--clip", clip_arg])
    else:
        # 降级：固定裁剪区域（右侧二维码区域）
        print("⚠️  无法动态定位二维码 iframe，使用固定截图区域", file=sys.stderr)
        rc, _ = run_browse(["screenshot", image_path, "--clip", "950,100,280,380"])

    return rc == 0


def is_logged_in() -> bool:
    """
    检测当前页面 URL 是否已跳转到 iERP 首页（非 passport 域）。

    Returns:
        True 表示已登录成功
    """
    rc, url = run_browse(["url"])
    if rc != 0:
        return False
    return "ierp.kingdee.com" in url and "passport" not in url


def dismiss_privacy_dialog() -> None:
    """检测并点击隐私政策弹窗中的同意按钮（如存在）。"""
    rc, snapshot = run_browse(["snapshot", "-i"])
    if rc != 0:
        return
    keywords = ["接受并继续", "同意", "继续登录", "我已阅读"]
    for kw in keywords:
        if kw in snapshot:
            run_browse(["click", kw])
            print(f"  → 已点击弹窗按钮：{kw}")
            time.sleep(1)
            break


def reload_and_capture(image_path: str, retry_count: int) -> bool:
    """
    刷新登录页面并重新截取二维码、发送通知。

    Args:
        image_path: 截图保存路径
        retry_count: 当前刷新次数

    Returns:
        True 表示操作成功
    """
    print(f"\n🔄 刷新二维码（第 {retry_count + 1} 次）...")
    run_browse(["reload"])
    time.sleep(3)  # 等待 iframe 加载

    if not capture_qrcode(image_path):
        print("❌ 截图失败，跳过本次通知", file=sys.stderr)
        return False

    send_qrcode(image_path, retry_count)
    return True


def wait_for_login(
    timeout: int = 180,
    qrcode_interval: int = 30,
    check_interval: int = 3,
    image_path: str = "/tmp/ierp_qrcode.png",
) -> bool:
    """
    轮询等待 iERP 扫码登录完成。

    Args:
        timeout: 最大等待秒数，超时后报错退出
        qrcode_interval: 二维码自动刷新间隔（秒）
        check_interval: 登录状态检测间隔（秒）
        image_path: 二维码截图路径

    Returns:
        True 表示登录成功，False 表示超时或超过刷新上限
    """
    # 读取 config 中的 max_qrcode_retry
    try:
        import json

        config_path = Path(__file__).parent / "config.json"
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        max_retry = config.get("login", {}).get("max_qrcode_retry", 5)
        timeout = config.get("login", {}).get("scan_timeout", timeout)
    except Exception:
        max_retry = 5

    start_time = time.time()
    last_qrcode_time = start_time
    retry_count = 0

    print(f"⏳ 开始等待扫码，超时 {timeout} 秒，每 {qrcode_interval} 秒刷新二维码...")

    while True:
        elapsed = time.time() - start_time

        # 超时检测
        if elapsed > timeout:
            print(f"\n❌ 等待超时（{timeout} 秒），请重新运行登录流程", file=sys.stderr)
            return False

        # 检测是否已登录
        if is_logged_in():
            print("\n✅ 检测到登录成功！")
            return True

        # 检测隐私弹窗
        dismiss_privacy_dialog()

        # 判断是否需要刷新二维码
        since_last_qrcode = time.time() - last_qrcode_time
        if since_last_qrcode >= qrcode_interval:
            retry_count += 1
            if retry_count > max_retry:
                print(
                    f"\n❌ 二维码刷新次数已超过上限（{max_retry} 次），请检查网络或重新登录",
                    file=sys.stderr,
                )
                return False
            reload_and_capture(image_path, retry_count)
            last_qrcode_time = time.time()

        time.sleep(check_interval)


def main():
    parser = argparse.ArgumentParser(description="等待 iERP 扫码登录完成")
    parser.add_argument(
        "--timeout", type=int, default=180, help="最大等待秒数（默认180）"
    )
    parser.add_argument(
        "--qrcode-interval", type=int, default=30, help="二维码刷新间隔秒数（默认30）"
    )
    parser.add_argument(
        "--check-interval", type=int, default=3, help="登录状态检测间隔秒数（默认3）"
    )
    parser.add_argument(
        "--image", default="/tmp/ierp_qrcode.png", help="二维码截图路径"
    )
    args = parser.parse_args()

    success = wait_for_login(
        timeout=args.timeout,
        qrcode_interval=args.qrcode_interval,
        check_interval=args.check_interval,
        image_path=args.image,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
