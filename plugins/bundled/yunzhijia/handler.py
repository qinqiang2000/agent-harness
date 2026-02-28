"""云之家消息处理器 - 主协调器."""

import json
import logging
import re
from typing import Optional

from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

from plugins.bundled.yunzhijia.card_builder import YunzhijiaCardBuilder
from plugins.bundled.yunzhijia.message_sender import YunzhijiaMessageSender
from plugins.bundled.yunzhijia.models import YZJRobotMsg

logger = logging.getLogger(__name__)


class YunzhijiaHandler:
    """云之家消息处理器"""

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

    def __init__(
        self,
        agent_service: AgentService,
        session_service: SessionService,
        config: dict,
    ):
        self.agent_service = agent_service
        self.session_service = session_service

        # Read config with defaults
        self.default_skill = config.get("default_skill", "customer-service")
        session_timeout = config.get("session_timeout", 3600)
        card_template_id = config.get("card_template_id", "")
        max_img_per_card = config.get("max_img_per_card", 3)
        self.service_base_url = config.get("service_base_url", "http://localhost:9090")
        self.verbose = config.get("verbose", False)

        # Initialize sub-components
        self.session_mapper = PluginSessionMapper(
            timeout_seconds=session_timeout,
            channel_id="yunzhijia",
        )
        self.message_sender = YunzhijiaMessageSender(self.NOTIFY_URL_TEMPLATE)
        self.card_builder = YunzhijiaCardBuilder(
            template_id=card_template_id,
            max_img_per_card=max_img_per_card,
        )

    async def process_message(self, msg: YZJRobotMsg, yzj_token: str, skill: Optional[str] = None):
        """处理云之家消息"""
        yzj_session_id = msg.sessionId
        effective_skill = skill or self.default_skill
        logger.info(f"[YZJ] Received message: {msg.model_dump()}")
        logger.info(f"[YZJ] Processing: session={yzj_session_id}, skill={effective_skill}, content={msg.content[:50]}...")

        try:
            # 0. 清理过期会话
            self.session_mapper.cleanup_expired()

            # 1. 检查 FAQ
            faq_answer = self._match_faq(msg.content)
            if faq_answer:
                await self.message_sender.send_text(yzj_token, msg.operatorOpenid, faq_answer)
                logger.info(f"[YZJ] FAQ response sent for session: {yzj_session_id}")
                return

            # 2. 检测停止命令
            if self._is_stop_command(msg.content):
                await self._handle_stop_command(yzj_token, msg.operatorOpenid, yzj_session_id)
                return

            # 3. 获取或创建 agent session
            agent_session_id = self.session_mapper.get_or_create(yzj_session_id)
            if agent_session_id:
                logger.info(f"[YZJ] Resuming agent session: {agent_session_id}")
            else:
                logger.info(f"[YZJ] Creating new agent session for: {yzj_session_id}")

            # 4. 获取机器人名称
            robot_name = f"@{msg.robotName}" if msg.robotName else "@机器人"

            # 5. 清理消息内容
            cleaned_content = self._clean_content(msg.content)

            # 6. 构建请求（检查是否有待回答的问题）
            prompt = cleaned_content
            if agent_session_id:
                pending_questions = self.session_mapper.get_and_clear_pending_questions(yzj_session_id)
                if pending_questions:
                    prompt = self._build_answer_prompt(cleaned_content, pending_questions)
                    logger.info(f"[YZJ] Enriched prompt with pending question context")

            request = QueryRequest(
                prompt=prompt,
                skill=effective_skill,
                tenant_id="yzj",
                language="中文",
                session_id=agent_session_id,
            )

            # 7. 处理消息流
            await self._process_agent_stream(
                request, yzj_token, msg.operatorOpenid,
                yzj_session_id, robot_name,
            )

        except Exception as e:
            logger.error(f"[YZJ] Error processing message: {e}", exc_info=True)
            await self.message_sender.send_text(
                yzj_token,
                msg.operatorOpenid,
                "抱歉，处理消息时出现错误，请稍后再试。",
            )

    async def _process_agent_stream(
        self,
        request: QueryRequest,
        yzj_token: str,
        operator_openid: str,
        yzj_session_id: str,
        robot_name: str,
    ):
        """处理 Agent 消息流"""
        message_count = 0
        agent_session_id = request.session_id

        # Resume session 时也要更新 last_active
        if agent_session_id:
            self.session_mapper.update_activity(yzj_session_id, agent_session_id)

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                agent_session_id = new_session_id
                self.session_mapper.update_activity(yzj_session_id, new_session_id)
                logger.info(f"[YZJ] Session mapping: {yzj_session_id} -> {new_session_id}")

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])

                # Store questions for resume context
                self.session_mapper.set_pending_questions(yzj_session_id, questions)

                for question in questions:
                    formatted_message = self._format_question(question, robot_name)
                    message_count += 1
                    await self.message_sender.send_text(
                        yzj_token, operator_openid, formatted_message,
                    )
                    logger.info(f"[YZJ] Sent question #{message_count}")

                # 中断 SDK 会话，等待用户回复
                if agent_session_id:
                    await self.session_service.interrupt(agent_session_id)
                logger.info(f"[YZJ] Session paused awaiting user reply: {agent_session_id}")
                break  # 不再处理后续事件

            elif event_type == "result":
                result_data = json.loads(event.get("data", "{}"))

                if result_data.get("result"):
                    final_result = result_data["result"]
                    reply = f"{final_result}\n\n👉 如还有疑问，可直接回复本消息"
                    await self.message_sender.send_with_images(
                        yzj_token, operator_openid, reply,
                        self.service_base_url, self.card_builder,
                    )
                    message_count += 1
                    logger.info(f"[YZJ] Sent final result")
                else:
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
                    f"抱歉，处理时出现错误：{error_data.get('message', '未知错误')}",
                )

        if message_count == 0:
            await self.message_sender.send_text(
                yzj_token, operator_openid,
                "抱歉，未能获取到答案，请稍后再试。",
            )

    async def _handle_stop_command(
        self,
        yzj_token: str,
        operator_openid: str,
        yzj_session_id: str,
    ):
        """处理停止命令"""
        agent_session_id = self.session_mapper.get_or_create(yzj_session_id)

        if agent_session_id:
            logger.info(f"[YZJ] Stop command: interrupting {agent_session_id}")
            success = await self.session_service.interrupt(agent_session_id)

            if success:
                await self.message_sender.send_text(
                    yzj_token, operator_openid, "✅ 已停止当前任务",
                )
                logger.info(f"[YZJ] Session interrupted: {agent_session_id}")
            else:
                await self.message_sender.send_text(
                    yzj_token, operator_openid, "⚠️ 停止失败，会话可能已结束",
                )
                logger.warning(f"[YZJ] Failed to interrupt: {agent_session_id}")
        else:
            await self.message_sender.send_text(
                yzj_token, operator_openid, "当前没有正在运行的任务",
            )
            logger.info(f"[YZJ] No active session to interrupt")

    def _clean_content(self, content: str) -> str:
        """清理消息内容（去除 @提及）"""
        cleaned = re.sub(r'@\S+\s*', '', content)
        return cleaned.strip()

    def _is_stop_command(self, content: str) -> bool:
        """判断是否为停止命令"""
        cleaned = self._clean_content(content)
        if len(cleaned) > self.MAX_STOP_COMMAND_LENGTH:
            return False
        cleaned_lower = cleaned.lower()
        return any(keyword in cleaned_lower for keyword in self.STOP_KEYWORDS)

    def _match_faq(self, content: str) -> Optional[str]:
        """匹配 FAQ，返回预定义答案"""
        cleaned = self._clean_content(content)
        for faq_key, faq_answer in self.FAQ_MAP.items():
            if cleaned.lower() == faq_key.lower():
                logger.info(f"[YZJ] FAQ matched: '{cleaned}' -> '{faq_answer}'")
                return faq_answer
        return None

    def _build_answer_prompt(self, user_reply: str, questions: list) -> str:
        """Build enriched prompt that includes the question context for the user's reply.

        Args:
            user_reply: User's raw reply (e.g. "2")
            questions: Original AskUserQuestion questions list

        Returns:
            Enriched prompt with question context
        """
        parts = []
        for question in questions:
            question_text = question.get("question", "")
            options = question.get("options", [])

            parts.append(f"上一轮你使用 AskUserQuestion 向用户提问: {question_text}")
            if options:
                parts.append("选项:")
                for i, option in enumerate(options, 1):
                    label = option.get("label", "")
                    description = option.get("description", "")
                    if description:
                        parts.append(f"  {i}. {label} - {description}")
                    else:
                        parts.append(f"  {i}. {label}")

        parts.append(f"\n用户回答: {user_reply}")
        parts.append("请根据用户的回答继续处理。")
        return "\n".join(parts)

    def _format_question(self, question: dict, robot_name: Optional[str] = None) -> str:
        """将 AskUserQuestion 格式化为云之家可读的文本"""
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
        """获取会话统计信息"""
        return self.session_mapper.get_stats()
