"""企业微信群机器人 Channel Plugin 入口."""

import logging
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.wecom.crypto import WecomCrypto
from plugins.bundled.wecom_group.handler import WecomGroupHandler
from plugins.bundled.wecom_group.message_sender import WecomGroupMessageSender
from plugins.bundled.wecom_group.models import WecomGroupMessage

logger = logging.getLogger(__name__)


class WecomGroupChannelPlugin(ChannelPlugin):
    """企业微信群机器人 Channel Plugin."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config

        corp_id = self.config.get("corp_id") or os.getenv("WECOM_GROUP_CORP_ID", "")
        token = self.config.get("token") or os.getenv("WECOM_GROUP_TOKEN", "")
        encoding_aes_key = self.config.get("encoding_aes_key") or os.getenv("WECOM_GROUP_ENCODING_AES_KEY", "")

        self.crypto = WecomCrypto(
            token=token,
            encoding_aes_key=encoding_aes_key,
            corp_id=corp_id,
        )
        self.message_sender = WecomGroupMessageSender()
        self.handler = WecomGroupHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            message_sender=self.message_sender,
            config=self.config,
        )

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="wecom_group",
            name="企业微信群机器人",
            webhook_path="/wecom_group/callback",
            description="企业微信群机器人消息接收与回复集成",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=True,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=True,
            transfer_human=False,
        )

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["wecom_group"])
        crypto = self.crypto
        handler = self.handler

        @router.get("/wecom_group/callback")
        async def wecom_group_verify(
            msg_signature: str = Query(...),
            timestamp: str = Query(...),
            nonce: str = Query(...),
            echostr: str = Query(...),
        ):
            """企业微信服务器验证接口."""
            if not crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
                logger.warning("[WeComGroup] Signature verification failed on GET")
                return PlainTextResponse("invalid signature", status_code=403)

            try:
                plaintext, _ = crypto._decrypt(echostr)
                logger.info("[WeComGroup] Server verification passed")
                return PlainTextResponse(plaintext)
            except Exception as e:
                logger.error(f"[WeComGroup] Failed to decrypt echostr: {e}")
                return PlainTextResponse("decrypt error", status_code=500)

        @router.post("/wecom_group/callback")
        async def wecom_group_callback(
            request: Request,
            background_tasks: BackgroundTasks,
            msg_signature: str = Query(...),
            timestamp: str = Query(...),
            nonce: str = Query(...),
            skill: str = Query(None, description="指定使用的 skill"),
        ):
            """企业微信群机器人消息接收接口."""
            body = await request.body()
            xml_body = body.decode("utf-8")

            logger.info(
                f"[WeComGroup] POST callback: msg_signature={msg_signature}, "
                f"timestamp={timestamp}, nonce={nonce}, body={xml_body[:200]}"
            )

            try:
                root = ET.fromstring(xml_body)
                encrypt = root.findtext("Encrypt") or ""
            except Exception as e:
                logger.error(f"[WeComGroup] Failed to parse XML: {e}")
                return PlainTextResponse("parse error", status_code=400)

            if not crypto.verify_signature(msg_signature, timestamp, nonce, encrypt):
                logger.warning(
                    f"[WeComGroup] Signature verification failed: "
                    f"token={crypto.token}, timestamp={timestamp}, nonce={nonce}"
                )
                return PlainTextResponse("invalid signature", status_code=403)

            try:
                plaintext, _ = crypto.decrypt_message(xml_body)
            except Exception as e:
                logger.error(f"[WeComGroup] Failed to decrypt message: {e}")
                return PlainTextResponse("decrypt error", status_code=500)

            try:
                msg = WecomGroupMessage.from_xml(plaintext)
            except Exception as e:
                logger.error(f"[WeComGroup] Failed to parse message XML: {e}")
                return PlainTextResponse("parse error", status_code=500)

            logger.info(
                f"[WeComGroup] Received: user={msg.from_user_name}, chat={msg.chat_id}, "
                f"type={msg.msg_type}, content={str(msg.content or '')[:50]!r}"
            )

            background_tasks.add_task(handler.process_message, msg, skill)

            return PlainTextResponse("")

        @router.get("/wecom_group/stats")
        async def wecom_group_stats():
            """获取会话统计信息（调试用）."""
            return handler.get_session_stats()

        return router

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await self.message_sender.send_text(text)

    async def on_start(self) -> None:
        logger.info("[WeComGroup] Plugin started")

    async def on_stop(self) -> None:
        logger.info("[WeComGroup] Plugin stopped")


def register(api: PluginAPI) -> WecomGroupChannelPlugin:
    """Plugin 入口点 - 由 PluginLifecycle.register() 调用."""
    plugin = WecomGroupChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[WeComGroup] Plugin registered")
    return plugin
