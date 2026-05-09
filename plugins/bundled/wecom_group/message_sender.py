"""企业微信群机器人消息发送器."""

import logging

import aiohttp

logger = logging.getLogger(__name__)


class WecomGroupMessageSender:
    """支持两种回复方式：
    - response_url：智能机器人模式，每条消息携带一次性回复 URL
    - webhook_url：普通群机器人模式，固定 Webhook URL
    """

    async def send_text(self, content: str, response_url: str = "", webhook_url: str = "") -> bool:
        """发送文本消息."""
        if response_url:
            return await self._post_response(response_url, content)
        if webhook_url:
            return await self._post_webhook(webhook_url, content)
        logger.error("[WeComGroup] No response_url or webhook_url available")
        return False

    async def _post_response(self, response_url: str, content: str) -> bool:
        """通过智能机器人 response_url 回复."""
        data = {
            "msgtype": "text",
            "text": {"content": content},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(response_url, json=data) as resp:
                    result = await resp.json()
                    if result.get("errcode") == 0:
                        logger.info("[WeComGroup] Reply sent via response_url")
                        return True
                    else:
                        logger.error(f"[WeComGroup] response_url send failed: {result}")
                        return False
        except Exception as e:
            logger.error(f"[WeComGroup] response_url request error: {e}", exc_info=True)
            return False

    async def _post_webhook(self, webhook_url: str, content: str, mentioned_list: list = None) -> bool:
        """通过群机器人 Webhook 发消息到群."""
        data = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list or [],
            },
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data) as resp:
                    result = await resp.json()
                    if result.get("errcode") == 0:
                        logger.info("[WeComGroup] Message sent via webhook_url")
                        return True
                    else:
                        logger.error(f"[WeComGroup] webhook send failed: {result}")
                        return False
        except Exception as e:
            logger.error(f"[WeComGroup] webhook request error: {e}", exc_info=True)
            return False
