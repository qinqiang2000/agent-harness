"""消息发送器 - 发送云之家消息（文本和图片卡片）."""

import logging
import re
from typing import List

import aiohttp

from plugins.bundled.yunzhijia.card_builder import YunzhijiaCardBuilder

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """处理云之家不支持的内容格式。"""
    # java 全限定类名（如 java.lang.ClassCastException）→ 只保留类名
    text = re.sub(r'java(?:\.[a-z][a-z0-9_]*)+\.([A-Z][A-Za-z0-9_]*)', r'\1', text)
    return text


class YunzhijiaMessageSender:
    """云之家消息发送器"""

    def __init__(self, notify_url_template: str):
        self.notify_url_template = notify_url_template

    async def send_text(self, token: str, openid: str, content: str):
        """发送文本消息"""
        url = self.notify_url_template.format(token)
        data = {
            "content": _strip_markdown(content),
            "notifyParams": [{"type": "openIds", "values": [openid]}]
        }

        success = await self._send_request(url, data)
        if success:
            logger.info(f"[MessageSender] Text message sent to {openid}")
        else:
            logger.error(f"[MessageSender] Failed to send text message to {openid}")

    async def send_with_images(
        self,
        token: str,
        openid: str,
        content: str,
        service_base_url: str,
        card_builder: YunzhijiaCardBuilder
    ):
        """发送带图片的消息（文本 + 卡片）"""
        from api.utils.image_utils import extract_images_from_content

        cleaned_content, img_urls = extract_images_from_content(content, service_base_url)

        if img_urls:
            cleaned_content += "\n\n（具体图片请查看下方消息）"

        await self.send_text(token, openid, cleaned_content)

        if img_urls:
            await self._send_card_notices(token, openid, img_urls, card_builder)

    async def _send_card_notices(
        self,
        token: str,
        openid: str,
        img_urls: List[str],
        card_builder: YunzhijiaCardBuilder
    ):
        """发送图片卡片消息列表"""
        payloads = card_builder.build_card_payloads(img_urls, openid)
        url = self.notify_url_template.format(token)

        for i, payload in enumerate(payloads):
            success = await self._send_request(url, payload)
            if success:
                logger.info(f"[MessageSender] Card {i+1}/{len(payloads)} sent to {openid}")
            else:
                logger.error(f"[MessageSender] Failed to send card {i+1}/{len(payloads)}")

    async def _send_request(self, url: str, data: dict) -> bool:
        """发送 HTTP 请求到云之家"""
        logger.debug(f"[MessageSender] POST {url} payload={data}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(
                            f"[MessageSender] HTTP {response.status}: {response_text} "
                            f"| url={url} payload={data}"
                        )
                        return False
        except Exception as e:
            logger.error(f"[MessageSender] Request error: {e}", exc_info=True)
            return False
