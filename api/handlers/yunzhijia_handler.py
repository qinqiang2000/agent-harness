"""Yunzhijia (云之家) message handler."""

import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

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
    5. 会话超时：自动清理超时未活动的会话，避免上下文无限累积
    """

    NOTIFY_URL = "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken={}"

    # 停止命令配置
    STOP_KEYWORDS = ["停止", "stop", "取消", "cancel"]
    MAX_STOP_COMMAND_LENGTH = 10

    # 会话超时配置（单位：秒）
    SESSION_TIMEOUT_SECONDS = int(os.getenv("YZJ_SESSION_TIMEOUT", "3600"))  # 默认 60 分钟

    # 图片卡片配置
    CARD_NOTICE_TEMPLATE_ID = os.getenv("YZJ_CARD_TEMPLATE_ID", "")  # 云之家卡片模板 ID
    MAX_IMG_NUM_IN_CARD_NOTICE = int(os.getenv("YZJ_MAX_IMG_PER_CARD", "3"))  # 每个卡片最大图片数
    SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL", "http://localhost:9090")  # 服务基础 URL

    # FAQ 配置：预定义问答，不走 agent（支持多个触发关键词）
    FAQ_MAP = {
        "你好，你能做什么呢?": '"0幻觉"回答发票云知识库相关问题',
        "你好": '"你好，我可0幻觉"回答发票云知识库相关问题，请有什么可以帮助您',
        "你能做什么": '"0幻觉"回答发票云知识库相关问题',
        "能做什么": '"0幻觉"回答发票云知识库相关问题',
    }

    def __init__(self, agent_service: AgentService, session_service: SessionService):
        """初始化云之家处理器

        Args:
            agent_service: Agent 服务实例
            session_service: Session 服务实例（用于会话中断）
        """
        self.agent_service = agent_service
        self.session_service = session_service
        # 会话映射：{yzj_session_id: {"agent_session_id": str, "last_active": float}}
        self.session_map: Dict[str, Dict[str, any]] = {}

    def _clean_content(self, content: str) -> str:
        """清理消息内容

        去除 @提及（如 @API客服）并去除前后空格

        Args:
            content: 原始消息内容

        Returns:
            str: 清理后的消息内容
        """
        # 去除 @提及（匹配 @xxx 空格）
        cleaned = re.sub(r'@\S+\s*', '', content)
        # 去除前后空格
        return cleaned.strip()

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
        # 清理消息内容
        cleaned = self._clean_content(content)

        # 长度限制
        if len(cleaned) > self.MAX_STOP_COMMAND_LENGTH:
            return False

        # 转小写后检查关键词
        cleaned_lower = cleaned.lower()
        return any(keyword in cleaned_lower for keyword in self.STOP_KEYWORDS)

    def _match_faq(self, content: str) -> Optional[str]:
        """匹配 FAQ，返回预定义答案

        规则：
        1. 去除 @提及和前后空格
        2. 精确匹配 FAQ_MAP 中的关键词（不区分大小写）

        Args:
            content: 消息内容

        Returns:
            Optional[str]: 如果匹配，返回预定义答案；否则返回 None
        """
        # 清理消息内容
        cleaned = self._clean_content(content)

        # 精确匹配（不区分大小写）
        for faq_key, faq_answer in self.FAQ_MAP.items():
            if cleaned.lower() == faq_key.lower():
                logger.info(f"[YZJ] FAQ matched: '{cleaned}' -> '{faq_answer}'")
                return faq_answer

        return None

    def _check_session_timeout(self, yzj_session_id: str) -> Optional[str]:
        """检查会话是否超时，返回有效的 agent_session_id

        Args:
            yzj_session_id: 云之家会话 ID

        Returns:
            Optional[str]: 如果会话未超时，返回 agent_session_id；否则返回 None
        """
        if yzj_session_id not in self.session_map:
            return None

        session_info = self.session_map[yzj_session_id]
        last_active = session_info.get("last_active", 0)
        current_time = time.time()
        elapsed = current_time - last_active

        if elapsed > self.SESSION_TIMEOUT_SECONDS:
            # 会话超时，清理
            agent_session_id = session_info.get("agent_session_id")
            logger.info(
                f"[YZJ] Session timeout: yzj_session={yzj_session_id}, "
                f"agent_session={agent_session_id}, "
                f"inactive_time={elapsed:.0f}s (threshold={self.SESSION_TIMEOUT_SECONDS}s)"
            )
            del self.session_map[yzj_session_id]
            return None

        # 会话有效
        return session_info.get("agent_session_id")

    def _update_session_activity(self, yzj_session_id: str, agent_session_id: str):
        """更新会话活动时间

        Args:
            yzj_session_id: 云之家会话 ID
            agent_session_id: Agent 会话 ID
        """
        self.session_map[yzj_session_id] = {
            "agent_session_id": agent_session_id,
            "last_active": time.time()
        }

    def _cleanup_expired_sessions(self):
        """清理所有过期会话"""
        current_time = time.time()
        expired_sessions = []

        for yzj_session_id, session_info in self.session_map.items():
            last_active = session_info.get("last_active", 0)
            if current_time - last_active > self.SESSION_TIMEOUT_SECONDS:
                expired_sessions.append(yzj_session_id)

        for yzj_session_id in expired_sessions:
            agent_session_id = self.session_map[yzj_session_id].get("agent_session_id")
            logger.info(
                f"[YZJ] Cleaning expired session: yzj_session={yzj_session_id}, "
                f"agent_session={agent_session_id}"
            )
            del self.session_map[yzj_session_id]

        if expired_sessions:
            logger.info(f"[YZJ] Cleaned {len(expired_sessions)} expired sessions")

    async def process_message(self, msg: YZJRobotMsg, yzj_token: str):
        """处理云之家消息

        Args:
            msg: 云之家消息
            yzj_token: 云之家机器人 token
        """
        yzj_session_id = msg.sessionId
        logger.info(f"[YZJ] Received message: {msg.model_dump()}")
        logger.info(f"[YZJ] Processing message: session={yzj_session_id}, content={msg.content[:50]}...")

        try:
            # 0. 清理过期会话（定期维护）
            self._cleanup_expired_sessions()

            # 1. 检查 FAQ（固定回复，不走 agent）
            faq_answer = self._match_faq(msg.content)
            if faq_answer:
                await self._send_message(yzj_token, msg.operatorOpenid, faq_answer)
                logger.info(f"[YZJ] FAQ response sent for session: {yzj_session_id}")
                return  # 直接返回，不继续处理

            # 2. 检测停止命令
            if self._is_stop_command(msg.content):
                # 获取现有 agent session（从新数据结构中获取）
                session_info = self.session_map.get(yzj_session_id)
                agent_session_id = session_info.get("agent_session_id") if session_info else None
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

            # 3. 获取或创建 agent session（检查超时）
            agent_session_id = self._check_session_timeout(yzj_session_id)
            if agent_session_id:
                logger.info(f"[YZJ] Resuming agent session: {agent_session_id}")
            else:
                logger.info(f"[YZJ] Creating new agent session for: {yzj_session_id}")

            # 4. 获取机器人名称（用于引导用户回复）
            robot_name = f"@{msg.robotName}" if msg.robotName else "@机器人"
            logger.info(f"[YZJ] Robot name: {robot_name}")

            # 5. 清理消息内容（去除 @提及）
            cleaned_content = self._clean_content(msg.content)
            logger.info(f"[YZJ] Cleaned content: {cleaned_content[:50]}...")

            # 6. 构建请求
            request = QueryRequest(
                prompt=cleaned_content,
                skill="customer-service",
                tenant_id="yzj",
                language="中文",
                session_id=agent_session_id
            )

            # 7. 实时处理消息流 - 每收到一条 assistant_message 立即发送
            message_count = 0
            async for event in self.agent_service.process_query(request):
                event_type = event.get("event")

                if event_type == "session_created":
                    # 更新会话映射 - 解析 JSON 数据
                    data = json.loads(event["data"])
                    new_session_id = data["session_id"]
                    agent_session_id = new_session_id  # 更新局部变量
                    self._update_session_activity(yzj_session_id, new_session_id)
                    logger.info(f"[YZJ] Session mapping updated: {yzj_session_id} -> {new_session_id}")

                elif event_type == "assistant_message":
                    # 实时发送每条消息 - 解析 JSON 数据
                    data = json.loads(event["data"])
                    content = data.get("content", "")
                    if content and content.strip():
                        message_count += 1
                        await self._send_message(yzj_token, msg.operatorOpenid, content)
                        logger.info(f"[YZJ] Sent message #{message_count} for session: {yzj_session_id}")

                        # 更新会话活动时间
                        if agent_session_id:
                            self._update_session_activity(yzj_session_id, agent_session_id)

                elif event_type == "ask_user_question":
                    # 处理 AskUserQuestion 工具调用
                    data = json.loads(event["data"])
                    questions = data.get("questions", [])

                    # 将问题格式化为文本消息
                    for question in questions:
                        formatted_message = self._format_question(question, robot_name)
                        message_count += 1
                        await self._send_message(yzj_token, msg.operatorOpenid, formatted_message)
                        logger.info(f"[YZJ] Sent question #{message_count} for session: {yzj_session_id}")

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
        """发送消息到云之家（支持图片）

        Args:
            yzj_token: 云之家机器人 token
            operator_openid: 操作人 OpenID
            content: 消息内容（可能包含 markdown 图片）
        """
        from api.utils.image_utils import extract_images_from_content

        # 提取图片并清理内容
        cleaned_content, img_urls = extract_images_from_content(content, self.SERVICE_BASE_URL)

        # 如果有图片，提示用户
        if img_urls:
            cleaned_content += "\n\n（具体图片请查看下方消息）"

        # 发送文本消息
        url = self.NOTIFY_URL.format(yzj_token)
        data = {
            "content": cleaned_content,
            "notifyParams": [{"type": "openIds", "values": [operator_openid]}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        logger.info(f"[YZJ] Text message sent to {operator_openid}")
                    else:
                        response_text = await response.text()
                        logger.error(f"[YZJ] Failed to send message: {response_text}")
        except Exception as e:
            logger.error(f"[YZJ] Error sending message: {e}", exc_info=True)

        # 发送图片卡片
        if img_urls:
            await self._send_card_notice(yzj_token, operator_openid, img_urls)

    async def _send_card_notice(
        self,
        yzj_token: str,
        operator_openid: str,
        img_urls: List[str]
    ):
        """发送云之家图片卡片消息

        Args:
            yzj_token: 云之家机器人 token
            operator_openid: 操作人 OpenID
            img_urls: 图片 URL 列表
        """
        if not img_urls or not self.CARD_NOTICE_TEMPLATE_ID:
            logger.warning("[YZJ] No images or card template not configured")
            return

        img_num = len(img_urls)
        card_num = (img_num + self.MAX_IMG_NUM_IN_CARD_NOTICE - 1) // self.MAX_IMG_NUM_IN_CARD_NOTICE

        url = self.NOTIFY_URL.format(yzj_token)

        for i in range(card_num):
            data_content = self._gen_card_notice_data_content(img_urls, i)

            payload = {
                "msgType": 2,  # 卡片消息
                "param": {
                    "baseInfo": {
                        "templateId": self.CARD_NOTICE_TEMPLATE_ID,
                        "dataContent": str(data_content)
                    }
                },
                "notifyParams": [{"type": "openIds", "values": [operator_openid]}]
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as response:
                        if response.status == 200:
                            logger.info(f"[YZJ] Card notice sent successfully, card {i+1}/{card_num}")
                        else:
                            response_text = await response.text()
                            logger.error(f"[YZJ] Failed to send card notice: {response_text}")
            except Exception as e:
                logger.error(f"[YZJ] Error sending card notice: {e}", exc_info=True)

    def _gen_card_notice_data_content(self, img_urls: List[str], card_index: int) -> dict:
        """构建卡片消息 data_content

        Args:
            img_urls: 图片 URL 列表
            card_index: 当前卡片索引

        Returns:
            卡片数据字典
        """
        data_content = {}
        start_idx = card_index * self.MAX_IMG_NUM_IN_CARD_NOTICE
        end_idx = min(start_idx + self.MAX_IMG_NUM_IN_CARD_NOTICE, len(img_urls))

        for j, idx in enumerate(range(start_idx, end_idx)):
            img_url = img_urls[idx]
            if j == 0:
                data_content["bigImageUrl"] = img_url
            else:
                data_content[f"bigImage{j}Url"] = img_url

        return data_content

    def _format_question(self, question: dict, robot_name: Optional[str] = None) -> str:
        """将 AskUserQuestion 格式化为云之家可读的文本

        Args:
            question: 问题字典，包含 question, options 等字段
            robot_name: 机器人名称（如 "@API客服"），用于指引用户回复

        Returns:
            格式化后的消息文本

        Examples:
            输出示例（有 robot_name）：
            请选择你的问题类型

            1. 功能咨询 - 产品功能相关问题
            2. 故障排查 - 使用中遇到的问题
            3. 其他

            请回复选项编号或文字（@API客服 回复）
        """
        question_text = question.get("question", "请选择")
        options = question.get("options", [])

        # 构建消息
        lines = [question_text, ""]

        for i, option in enumerate(options, 1):
            label = option.get("label", "")
            description = option.get("description", "")

            if description:
                lines.append(f"{i}. {label} - {description}")
            else:
                lines.append(f"{i}. {label}")

        lines.append("")
        if robot_name:
            lines.append(f"请回复选项编号或文字（{robot_name} 回复）")
        else:
            lines.append("请回复对应的选项编号或文字。")

        return "\n".join(lines)

    def get_session_stats(self) -> dict:
        """获取会话统计信息

        Returns:
            dict: 统计信息，包括会话数量、映射关系和活动时间
        """
        current_time = time.time()
        sessions = []

        for yzj_session_id, session_info in self.session_map.items():
            agent_session_id = session_info.get("agent_session_id")
            last_active = session_info.get("last_active", 0)
            inactive_seconds = current_time - last_active

            sessions.append({
                "yzj_session_id": yzj_session_id,
                "agent_session_id": agent_session_id,
                "inactive_seconds": int(inactive_seconds),
                "will_expire_in": max(0, int(self.SESSION_TIMEOUT_SECONDS - inactive_seconds))
            })

        return {
            "total_sessions": len(self.session_map),
            "session_timeout_seconds": self.SESSION_TIMEOUT_SECONDS,
            "sessions": sessions
        }
