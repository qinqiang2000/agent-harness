"""Yunzhijia channel plugin entry point."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelPlugin, ChannelMeta, ChannelCapabilities

from plugins.bundled.yunzhijia.handler import YunzhijiaHandler
from plugins.bundled.yunzhijia.models import YZJRobotMsg

logger = logging.getLogger(__name__)


class YunzhijiaChannelPlugin(ChannelPlugin):
    """Yunzhijia (云之家) channel plugin implementation."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config
        self.handler = YunzhijiaHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            config=self.config,
        )

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="yunzhijia",
            name="Yunzhijia Channel",
            webhook_path="/yzj/chat",
            description="云之家群聊机器人集成",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=True,
            send_images=True,
            send_cards=True,
            receive_webhook=True,
            session_management=True,
        )

    def create_router(self) -> APIRouter:
        """Create the /yzj/* router."""
        router = APIRouter(tags=["yunzhijia"])
        handler = self.handler
        verbose = self.config.get("verbose", False)

        @router.post("/yzj/chat")
        async def yzj_chat(
            request: Request,
            msg: YZJRobotMsg,
            background_tasks: BackgroundTasks,
            yzj_token: str = Query(..., description="云之家机器人 token"),
            skill: str = Query(None, description="指定使用的 skill"),
        ):
            """云之家消息接收端点"""
            session_id = request.headers.get("sessionId")
            msg.sessionId = session_id

            logger.info(
                f"[YZJ] Received message: token={yzj_token[:8]}..., "
                f"session={session_id}, operator={msg.operatorName}, "
                f"content={msg.content[:30] if msg.content else 'empty'}..."
            )

            if not yzj_token:
                return JSONResponse(content={
                    "success": False,
                    "data": {"type": 2, "content": "缺少 yzj_token 参数"},
                })

            if not msg.content or not msg.content.strip():
                return JSONResponse(content={
                    "success": True,
                    "data": {"type": 2, "content": "请输入有效内容"},
                })

            background_tasks.add_task(handler.process_message, msg, yzj_token, skill)

            message_content = (
                "收到，我马上探索最佳答案"
                if verbose
                else "收到，我马上探索最佳答案（受限于云之家，过程信息不输出，请耐心等待...）"
            )
            return JSONResponse(content={
                "success": True,
                "data": {"type": 2, "content": message_content},
            })

        @router.get("/yzj/stats")
        async def yzj_stats():
            """获取云之家处理器统计信息"""
            return handler.get_session_stats()

        return router

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a text message to a recipient via Yunzhijia webhook."""
        if not context or "token" not in context:
            logger.error("[YZJ] Cannot send_text without 'token' in context")
            return False
        await self.handler.message_sender.send_text(
            context["token"], recipient_id, text,
        )
        return True

    async def on_start(self) -> None:
        logger.info("[YZJ] Yunzhijia channel plugin started")

    async def on_stop(self) -> None:
        logger.info("[YZJ] Yunzhijia channel plugin stopped")


def register(api: PluginAPI) -> YunzhijiaChannelPlugin:
    """Plugin entry point - called by PluginLifecycle.register().

    Args:
        api: PluginAPI instance

    Returns:
        YunzhijiaChannelPlugin instance
    """
    plugin = YunzhijiaChannelPlugin(api)

    # Register the channel's router
    router = plugin.create_router()
    api.register_router(router)

    logger.info(f"[YZJ] Yunzhijia plugin registered with config: {api.config}")
    return plugin
