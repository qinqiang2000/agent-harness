"""
Cookie 管理脚本 - 保存、加载和验证 iERP 登录 Cookie
用法:
  python cookie_manager.py --check     # 检查本地是否有 Cookie 文件
  python cookie_manager.py --save      # 从 stdin 读取 cookie JSON 并保存
  python cookie_manager.py --clear     # 清除本地 Cookie
  python cookie_manager.py --export    # 导出 cookie JSON 到 stdout（供 browse skill 使用）
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _get_cookie_path() -> Path:
    """从 config.json 获取 Cookie 存储路径，配置文件不存在时使用默认值"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        cookie_file = config.get("ierp", {}).get("cookie_file", "data/cookies.json")
    else:
        cookie_file = "data/cookies.json"
    cookie_path = Path(__file__).parent / cookie_file
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    return cookie_path


def check_cookies() -> bool:
    """
    检查本地是否存在 Cookie 文件。
    实际 Cookie 是否仍有效以页面为准：打开 iERP 首页，
    能进入首页则有效，跳回登录页则失效需重新扫码。

    Returns:
        True 表示本地有 Cookie 文件，False 表示文件不存在需要扫码登录
    """
    cookie_path = _get_cookie_path()
    if not cookie_path.exists():
        print("COOKIE_STATUS: NOT_FOUND")
        return False
    try:
        with open(cookie_path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"COOKIE_STATUS: VALID (saved at {data['save_time']})")
        return True
    except Exception as e:
        print(f"COOKIE_STATUS: ERROR ({e})")
        return False


def save_cookies(cookies_json: str) -> bool:
    """
    保存 Cookie 到本地文件。

    Args:
        cookies_json: JSON 字符串，格式为 browse skill 导出的 cookies 数组

    Returns:
        True 表示保存成功
    """
    cookie_path = _get_cookie_path()
    try:
        cookies = json.loads(cookies_json)
        data = {
            "cookies": cookies,
            "save_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Cookie 已保存: {cookie_path}")
        return True
    except Exception as e:
        print(f"❌ Cookie 保存失败: {e}")
        return False


def clear_cookies() -> bool:
    """清除本地 Cookie 文件"""
    cookie_path = _get_cookie_path()
    if cookie_path.exists():
        cookie_path.unlink()
        print(f"✅ Cookie 已清除: {cookie_path}")
    else:
        print("ℹ️  Cookie 文件不存在，无需清除")
    return True


def export_cookies() -> bool:
    """导出 Cookie JSON 到 stdout，供 browse skill cookie-import 使用"""
    cookie_path = _get_cookie_path()
    if not cookie_path.exists():
        print("❌ Cookie 文件不存在", file=sys.stderr)
        return False
    try:
        with open(cookie_path, encoding="utf-8") as f:
            data = json.load(f)
        # 只输出 cookies 数组（browse skill cookie-import 需要的格式）
        print(json.dumps(data["cookies"], ensure_ascii=False))
        return True
    except Exception as e:
        print(f"❌ Cookie 导出失败: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="iERP Cookie 管理")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check", action="store_true", help="检查本地是否有 Cookie 文件"
    )
    group.add_argument("--save", action="store_true", help="从 stdin 读取 JSON 并保存")
    group.add_argument("--clear", action="store_true", help="清除本地 Cookie")
    group.add_argument(
        "--export", action="store_true", help="导出 cookie JSON 到 stdout"
    )
    args = parser.parse_args()

    if args.check:
        success = check_cookies()
        sys.exit(0 if success else 1)
    elif args.save:
        cookies_json = sys.stdin.read().strip()
        success = save_cookies(cookies_json)
        sys.exit(0 if success else 1)
    elif args.clear:
        success = clear_cookies()
        sys.exit(0 if success else 1)
    elif args.export:
        success = export_cookies()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
