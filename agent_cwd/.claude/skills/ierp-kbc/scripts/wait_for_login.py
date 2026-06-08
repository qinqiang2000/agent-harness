"""
iERP 扫码登录等待脚本
通过轮询 browse skill 检测登录状态，每 30 秒自动刷新二维码并重新通知。

用法:
  python wait_for_login.py [--image /tmp/ierp_qrcode.png]  # 等待扫码完成
  python wait_for_login.py --capture-only --image /tmp/ierp_qrcode.png  # 仅截取二维码
"""

import argparse
import json
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
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except FileNotFoundError:
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


def wait_for_qrcode_render(max_wait: int = 15) -> bool:
    """
    等待 iframe 内的二维码图片渲染完成。
    reload 后 iframe 需要重新加载，直接截图会拿到"二维码失效"占位图。

    Args:
        max_wait: 最大等待秒数

    Returns:
        True 表示二维码已渲染，False 表示超时
    """
    for _ in range(max_wait):
        time.sleep(1)
        run_browse(["frame", "iframe#qr-code"])
        rc, result = run_browse(
            [
                "js",
                "const qr=document.querySelector('img.qrcode');qr&&qr.getBoundingClientRect().width>0?'READY':'WAIT'",
            ]
        )
        run_browse(["frame", "main"])
        if rc == 0 and "READY" in result:
            return True
    return False


def capture_qrcode(image_path: str) -> bool:
    """
    截取登录页二维码区域。
    先切换到 iframe 内获取 img.qrcode 的精确坐标，结合 iframe 在页面中的位置
    计算绝对坐标后截图，确保截到有效的二维码而非占位图。

    Args:
        image_path: 截图保存路径

    Returns:
        True 表示截图成功
    """
    clip_arg = None

    # 获取 iframe 在页面中的位置
    rc, iframe_out = run_browse(
        [
            "js",
            "JSON.stringify(document.querySelector('iframe#qr-code')?.getBoundingClientRect() || {})",
        ]
    )
    if rc == 0 and '"width"' in iframe_out:
        try:
            iframe_rect = json.loads(iframe_out)
            iframe_x = int(iframe_rect.get("left", 0))
            iframe_y = int(iframe_rect.get("top", 0))

            # 切换到 iframe 内获取 img.qrcode 精确坐标
            run_browse(["frame", "iframe#qr-code"])
            rc2, qr_out = run_browse(
                [
                    "js",
                    "const qr=document.querySelector('img.qrcode,canvas,#qrcode,.qrcode,[class*=\"qr\"]');"
                    "qr?JSON.stringify({x:qr.getBoundingClientRect().left,y:qr.getBoundingClientRect().top,"
                    "w:qr.getBoundingClientRect().width,h:qr.getBoundingClientRect().height}):'null'",
                ]
            )
            run_browse(["frame", "main"])

            if rc2 == 0 and qr_out and qr_out != "null":
                qr_rect = json.loads(qr_out)
                abs_x = iframe_x + int(qr_rect.get("x", 0))
                abs_y = iframe_y + int(qr_rect.get("y", 0))
                w = int(qr_rect.get("w", 0))
                h = int(qr_rect.get("h", 0))
                if w > 0 and h > 0:
                    clip_arg = f"{abs_x},{abs_y},{w},{h}"
        except Exception:
            pass

    if clip_arg:
        rc, _ = run_browse(["screenshot", image_path, "--clip", clip_arg])
    else:
        print("⚠️  无法动态定位二维码，使用固定截图区域", file=sys.stderr)
        rc, _ = run_browse(["screenshot", image_path, "--clip", "980,125,230,230"])

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
    刷新登录页面，等待二维码渲染后截图并重新发送通知。

    Args:
        image_path: 截图保存路径
        retry_count: 当前刷新次数

    Returns:
        True 表示操作成功
    """
    print(f"\n🔄 刷新二维码（第 {retry_count + 1} 次）...")
    run_browse(["reload"])

    if not wait_for_qrcode_render():
        print("⚠️  等待二维码渲染超时，尝试直接截图", file=sys.stderr)

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
    try:
        config_path = Path(__file__).parent / "config.json"
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        max_retry = config.get("ierp", {}).get("max_qrcode_retry", 5)
        timeout = config.get("ierp", {}).get("scan_timeout", timeout)
    except Exception:
        max_retry = 5

    start_time = time.time()
    last_qrcode_time = start_time
    retry_count = 0

    print(f"⏳ 开始等待扫码，超时 {timeout} 秒，每 {qrcode_interval} 秒刷新二维码...")

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            print(f"\n❌ 等待超时（{timeout} 秒），请重新运行登录流程", file=sys.stderr)
            return False

        if is_logged_in():
            print("\n✅ 检测到登录成功！")
            return True

        dismiss_privacy_dialog()

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
    parser.add_argument(
        "--capture-only", action="store_true", help="仅截取二维码，不等待扫码"
    )
    args = parser.parse_args()

    if args.capture_only:
        # 等待渲染后截图
        if not wait_for_qrcode_render():
            print("⚠️  等待二维码渲染超时，尝试直接截图", file=sys.stderr)
        success = capture_qrcode(args.image)
        sys.exit(0 if success else 1)

    success = wait_for_login(
        timeout=args.timeout,
        qrcode_interval=args.qrcode_interval,
        check_interval=args.check_interval,
        image_path=args.image,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
