"""
云之家通知脚本 - 发送二维码图片给指定人员
用法:
  python notify_yzj.py --image <截图路径> [--retry <次数>] [--title <标题>]
"""

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# 加载同目录下的 .env 文件
load_dotenv(Path(__file__).parent / ".env")


def _load_config() -> dict:
    """加载 config.json，敏感字段优先从环境变量读取"""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        print("   请参考 references/config.example.json 创建 scripts/config.json")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    yzj = config.get("yzj", {})
    # 敏感字段优先读环境变量
    if not yzj.get("pub_secret"):
        yzj["pub_secret"] = os.environ.get("YZJ_PUB_SECRET", "")
    if not yzj.get("session_cookie"):
        yzj["session_cookie"] = os.environ.get("YZJ_SESSION_COOKIE", "")
    return config


def _generate_pubtoken(
    company_id: str, pub_id: str, pub_secret: str, nonce: str, timestamp: str
) -> str:
    """生成云之家鉴权 token（SHA1 签名），参数按字典序排序后拼接做 SHA1"""
    values = sorted([company_id, pub_id, pub_secret, nonce, timestamp])
    return hashlib.sha1("".join(values).encode("utf-8")).hexdigest()


def send_qrcode(image_path: str, retry_count: int = 0, title: str = None) -> bool:
    """
    发送二维码图片到云之家指定人员。

    Args:
        image_path: 二维码截图文件路径
        retry_count: 当前是第几次刷新（0 表示首次）
        title: 自定义消息标题，None 时自动生成

    Returns:
        True 表示发送成功，False 表示失败
    """
    config = _load_config()
    yzj = config["yzj"]

    company_id = yzj.get("company_id", "")
    pub_id = yzj.get("pub_id", "")
    pub_secret = yzj.get("pub_secret", "")
    user_ids = yzj.get("user_ids", [])
    url = yzj.get("pubsend_url", "https://yunzhijia.com/pubacc/pubsendV2")
    session_cookie = yzj.get("session_cookie", "")

    if not all([company_id, pub_id, pub_secret, user_ids]):
        print("❌ 云之家配置不完整，请检查 config.json 和 .env")
        return False

    # 读取并编码图片
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        pic_b64 = base64.b64encode(image_bytes).decode("utf-8")
    except Exception as e:
        print(f"❌ 读取截图失败: {e}")
        return False

    # 生成鉴权信息
    timestamp = str(int(time.time() * 1000))
    nonce = timestamp[-4:]
    pubtoken = _generate_pubtoken(company_id, pub_id, pub_secret, nonce, timestamp)

    # 构建消息标题
    if title is None:
        if retry_count == 0:
            title = "🔐 iERP 需要登录"
        else:
            title = f"🔐 iERP 需要重新登录（第{retry_count + 1}次生成二维码）"

    payload = {
        "from": {
            "no": company_id,
            "pub": pub_id,
            "nonce": nonce,
            "time": timestamp,
            "pubtoken": pubtoken,
        },
        "to": [{"no": company_id, "user": user_ids}],
        "type": "6",
        "msg": {
            "model": 2,
            "todo": 0,
            "sourceid": "",
            "list": [
                {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "title": title,
                    "text": "请用手机扫描二维码完成登录",
                    "url": "",
                    "appid": "",
                    "name": "qrcode.png",
                    "pic": pic_b64,
                }
            ],
        },
    }

    headers = {"Content-Type": "application/json"}
    if session_cookie:
        headers["Cookie"] = session_cookie

    try:
        import requests

        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        result = resp.json()
        if result.get("code") == 0:
            print(f"✅ 云之家通知已发送：{title}")
            return True
        else:
            print(f"⚠️  云之家发送失败: {result}")
            return False
    except Exception as e:
        print(f"⚠️  云之家发送异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="发送二维码到云之家")
    parser.add_argument("--image", required=True, help="二维码截图路径")
    parser.add_argument("--retry", type=int, default=0, help="刷新次数（0表示首次）")
    parser.add_argument("--title", default=None, help="自定义消息标题")
    args = parser.parse_args()

    success = send_qrcode(args.image, args.retry, args.title)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
