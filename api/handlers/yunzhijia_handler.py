"""Yunzhijia (云之家) message handler."""

import asyncio
import json
import logging
import re
from typing import Dict

import aiohttp

from api.models.yunzhijia import YZJRobotMsg
from api.models.requests import QueryRequest
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

logger = logging.getLogger(__name__)


class YunzhijiaHandler:
    """云之家消息处理器

    职责：
    1. 会话映射管理：yzj_session_id ↔ agent_session_id
    2. 实时消息推送：每收到一条 assistant_message 立即发送给用户
    3. 云之家推送：调用云之家 Webhook API 发送消息
    4. 会话中断：支持用户发送"停止"命令中断正在运行的会话
    """

    NOTIFY_URL = "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken={}"

    # 停止命令关键词（不区分大小写）
    STOP_KEYWORDS = ["停止", "stop", "取消", "cancel"]

    # 停止命令的最大长度（避免误伤）
    MAX_STOP_COMMAND_LENGTH = 10

    def __init__(self, agent_service: AgentService, session_service: SessionService):
        """初始化云之家处理器

        Args:
            agent_service: Agent 服务实例
            session_service: Session 服务实例（用于会话中断）
        """
        self.agent_service = agent_service
        self.session_service = session_service
        self.session_map: Dict[str, str] = {}  # {yzj_session_id: agent_session_id}

    def _is_stop_command(self, content: str) -> bool:
        """判断是否为停止命令

        规则：
        1. 去除 @提及（如 @API客服）
        2. 去除前后空格
        3. 消息长度 ≤ MAX_STOP_COMMAND_LENGTH
        4. 包含停止关键词

        Args:
            content: 消息内容

        Returns:
            bool: 是否为停止命令
        """
        # 去除 @提及（匹配 @xxx 空格）
        cleaned = re.sub(r'@\S+\s*', '', content)

        # 去除前后空格
        cleaned = cleaned.strip()

        # 长度限制
        if len(cleaned) > self.MAX_STOP_COMMAND_LENGTH:
            return False

        # 转小写后检查关键词
        cleaned_lower = cleaned.lower()
        return any(keyword in cleaned_lower for keyword in self.STOP_KEYWORDS)

    async def process_message(self, msg: YZJRobotMsg, yzj_token: str):
        """处理云之家消息

        Args:
            msg: 云之家消息
            yzj_token: 云之家机器人 token
        """
        yzj_session_id = msg.sessionId
        logger.info(f"[YZJ] Processing message: session={yzj_session_id}, content={msg.content[:50]}...")

        try:
            # 1. 检测停止命令
            if self._is_stop_command(msg.content):
                # 获取现有 agent session
                agent_session_id = self.session_map.get(yzj_session_id)
                if agent_session_id:
                    logger.info(f"[YZJ] Stop command detected, interrupting session: {agent_session_id}")
                    success = await self.session_service.interrupt(agent_session_id)

                    if success:
                        await self._send_message(
                            yzj_token,
                            msg.operatorOpenid,
                            "✅ 已停止当前任务"
                        )
                        logger.info(f"[YZJ] Session interrupted successfully: {agent_session_id}")
                    else:
                        await self._send_message(
                            yzj_token,
                            msg.operatorOpenid,
                            "⚠️ 停止失败，会话可能已结束"
                        )
                        logger.warning(f"[YZJ] Failed to interrupt session: {agent_session_id}")
                else:
                    await self._send_message(
                        yzj_token,
                        msg.operatorOpenid,
                        "当前没有正在运行的任务"
                    )
                    logger.info(f"[YZJ] No active session to interrupt for: {yzj_session_id}")

                return  # 直接返回，不继续处理

            # 2. 获取或创建 agent session
            agent_session_id = self.session_map.get(yzj_session_id)
            if agent_session_id:
                logger.info(f"[YZJ] Resuming agent session: {agent_session_id}")
            else:
                logger.info(f"[YZJ] Creating new agent session for: {yzj_session_id}")

            # 3. 构建请求
            request = QueryRequest(
                prompt=msg.content,
                skill="customer-service",
                tenant_id="yzj",
                language="中文",
                session_id=agent_session_id
            )

            # 4. 实时处理消息流 - 每收到一条 assistant_message 立即发送
            message_count = 0
            async for event in self.agent_service.process_query(request):
                event_type = event.get("event")

                if event_type == "session_created":
                    # 更新会话映射 - 解析 JSON 数据
                    data = json.loads(event["data"])
                    new_session_id = data["session_id"]
                    self.session_map[yzj_session_id] = new_session_id
                    logger.info(f"[YZJ] Session mapping updated: {yzj_session_id} -> {new_session_id}")

                elif event_type == "assistant_message":
                    # 实时发送每条消息 - 解析 JSON 数据
                    data = json.loads(event["data"])
                    content = data.get("content", "")
                    if content and content.strip():
                        message_count += 1
                        await self._send_message(yzj_token, msg.operatorOpenid, content)
                        logger.info(f"[YZJ] Sent message #{message_count} for session: {yzj_session_id}")

                elif event_type == "result":
                    # 解析 JSON 数据
                    result_data = json.loads(event.get("data", "{}"))
                    logger.info(
                        f"[YZJ] Agent completed: session={result_data.get('session_id')}, "
                        f"duration={result_data.get('duration_ms')}ms, "
                        f"turns={result_data.get('num_turns')}, "
                        f"messages_sent={message_count}"
                    )

                elif event_type == "error":
                    # 解析 JSON 数据
                    error_data = json.loads(event.get("data", "{}"))
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
            "session_mappings": list(self.session_map.keys())
        }
