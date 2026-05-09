"""企业微信 Channel Plugin 入口."""

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.wecom.crypto import WecomCrypto
from plugins.bundled.wecom.handler import WecomHandler
from plugins.bundled.wecom.message_sender import WecomMessageSender
from plugins.bundled.wecom.models import WecomMessage

logger = logging.getLogger(__name__)


class WecomChannelPlugin(ChannelPlugin):
    """企业微信自建应用 Channel Plugin."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config

        corp_id = self.config.get("corp_id") or os.getenv("WECOM_CORP_ID", "")
        corp_secret = self.config.get("corp_secret") or os.getenv("WECOM_CORP_SECRET", "")
        agent_id = int(self.config.get("agent_id") or os.getenv("WECOM_AGENT_ID", "0"))
        token = self.config.get("token") or os.getenv("WECOM_TOKEN", "")
        encoding_aes_key = self.config.get("encoding_aes_key") or os.getenv("WECOM_ENCODING_AES_KEY", "")

        self.crypto = WecomCrypto(
            token=token,
            encoding_aes_key=encoding_aes_key,
            corp_id=corp_id,
        )
        self.message_sender = WecomMessageSender(
            corp_id=corp_id,
            corp_secret=corp_secret,
            agent_id=agent_id,
        )
        self.handler = WecomHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            message_sender=self.message_sender,
            config=self.config,
        )

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="wecom",
            name="企业微信",
            webhook_path="/wecom/callback",
            description="企业微信自建应用消息接收与回复集成",
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
        router = APIRouter(tags=["wecom"])
        crypto = self.crypto
        handler = self.handler

        @router.get("/wecom/callback")
        async def wecom_verify(
            msg_signature: str = Query(...),
            timestamp: str = Query(...),
            nonce: str = Query(...),
            echostr: str = Query(...),
        ):
            """企业微信服务器验证接口."""
            if not crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
                logger.warning("[WeCom] Signature verification failed on GET")
                return PlainTextResponse("invalid signature", status_code=403)

            # echostr 本身是加密的，需要解密后返回明文
            try:
                plaintext, _ = crypto._decrypt(echostr)
                logger.info("[WeCom] Server verification passed")
                return PlainTextResponse(plaintext)
            except Exception as e:
                logger.error(f"[WeCom] Failed to decrypt echostr: {e}")
                return PlainTextResponse("decrypt error", status_code=500)

        @router.post("/wecom/callback")
        async def wecom_callback(
            request: Request,
            background_tasks: BackgroundTasks,
            msg_signature: str = Query(...),
            timestamp: str = Query(...),
            nonce: str = Query(...),
        ):
            """企业微信消息接收接口."""
            body = await request.body()
            xml_body = body.decode("utf-8")

            logger.info(
                f"[WeCom] POST callback: msg_signature={msg_signature}, "
                f"timestamp={timestamp}, nonce={nonce}, body={xml_body[:200]}"
            )

            # POST 签名是对 Encrypt 字段内容做的，需要先从 XML 里取出来
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(xml_body)
                encrypt = root.findtext("Encrypt") or ""
            except Exception as e:
                logger.error(f"[WeCom] Failed to parse XML: {e}")
                return PlainTextResponse("parse error", status_code=400)

            logger.info(f"[WeCom] Encrypt field (first 50): {encrypt[:50]}")

            if not crypto.verify_signature(msg_signature, timestamp, nonce, encrypt):
                logger.warning(
                    f"[WeCom] Signature verification failed on POST: "
                    f"token={crypto.token}, timestamp={timestamp}, nonce={nonce}, "
                    f"encrypt_prefix={encrypt[:20]}"
                )
                return PlainTextResponse("invalid signature", status_code=403)

            try:
                plaintext, _ = crypto.decrypt_message(xml_body)
            except Exception as e:
                logger.error(f"[WeCom] Failed to decrypt message: {e}")
                return PlainTextResponse("decrypt error", status_code=500)

            try:
                msg = WecomMessage.from_xml(plaintext)
            except Exception as e:
                logger.error(f"[WeCom] Failed to parse message XML: {e}")
                return PlainTextResponse("parse error", status_code=500)

            logger.info(
                f"[WeCom] Received: user={msg.from_user_name}, "
                f"type={msg.msg_type}, content={str(msg.content or '')[:50]!r}"
            )

            # 企业微信要求 5 秒内响应，消息处理放后台
            background_tasks.add_task(handler.process_message, msg)

            # 返回空字符串表示成功接收
            return PlainTextResponse("")

        @router.get("/wecom/stats")
        async def wecom_stats():
            """获取会话统计信息（调试用）."""
            return handler.get_session_stats()

        return router

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await self.message_sender.send_text(recipient_id, text)

    async def on_start(self) -> None:
        logger.info("[WeCom] Plugin started")

    async def on_stop(self) -> None:
        logger.info("[WeCom] Plugin stopped")


def register(api: PluginAPI) -> WecomChannelPlugin:
    """Plugin 入口点 - 由 PluginLifecycle.register() 调用."""
    plugin = WecomChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[WeCom] Plugin registered")
    return plugin
