"""
云之家通知脚本 - 发送文字或图片消息给指定人员
用法:
  python notify.py --text <消息内容> [--complete]
  python notify.py --image <图片路径> [--title <标题>] [--text <附加说明>]
"""

import argparse
import base64
import hashlib
import io
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


def _build_auth(company_id: str, pub_id: str, pub_secret: str) -> dict:
    """
    构建云之家鉴权信息（SHA1 签名）。
    参数按字典序排序后拼接做 SHA1。

    Returns:
        包含 nonce、timestamp、pubtoken 的字典
    """
    timestamp = str(int(time.time() * 1000))
    nonce = timestamp[-4:]
    values = sorted([company_id, pub_id, pub_secret, nonce, timestamp])
    pubtoken = hashlib.sha1("".join(values).encode("utf-8")).hexdigest()
    return {"nonce": nonce, "timestamp": timestamp, "pubtoken": pubtoken}


def _post(payload: dict, url: str, session_cookie: str) -> bool:
    """
    发送 POST 请求到云之家 API。

    Args:
        payload: 请求体
        url: API 地址
        session_cookie: PLAY_SESSION Cookie

    Returns:
        True 表示发送成功
    """
    headers = {"Content-Type": "application/json"}
    if session_cookie:
        headers["Cookie"] = session_cookie
    try:
        import requests

        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        result = resp.json()
        if result.get("code") == 0:
            return True
        else:
            print(f"⚠️  云之家返回错误: {result}")
            return False
    except Exception as e:
        print(f"⚠️  云之家请求异常: {e}")
        return False


def send_text(text: str, complete: bool = False) -> bool:
    """
    发送文字消息到云之家。

    Args:
        text: 消息内容
        complete: True 时发送给 complete_user_ids，否则发给 user_ids

    Returns:
        True 表示发送成功
    """
    config = _load_config()
    yzj = config["yzj"]

    company_id = yzj.get("company_id", "")
    pub_id = yzj.get("pub_id", "")
    pub_secret = yzj.get("pub_secret", "")
    url = yzj.get("pubsend_url", "https://yunzhijia.com/pubacc/pubsendV2")
    session_cookie = yzj.get("session_cookie", "")
    user_ids = (
        (yzj.get("complete_user_ids") or yzj.get("user_ids", []))
        if complete
        else yzj.get("user_ids", [])
    )

    if not all([company_id, pub_id, pub_secret, user_ids]):
        print("❌ 云之家配置不完整，请检查 config.json 和 .env")
        print(
            f"   缺失字段: { {k for k, v in {'company_id': company_id, 'pub_id': pub_id, 'pub_secret': pub_secret, 'user_ids': user_ids}.items() if not v} }"
        )
        return False

    auth = _build_auth(company_id, pub_id, pub_secret)
    payload = {
        "from": {
            "no": company_id,
            "pub": pub_id,
            "nonce": auth["nonce"],
            "time": auth["timestamp"],
            "pubtoken": auth["pubtoken"],
        },
        "to": [{"no": company_id, "user": user_ids}],
        "type": "2",
        "msg": {"text": text},
    }

    success = _post(payload, url, session_cookie)
    if success:
        print(f"✅ 云之家文字消息已发送：{text[:50]}{'...' if len(text) > 50 else ''}")
    return success


def send_image(image_path: str, title: str = None, text: str = "请查看图片") -> bool:
    """
    发送图片消息到云之家。
    图片缩小后居中放在白色背景上，避免云之家卡片展示时裁剪。

    Args:
        image_path: 图片文件路径
        title: 消息标题，None 时使用文件名
        text: 图片附加说明文字

    Returns:
        True 表示发送成功
    """
    config = _load_config()
    yzj = config["yzj"]

    company_id = yzj.get("company_id", "")
    pub_id = yzj.get("pub_id", "")
    pub_secret = yzj.get("pub_secret", "")
    url = yzj.get("pubsend_url", "https://yunzhijia.com/pubacc/pubsendV2")
    session_cookie = yzj.get("session_cookie", "")
    user_ids = yzj.get("user_ids", [])

    if not all([company_id, pub_id, pub_secret, user_ids]):
        print("❌ 云之家配置不完整，请检查 config.json 和 .env")
        return False

    # 图片缩小后居中放在白色背景上，避免云之家卡片裁剪
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        canvas_size = 240
        qr_size = 160
        padding = (canvas_size - qr_size) // 2
        img = img.resize((qr_size, qr_size), Image.LANCZOS)
        canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
        canvas.paste(img, (padding, padding))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        pic_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"❌ 读取图片失败: {e}")
        return False

    if title is None:
        title = Path(image_path).stem

    auth = _build_auth(company_id, pub_id, pub_secret)
    payload = {
        "from": {
            "no": company_id,
            "pub": pub_id,
            "nonce": auth["nonce"],
            "time": auth["timestamp"],
            "pubtoken": auth["pubtoken"],
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
                    "text": text,
                    "url": "",
                    "appid": "",
                    "name": Path(image_path).name,
                    "pic": pic_b64,
                }
            ],
        },
    }

    success = _post(payload, url, session_cookie)
    if success:
        print(f"✅ 云之家图片消息已发送：{title}")
    return success


def main():
    parser = argparse.ArgumentParser(description="发送云之家通知")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="文字消息内容")
    group.add_argument("--image", help="图片文件路径（发送图文消息）")
    parser.add_argument("--title", default=None, help="图片消息标题")
    parser.add_argument(
        "--complete",
        action="store_true",
        help="发送给流程完成通知接收人（complete_user_ids）",
    )
    args = parser.parse_args()

    if args.text:
        success = send_text(args.text, args.complete)
    else:
        success = send_image(args.image, args.title, args.text or "请查看图片")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
