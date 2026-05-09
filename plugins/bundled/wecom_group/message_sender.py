"""企业微信群机器人消息发送器 - 通过 Webhook 发送消息到群."""

import logging

import aiohttp

logger = logging.getLogger(__name__)


class WecomGroupMessageSender:
    """通过群机器人 Webhook 发送消息到群.

    webhook_url 优先使用消息里携带的动态地址，fallback 到初始化时配置的默认地址。
    """

    def __init__(self, webhook_url: str = ""):
        self.default_webhook_url = webhook_url

    async def send_text(self, content: str, webhook_url: str = "", mentioned_list: list = None) -> bool:
        """发送文本消息到群，可选 @ 指定成员."""
        data = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list or [],
            },
        }
        return await self._post(data, webhook_url)

    async def send_markdown(self, content: str, webhook_url: str = "") -> bool:
        """发送 Markdown 消息到群."""
        data = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        return await self._post(data, webhook_url)

    async def _post(self, data: dict, webhook_url: str = "") -> bool:
        url = webhook_url or self.default_webhook_url
        if not url:
            logger.error("[WeComGroup] No webhook_url available to send message")
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as resp:
                    result = await resp.json()
                    if result.get("errcode") == 0:
                        logger.info("[WeComGroup] Message sent successfully")
                        return True
                    else:
                        logger.error(f"[WeComGroup] Send failed: {result}")
                        return False
        except Exception as e:
            logger.error(f"[WeComGroup] Request error: {e}", exc_info=True)
            return False
