"""智齿 Channel Plugin 入口."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.zhichi.agent_status import ZhichiAgentStatusClient
from plugins.bundled.zhichi.handler import ZhichiHandler
from plugins.bundled.zhichi.models import ThirdAlgorithmReqVo, ThirdAlgorithmRespVo, ThirdAlgorithmRespWrapper
from plugins.bundled.zhichi.quick_reply import generate_quick_reply
from plugins.bundled.zhichi.token_manager import ZhichiTokenManager
# from plugins.bundled.zhichi.message_sender import ZhichiMessageSender

logger = logging.getLogger(__name__)


class ZhichiChannelPlugin(ChannelPlugin):
    """智齿客服机器人 Channel Plugin."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config

        self.token_manager: Optional[ZhichiTokenManager] = None
        agent_status_client: Optional[ZhichiAgentStatusClient] = None
        if self.config.get("check_agent_online", True):
            app_id = self.config.get("app_id", "")
            app_key = self.config.get("app_key", "")
            if app_id and app_key:
                self.token_manager = ZhichiTokenManager(
                    app_id=app_id,
                    app_key=app_key,
                    token_api_url=self.config.get(
                        "token_api_url", "https://www.soboten.com/api/get_token"
                    ),
                    refresh_buffer_seconds=self.config.get("token_refresh_buffer_seconds", 300),
                )
                agent_status_client = ZhichiAgentStatusClient(
                    token_manager=self.token_manager,
                    once_data_url=self.config.get(
                        "once_data_url",
                        "https://www.soboten.com/api/chat/5/user/get_once_data",
                    ),
                )
            else:
                logger.warning(
                    "[Zhichi] check_agent_online=true 但未配置 app_id/app_key，转人工前不做在线查询"
                )

        self.handler = ZhichiHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            config=self.config,
            agent_status_client=agent_status_client,
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
            send_text=False,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=True,
            transfer_human=True,
        )

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["zhichi"])
        handler = self.handler
        static_dir = Path(__file__).parent / "static"

        @router.get("/zhichi/")
        async def zhichi_index():
            return FileResponse(static_dir / "index.html")

        router.mount("/zhichi/static", StaticFiles(directory=static_dir), name="zhichi-static")

        @router.post("/zhichi/ask")
        async def zhichi_ask(req: ThirdAlgorithmReqVo):
            """智齿消息接收端点，同步处理后直接返回结果."""
            if not req.question or not req.question.strip():
                return JSONResponse(content={"code": 1, "message": "question 不能为空"})

            if not req.ai_agent_cid or not req.ai_agent_cid.strip():
                return JSONResponse(content={"code": 1, "message": "ai_agent_cid 不能为空"})

            logger.info(f"[Zhichi] Received request: {req.model_dump_json()}")

            if req.req_stream:
                async def generate():
                    # 先推送即时回复（与主 Agent 启动并行，提升响应体验）
                    # quick_reply_text = generate_quick_reply(req.question)
                    # waiting = ThirdAlgorithmRespWrapper(
                    #     data=ThirdAlgorithmRespVo(
                    #         llm_answer=quick_reply_text + "\n",
                    #         robot_answer_message_type="MESSAGE",
                    #         runtimeid=req.runtimeid,
                    #         message_end=False,
                    #     )
                    # )
                    # waiting_json = waiting.model_dump_json(exclude_none=True)
                    # logger.info(f"[Zhichi] Stream chunk: {waiting_json}")
                    # yield f"data:{waiting_json}\n\n"

                    # 推送 AI 实际答案
                    async for llm_answer, message_end, transfer, group_name in handler.stream_answer(req):
                        chunk = ThirdAlgorithmRespWrapper(
                            data=ThirdAlgorithmRespVo(
                                llm_answer=llm_answer,
                                runtimeid=req.runtimeid,
                                message_end=message_end,
                                third_transfer_flag=transfer or None,
                                third_transfer_groupName=group_name or None,
                            )
                        )
                        chunk_json = chunk.model_dump_json(exclude_none=True)
                        logger.info(f"[Zhichi] Stream chunk: {chunk_json}")
                        # 节点 7：智齿 chunk 发出
                        logger.info(f"[PERF] ZHICHI_SEND_DONE chunk_len={len(chunk_json)}bytes")
                        yield f"data:{chunk_json}\n\n"

                return StreamingResponse(
                    generate(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )

            else:
                llm_answer, transfer, group_name = await handler.get_answer(req)
                resp = ThirdAlgorithmRespWrapper(
                    data=ThirdAlgorithmRespVo(
                        llm_answer=llm_answer,
                        runtimeid=req.runtimeid,
                        third_transfer_flag=transfer or None,
                        third_transfer_groupName=group_name or None,
                    )
                )
                resp_json = resp.model_dump_json(exclude_none=True)
                logger.info(f"[Zhichi] Synchronous response: {resp_json}")
                return JSONResponse(content=resp.model_dump(exclude_none=True))

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
        return False

    async def on_start(self) -> None:
        if self.token_manager:
            self.token_manager.start_background_refresh()
        logger.info("[Zhichi] Plugin started")

    async def on_stop(self) -> None:
        if self.token_manager:
            self.token_manager.stop_background_refresh()
        logger.info("[Zhichi] Plugin stopped")


def register(api: PluginAPI) -> ZhichiChannelPlugin:
    """Plugin 入口点 - 由 PluginLifecycle.register() 调用."""
    plugin = ZhichiChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info(f"[Zhichi] Plugin registered")
    return plugin
