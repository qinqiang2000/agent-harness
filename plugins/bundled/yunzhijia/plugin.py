"""Yunzhijia channel plugin entry point."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelPlugin, ChannelMeta, ChannelCapabilities

from plugins.bundled.yunzhijia.handler import YunzhijiaHandler
from plugins.bundled.yunzhijia.message_sender import mock_pop_messages
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
            transfer_human=False,  # 云之家不支持转人工
        )

    def create_router(self) -> APIRouter:
        """Create the /yzj/* router."""
        router = APIRouter(tags=["yunzhijia"])
        handler = self.handler

        # === Debug：打印云之家发来的原始请求体（解决 422 时定位字段不匹配） ===
        @router.post("/yzj/chat-debug")
        async def yzj_chat_debug(request: Request):
            """收到原始请求打日志，不解析模型。仅用于定位 422 错误。"""
            body = await request.body()
            logger.info(f"[YZJ DEBUG] headers: {dict(request.headers)}")
            logger.info(f"[YZJ DEBUG] query: {dict(request.query_params)}")
            logger.info(f"[YZJ DEBUG] raw body: {body.decode('utf-8', errors='replace')}")
            return JSONResponse(content={
                "success": True,
                "data": {"type": 2, "content": ""},
            })

        @router.post("/yzj/chat")
        async def yzj_chat(
            request: Request,
            background_tasks: BackgroundTasks,
            yzj_token: str = Query(None, description="云之家机器人 token（对话型机器人不带此参数）"),
            skill: str = Query(None, description="指定使用的 skill"),
        ):
            """云之家消息接收端点"""
            # 打印完整原始 body（排查引用消息等额外字段）
            raw_body = await request.body()
            logger.info(f"[YZJ RAW] {raw_body.decode('utf-8', errors='replace')}")

            # 手动解析为 model（允许额外字段不报错）
            import json as _json
            try:
                body_dict = _json.loads(raw_body)
            except Exception:
                return JSONResponse(status_code=400, content={"success": False, "data": {"type": 2, "content": "无法解析请求体"}})

            msg = YZJRobotMsg(**{k: v for k, v in body_dict.items() if k in YZJRobotMsg.model_fields})

            session_id = request.headers.get("sessionId")
            msg.sessionId = session_id

            # 对话型机器人不带 yzj_token，用 robotId 做回调标识
            effective_token = yzj_token or msg.robotId or "unknown"

            logger.info(
                f"[YZJ] Received message: token={effective_token[:8]}..., "
                f"session={session_id}, operator={msg.operatorName}, "
                f"content={msg.content[:30] if msg.content else 'empty'}..."
            )

            if not msg.content or not msg.content.strip():
                return JSONResponse(content={
                    "success": True,
                    "data": {"type": 2, "content": "请输入有效内容"},
                })

            background_tasks.add_task(handler.process_message, msg, effective_token, skill)

            return JSONResponse(content={
                "success": True,
                "data": {"type": 2, "content": ""},
            })

        @router.get("/yzj/stats")
        async def yzj_stats():
            """获取云之家处理器统计信息"""
            return handler.get_session_stats()

        if os.getenv("YZJ_MOCK_ENABLED") == "true":
            @router.get("/yzj/mock/poll")
            async def yzj_mock_poll(openid: str = Query(...), token: str = Query("mock")):
                """轮询 mock 消息队列，取出并清空当前消息。"""
                return {"messages": mock_pop_messages(token, openid)}

            @router.get("/yzj/debug")
            async def yzj_debug():
                """调试用聊天页面"""
                html_path = os.path.join(os.path.dirname(__file__), "debug.html")
                return FileResponse(html_path, media_type="text/html")

            logger.info("[YZJ] Mock mode enabled: /yzj/debug and /yzj/mock/poll registered")

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
