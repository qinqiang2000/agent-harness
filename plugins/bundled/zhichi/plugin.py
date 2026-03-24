"""智齿 Channel Plugin 入口."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.zhichi.handler import ZhichiHandler
from plugins.bundled.zhichi.message_sender import ZhichiMessageSender
from plugins.bundled.zhichi.models import ThirdAlgorithmReqVo, ThirdAlgorithmRespWrapper
from plugins.bundled.zhichi.token_manager import ZhichiTokenManager

logger = logging.getLogger(__name__)


class ZhichiChannelPlugin(ChannelPlugin):
    """智齿客服机器人 Channel Plugin."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config

        self.token_manager = ZhichiTokenManager(
            app_id=self.config.get("app_id", ""),
            app_key=self.config.get("app_key", ""),
            token_api_url=self.config.get(
                "token_api_url", "https://www.sobot.com/api/get_token"
            ),
            refresh_buffer_seconds=self.config.get("token_refresh_buffer_seconds", 300),
        )

        self.message_sender = ZhichiMessageSender(
            token_manager=self.token_manager,
            answer_url_stream=self.config.get(
                "answer_url_stream",
                "https://www.sobot.com/api/robot/third_algorithm/stream/answer",
            ),
            answer_url_no_stream=self.config.get(
                "answer_url_no_stream",
                "https://www.sobot.com/api/robot/third_algorithm/answer",
            ),
            mock_send=self.config.get("mock_send", False),
        )

        self.handler = ZhichiHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            message_sender=self.message_sender,
            config=self.config,
        )

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="zhichi",
            name="智齿客服机器人",
            webhook_path="/zhichi/ask",
            description="智齿客服机器人 Channel 集成",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=True,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=True,
        )

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["zhichi"])
        handler = self.handler

        @router.post("/zhichi/ask")
        async def zhichi_ask(
            req: ThirdAlgorithmReqVo,
            background_tasks: BackgroundTasks,
        ):
            """智齿消息接收端点，立即返回 200，后台处理."""
            if not req.question or not req.question.strip():
                return JSONResponse(content={"code": 1, "message": "question 不能为空"})

            if not req.ai_agent_cid or not req.ai_agent_cid.strip():
                return JSONResponse(content={"code": 1, "message": "ai_agent_cid 不能为空"})

            logger.info(
                f"[Zhichi] Received request: {req.model_dump_json()}"
            )
            background_tasks.add_task(handler.process_message, req)
            ack = ThirdAlgorithmRespWrapper()
            ack_body = ack.model_dump(exclude_none=True)
            logger.info(f"[Zhichi] Immediate response: {ack_body}")
            return JSONResponse(content=ack_body)

        @router.get("/zhichi/stats")
        async def zhichi_stats():
            """获取会话统计信息（调试用）."""
            return handler.get_session_stats()

        return router

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        req_stream = (context or {}).get("req_stream", False)
        return await self.message_sender.send_answer(
            ai_agent_cid=recipient_id,
            llm_answer=text,
            req_stream=req_stream,
        )

    async def on_start(self) -> None:
        self.token_manager.start_background_refresh()
        logger.info("[Zhichi] Plugin started, background token refresh running")

    async def on_stop(self) -> None:
        self.token_manager.stop_background_refresh()
        logger.info("[Zhichi] Plugin stopped")


def register(api: PluginAPI) -> ZhichiChannelPlugin:
    """Plugin 入口点 - 由 PluginLifecycle.register() 调用."""
    plugin = ZhichiChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info(f"[Zhichi] Plugin registered")
    return plugin
