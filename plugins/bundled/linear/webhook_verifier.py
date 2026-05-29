"""Linear Webhook HMAC-SHA256 signature verification."""

import hashlib
import hmac
import time


def verify_linear_webhook(
    raw_body: bytes,
    signature: str,
    secret: str,
    timestamp_ms: int,
    replay_window_ms: int = 60_000,
) -> bool:
    """验证 Linear Webhook 签名和时间戳。

    Args:
        raw_body: 原始请求体字节
        signature: Linear-Signature 请求头值
        secret: Webhook secret
        timestamp_ms: webhookTimestamp 字段值（毫秒）
        replay_window_ms: 防重放时间窗口（默认 60 秒）

    Returns:
        True 表示验证通过
    """
    # 防重放：时间戳必须在窗口内
    if abs(time.time() * 1000 - timestamp_ms) > replay_window_ms:
        return False

    computed = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    try:
        return hmac.compare_digest(computed, signature)
    except (TypeError, ValueError):
        return False
