"""企业微信消息发送器 - 通过 wecom-sdk 调用主动消息接口."""

import logging

from wecom_sdk import Wecom
from wecom_sdk.schemas.message import MessageParams

logger = logging.getLogger(__name__)


class WecomMessageSender:
    """封装 wecom-sdk 的文本消息发送."""

    def __init__(self, corp_id: str, corp_secret: str, agent_id: int):
        self.agent_id = agent_id
        self._client = Wecom(corpid=corp_id, corpsecret=corp_secret)

    async def send_text(self, user_id: str, content: str) -> bool:
        """向指定用户发送文本消息."""
        params = MessageParams(
            touser=user_id,
            msgtype="text",
            agentid=self.agent_id,
            text={"content": content},
        )
        try:
            await self._client.send_message(params)
            logger.info(f"[WeCom] Text sent to {user_id}")
            return True
        except Exception as e:
            logger.error(f"[WeCom] Failed to send text to {user_id}: {e}")
            return False
