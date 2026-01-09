"""Yunzhijia (云之家) API endpoints."""

import logging
from fastapi import APIRouter, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from api.models.yunzhijia import YZJRobotMsg
from api.dependencies import get_yunzhijia_handler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["yunzhijia"])


@router.post("/yzj/chat")
async def yzj_chat(
    request: Request,
    msg: YZJRobotMsg,
    background_tasks: BackgroundTasks,
    yzj_token: str = Query(..., description="云之家机器人 token")
):
    """云之家消息接收端点

    接收云之家群聊机器人推送的消息，异步处理后通过 Webhook 回复。

    Args:
        request: FastAPI 请求对象
        msg: 云之家消息体
        background_tasks: 后台任务队列
        yzj_token: 云之家机器人 token（用于回复消息）

    Returns:
        JSONResponse: 立即返回确认消息
    """
    # 1. 从请求头获取 sessionId
    session_id = request.headers.get("sessionId")
    msg.sessionId = session_id

    logger.info(
        f"[YZJ] Received message: token={yzj_token[:8]}..., "
        f"session={session_id}, operator={msg.operatorName}, "
        f"content={msg.content[:30] if msg.content else 'empty'}..."
    )

    # 2. 验证必要参数
    if not yzj_token:
        logger.warning("[YZJ] Missing yzj_token parameter")
        return JSONResponse(content={
            "success": False,
            "data": {"type": 2, "content": "缺少 yzj_token 参数"}
        })

    if not msg.content or not msg.content.strip():
        logger.warning("[YZJ] Empty message content")
        return JSONResponse(content={
            "success": True,
            "data": {"type": 2, "content": "请输入有效内容"}
        })

    # 3. 后台异步处理
    handler = get_yunzhijia_handler()
    background_tasks.add_task(handler.process_message, msg, yzj_token)

    # 4. 立即返回（提醒用户可以打断）
    robot_name = msg.robotName if msg.robotName else "机器人"
    return JSONResponse(content={
        "success": True,
        "data": {
            "type": 2,
            "content": f"收到，开始深度探索..."
        }
    })


@router.get("/yzj/stats")
async def yzj_stats():
    """获取云之家处理器统计信息

    Returns:
        dict: 会话统计信息
    """
    handler = get_yunzhijia_handler()
    return handler.get_session_stats()
