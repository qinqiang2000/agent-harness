"""Yunzhijia (云之家) message handler."""

import asyncio
import logging
from typing import Dict

import aiohttp

from api.models.yunzhijia import YZJRobotMsg
from api.models.requests import QueryRequest
from api.services.agent_service import AgentService

logger = logging.getLogger(__name__)


class YunzhijiaHandler:
    """云之家消息处理器

    职责：
    1. 会话映射管理：yzj_session_id ↔ agent_session_id
    2. 实时消息推送：每收到一条 assistant_message 立即发送给用户
    3. 云之家推送：调用云之家 Webhook API 发送消息
    """

    NOTIFY_URL = "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken={}"

    def __init__(self, agent_service: AgentService):
        """初始化云之家处理器

        Args:
            agent_service: Agent 服务实例
        """
        self.agent_service = agent_service
        self.session_map: Dict[str, str] = {}  # {yzj_session_id: agent_session_id}

    async def process_message(self, msg: YZJRobotMsg, yzj_token: str):
        """处理云之家消息

        Args:
            msg: 云之家消息
            yzj_token: 云之家机器人 token
        """
        yzj_session_id = msg.sessionId
        logger.info(f"[YZJ] Processing message: session={yzj_session_id}, content={msg.content[:50]}...")

        try:
            # 1. 获取或创建 agent session
            agent_session_id = self.session_map.get(yzj_session_id)
            if agent_session_id:
                logger.info(f"[YZJ] Resuming agent session: {agent_session_id}")
            else:
                logger.info(f"[YZJ] Creating new agent session for: {yzj_session_id}")

            # 2. 构建请求
            request = QueryRequest(
                prompt=msg.content,
                skill="customer-service",
                tenant_id="yzj",
                language="中文",
                session_id=agent_session_id
            )

            # 3. 实时处理消息流 - 每收到一条 assistant_message 立即发送
            message_count = 0
            async for event in self.agent_service.process_query(request):
                event_type = event.get("event")

                if event_type == "session_created":
                    # 更新会话映射
                    new_session_id = event["data"]["session_id"]
                    self.session_map[yzj_session_id] = new_session_id
                    logger.info(f"[YZJ] Session mapping updated: {yzj_session_id} -> {new_session_id}")

                elif event_type == "assistant_message":
                    # 实时发送每条消息
                    content = event["data"]
                    if content and content.strip():
                        message_count += 1
                        await self._send_message(yzj_token, msg.operatorOpenid, content)
                        logger.info(f"[YZJ] Sent message #{message_count} for session: {yzj_session_id}")

                elif event_type == "result":
                    result_data = event.get("data", {})
                    logger.info(
                        f"[YZJ] Agent completed: session={result_data.get('session_id')}, "
                        f"duration={result_data.get('duration_ms')}ms, "
                        f"turns={result_data.get('num_turns')}, "
                        f"messages_sent={message_count}"
                    )

                elif event_type == "error":
                    error_data = event.get("data", {})
                    logger.error(f"[YZJ] Agent error: {error_data.get('message')}")
                    await self._send_message(
                        yzj_token,
                        msg.operatorOpenid,
                        f"抱歉，处理时出现错误：{error_data.get('message', '未知错误')}"
                    )

            # 如果没有发送任何消息，发送默认回复
            if message_count == 0:
                await self._send_message(
                    yzj_token,
                    msg.operatorOpenid,
                    "抱歉，未能获取到答案，请稍后再试。"
                )

        except Exception as e:
            logger.error(f"[YZJ] Error processing message: {e}", exc_info=True)
            await self._send_message(
                yzj_token,
                msg.operatorOpenid,
                "抱歉，处理消息时出现错误，请稍后再试。"
            )

    async def _send_message(self, yzj_token: str, operator_openid: str, content: str):
        """发送消息到云之家

        Args:
            yzj_token: 云之家机器人 token
            operator_openid: 操作人 OpenID（用于定向回复）
            content: 消息内容
        """
        url = self.NOTIFY_URL.format(yzj_token)
        data = {
            "content": content,
            "notifyParams": [{"type": "openIds", "values": [operator_openid]}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        logger.info(f"[YZJ] Message sent successfully to {operator_openid}")
                    else:
                        response_text = await response.text()
                        logger.error(
                            f"[YZJ] Failed to send message: status={response.status}, "
                            f"response={response_text}"
                        )
        except Exception as e:
            logger.error(f"[YZJ] Error sending message: {e}", exc_info=True)

    def get_session_stats(self) -> dict:
        """获取会话统计信息

        Returns:
            dict: 统计信息
        """
        return {
            "total_sessions": len(self.session_map),
            "processing_sessions": len(self.processing_sessions),
            "session_mappings": list(self.session_map.keys())
        }
