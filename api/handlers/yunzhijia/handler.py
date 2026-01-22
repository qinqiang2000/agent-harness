"""云之家消息处理器 - 主协调器."""

import json
import logging
import os
import re
from typing import Dict, List, Optional

from api.handlers.yunzhijia.card_builder import YunzhijiaCardBuilder
from api.handlers.yunzhijia.message_sender import YunzhijiaMessageSender
from api.handlers.yunzhijia.session_mapper import SessionMapper
from api.models.requests import QueryRequest
from api.models.yunzhijia import YZJRobotMsg
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

logger = logging.getLogger(__name__)


class YunzhijiaHandler:
    """云之家消息处理器

    职责：
    1. 协调各个子组件完成消息处理
    2. 实现消息处理主流程
    3. 处理 FAQ 和停止命令
    4. 管理消息流和事件处理
    """

    # 云之家通知 URL 模板
    NOTIFY_URL_TEMPLATE = "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken={}"

    # 停止命令配置
    STOP_KEYWORDS = ["停止", "stop", "取消", "cancel"]
    MAX_STOP_COMMAND_LENGTH = 10

    # FAQ 配置：预定义问答，不走 agent
    FAQ_MAP = {
        "你好，你能做什么呢?": '"0幻觉"回答发票云知识',
        "你好": '"你好，我可0幻觉"回答发票云知识，请有什么可以帮助您',
        "你能做什么": '"0幻觉"回答发票云知识',
        "能做什么": '"0幻觉"回答发票云知识',
    }

    def __init__(self, agent_service: AgentService, session_service: SessionService, default_skill: str = "customer-service"):
        """初始化云之家处理器

        Args:
            agent_service: Agent 服务实例
            session_service: Session 服务实例（用于会话中断）
            default_skill: 默认使用的 skill 名称
        """
        self.agent_service = agent_service
        self.session_service = session_service
        self.default_skill = default_skill

        # 初始化子组件
        self.session_mapper = SessionMapper(
            timeout_seconds=int(os.getenv("YZJ_SESSION_TIMEOUT", "3600"))
        )
        self.message_sender = YunzhijiaMessageSender(self.NOTIFY_URL_TEMPLATE)
        self.card_builder = YunzhijiaCardBuilder(
            template_id=os.getenv("YZJ_CARD_TEMPLATE_ID", ""),
            max_img_per_card=int(os.getenv("YZJ_MAX_IMG_PER_CARD", "3"))
        )

        # 配置
        self.service_base_url = os.getenv("SERVICE_BASE_URL", "http://localhost:9090")
        self.verbose = os.getenv("YZJ_VERBOSE", "false").lower() == "true"

    async def process_message(self, msg: YZJRobotMsg, yzj_token: str, skill: Optional[str] = None):
        """处理云之家消息

        Args:
            msg: 云之家消息
            yzj_token: 云之家机器人 token
            skill: 指定的 skill 名称（为 None 时使用 default_skill）
        """
        yzj_session_id = msg.sessionId
        # 确定使用的 skill（优先使用传入的，否则使用默认）
        effective_skill = skill or self.default_skill
        logger.info(f"[YZJ] Received message: {msg.model_dump()}")
        logger.info(f"[YZJ] Processing: session={yzj_session_id}, skill={effective_skill}, content={msg.content[:50]}...")

        try:
            # 0. 清理过期会话（定期维护）
            self.session_mapper.cleanup_expired()

            # 1. 检查 FAQ（固定回复，不走 agent）
            faq_answer = self._match_faq(msg.content)
            if faq_answer:
                await self.message_sender.send_text(yzj_token, msg.operatorOpenid, faq_answer)
                logger.info(f"[YZJ] FAQ response sent for session: {yzj_session_id}")
                return

            # 2. 检测停止命令
            if self._is_stop_command(msg.content):
                await self._handle_stop_command(yzj_token, msg.operatorOpenid, yzj_session_id)
                return

            # 3. 获取或创建 agent session（自动检查超时）
            agent_session_id = self.session_mapper.get_or_create(yzj_session_id)
            if agent_session_id:
                logger.info(f"[YZJ] Resuming agent session: {agent_session_id}")
            else:
                logger.info(f"[YZJ] Creating new agent session for: {yzj_session_id}")

            # 4. 获取机器人名称（用于引导用户回复）
            robot_name = f"@{msg.robotName}" if msg.robotName else "@机器人"

            # 5. 清理消息内容（去除 @提及）
            cleaned_content = self._clean_content(msg.content)

            # 6. 构建请求
            request = QueryRequest(
                prompt=cleaned_content,
                skill=effective_skill,
                tenant_id="yzj",
                language="中文",
                session_id=agent_session_id
            )

            # 7. 处理消息流
            await self._process_agent_stream(
                request, yzj_token, msg.operatorOpenid,
                yzj_session_id, robot_name
            )

        except Exception as e:
            logger.error(f"[YZJ] Error processing message: {e}", exc_info=True)
            await self.message_sender.send_text(
                yzj_token,
                msg.operatorOpenid,
                "抱歉，处理消息时出现错误，请稍后再试。"
            )

    async def _process_agent_stream(
        self,
        request: QueryRequest,
        yzj_token: str,
        operator_openid: str,
        yzj_session_id: str,
        robot_name: str
    ):
        """处理 Agent 消息流

        Args:
            request: Agent 查询请求
            yzj_token: 云之家 token
            operator_openid: 操作人 OpenID
            yzj_session_id: 云之家会话 ID
            robot_name: 机器人名称（用于提示）
        """
        message_count = 0
        has_sent_question = False  # 标记是否已发送 AskUserQuestion
        agent_session_id = request.session_id

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                # 更新会话映射
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                agent_session_id = new_session_id
                self.session_mapper.update_activity(yzj_session_id, new_session_id)
                logger.info(f"[YZJ] Session mapping: {yzj_session_id} -> {new_session_id}")

            elif event_type == "ask_user_question":
                # 处理 AskUserQuestion 工具调用
                has_sent_question = True  # 标记已发送问题
                data = json.loads(event["data"])
                questions = data.get("questions", [])

                for question in questions:
                    formatted_message = self._format_question(question, robot_name)
                    message_count += 1
                    await self.message_sender.send_text(
                        yzj_token, operator_openid, formatted_message
                    )
                    logger.info(f"[YZJ] Sent question #{message_count}")

            elif event_type == "result":
                result_data = json.loads(event.get("data", "{}"))

                # 如果已发送问题，跳过 result 内容（避免重复消息）
                if has_sent_question:
                    logger.info(
                        f"[YZJ] Skipped result (question sent): "
                        f"session={result_data.get('session_id')}, "
                        f"duration={result_data.get('duration_ms')}ms, "
                        f"turns={result_data.get('num_turns')}"
                    )
                else:
                    # 直接使用 ResultMessage.result 字段
                    if result_data.get("result"):
                        final_result = result_data["result"]
                        reply_with_hint = f"{final_result}\n\n👉 如还有疑问，可直接回复本消息"
                        await self.message_sender.send_with_images(
                            yzj_token, operator_openid, reply_with_hint,
                            self.service_base_url, self.card_builder
                        )
                        message_count += 1
                        logger.info(f"[YZJ] Sent final result")
                    else:
                        # 异常：没有 result 内容
                        logger.error("[YZJ] No result content in ResultMessage")

                    logger.info(
                        f"[YZJ] Completed: session={result_data.get('session_id')}, "
                        f"duration={result_data.get('duration_ms')}ms, "
                        f"turns={result_data.get('num_turns')}, "
                        f"messages={message_count}"
                    )

            elif event_type == "error":
                error_data = json.loads(event.get("data", "{}"))
                logger.error(f"[YZJ] Agent error: {error_data.get('message')}")
                await self.message_sender.send_text(
                    yzj_token, operator_openid,
                    f"抱歉，处理时出现错误：{error_data.get('message', '未知错误')}"
                )

        # 如果没有发送任何消息，发送默认回复
        if message_count == 0:
            await self.message_sender.send_text(
                yzj_token, operator_openid,
                "抱歉，未能获取到答案，请稍后再试。"
            )

    async def _handle_stop_command(
        self,
        yzj_token: str,
        operator_openid: str,
        yzj_session_id: str
    ):
        """处理停止命令

        Args:
            yzj_token: 云之家 token
            operator_openid: 操作人 OpenID
            yzj_session_id: 云之家会话 ID
        """
        agent_session_id = self.session_mapper.get_or_create(yzj_session_id)

        if agent_session_id:
            logger.info(f"[YZJ] Stop command: interrupting {agent_session_id}")
            success = await self.session_service.interrupt(agent_session_id)

            if success:
                await self.message_sender.send_text(
                    yzj_token, operator_openid, "✅ 已停止当前任务"
                )
                logger.info(f"[YZJ] Session interrupted: {agent_session_id}")
            else:
                await self.message_sender.send_text(
                    yzj_token, operator_openid, "⚠️ 停止失败，会话可能已结束"
                )
                logger.warning(f"[YZJ] Failed to interrupt: {agent_session_id}")
        else:
            await self.message_sender.send_text(
                yzj_token, operator_openid, "当前没有正在运行的任务"
            )
            logger.info(f"[YZJ] No active session to interrupt")

    def _clean_content(self, content: str) -> str:
        """清理消息内容（去除 @提及）

        Args:
            content: 原始消息内容

        Returns:
            清理后的消息内容
        """
        cleaned = re.sub(r'@\S+\s*', '', content)
        return cleaned.strip()

    def _is_stop_command(self, content: str) -> bool:
        """判断是否为停止命令

        Args:
            content: 消息内容

        Returns:
            是否为停止命令
        """
        cleaned = self._clean_content(content)

        if len(cleaned) > self.MAX_STOP_COMMAND_LENGTH:
            return False

        cleaned_lower = cleaned.lower()
        return any(keyword in cleaned_lower for keyword in self.STOP_KEYWORDS)

    def _match_faq(self, content: str) -> Optional[str]:
        """匹配 FAQ，返回预定义答案

        Args:
            content: 消息内容

        Returns:
            如果匹配，返回预定义答案；否则返回 None
        """
        cleaned = self._clean_content(content)

        for faq_key, faq_answer in self.FAQ_MAP.items():
            if cleaned.lower() == faq_key.lower():
                logger.info(f"[YZJ] FAQ matched: '{cleaned}' -> '{faq_answer}'")
                return faq_answer

        return None

    def _format_question(self, question: dict, robot_name: Optional[str] = None) -> str:
        """将 AskUserQuestion 格式化为云之家可读的文本

        Args:
            question: 问题字典
            robot_name: 机器人名称（用于指引用户回复）

        Returns:
            格式化后的消息文本
        """
        question_text = question.get("question", "请选择")
        options = question.get("options", [])

        lines = [question_text, ""]

        for i, option in enumerate(options, 1):
            label = option.get("label", "")
            description = option.get("description", "")

            if description:
                lines.append(f"{i}. {label} - {description}")
            else:
                lines.append(f"{i}. {label}")

        return "\n".join(lines)

    def get_session_stats(self) -> dict:
        """获取会话统计信息（委托给 SessionMapper）

        Returns:
            统计信息字典
        """
        return self.session_mapper.get_stats()
