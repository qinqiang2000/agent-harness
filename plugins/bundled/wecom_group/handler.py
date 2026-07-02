"""企业微信群机器人消息处理器."""

import json
import logging
from typing import Optional

from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.sdk_pool import get_cache
from api.services.session_service import SessionService
from api.utils.perf_timer import PerfTimer

from plugins.bundled.wecom_group.message_sender import WecomGroupMessageSender
from plugins.bundled.wecom_group.models import WecomGroupMessage

logger = logging.getLogger(__name__)

STOP_KEYWORDS = ["停止", "stop", "取消", "cancel"]
MAX_STOP_COMMAND_LENGTH = 10
RESET_COMMAND = "/clear"


class WecomGroupHandler:
    """企业微信群机器人消息处理器."""

    def __init__(
        self,
        agent_service: AgentService,
        session_service: SessionService,
        message_sender: WecomGroupMessageSender,
        config: dict,
    ):
        self.agent_service = agent_service
        self.session_service = session_service
        self.message_sender = message_sender
        self.default_skill = config.get("default_skill", "")
        session_timeout = config.get("session_timeout", 3600)
        self.session_mapper = PluginSessionMapper(
            timeout_seconds=session_timeout,
            channel_id="wecom_group",
        )

    async def process_message(self, msg: WecomGroupMessage, skill: Optional[str] = None):
        """处理群机器人消息（后台任务）."""
        user_id = msg.from_user_name
        session_key = f"{msg.chat_id}:{user_id}" if msg.chat_id else user_id
        content = (msg.content or "").strip()
        effective_skill = skill or self.default_skill
        response_url = msg.response_url or ""
        webhook_url = msg.webhook_url or ""

        logger.info(
            f"[WeComGroup] Processing: user={user_id}, chat={msg.chat_id}, "
            f"type={msg.msg_type}, content={content[:50]!r}"
        )

        try:
            self.session_mapper.cleanup_expired()

            if msg.msg_type != "text":
                await self.message_sender.send_text(
                    f"<@{user_id}> 暂时只支持文字消息，请发送文字内容。",
                    response_url=response_url,
                    webhook_url=webhook_url,
                )
                return

            if not content:
                return

            if content == RESET_COMMAND:
                self.session_mapper.remove(session_key)
                await self.message_sender.send_text(
                    f"<@{user_id}> ✅ 会话已重置，下次提问将开启新对话。",
                    response_url=response_url,
                    webhook_url=webhook_url,
                )
                return

            if self._is_stop_command(content):
                await self._handle_stop_command(user_id, session_key, response_url, webhook_url)
                return

            agent_session_id = self.session_mapper.get_or_create(session_key)
            prompt = content
            if agent_session_id:
                pending_questions = self.session_mapper.get_and_clear_pending_questions(session_key)
                if pending_questions:
                    prompt = f"用户回答: {content}\n请根据用户的回答继续处理。"

            request = QueryRequest(
                prompt=prompt,
                skill=effective_skill,
                tenant_id="wecom_group",
                language="中文",
                session_id=agent_session_id,
            )

            await self._process_agent_stream(request, user_id, session_key, response_url, webhook_url)

        except Exception as e:
            logger.error(f"[WeComGroup] Error processing message: {e}", exc_info=True)
            await self.message_sender.send_text(
                f"<@{user_id}> 抱歉，处理消息时出现错误，请稍后再试。",
                response_url=response_url,
                webhook_url=webhook_url,
            )

    async def _process_agent_stream(
        self,
        request: QueryRequest,
        user_id: str,
        session_key: str,
        response_url: str,
        webhook_url: str,
    ):
        """消费 agent 事件流并回复到群."""
        agent_session_id = request.session_id
        answered = False
        perf = PerfTimer(request_id=user_id[:8])
        perf.attach()

        if agent_session_id:
            self.session_mapper.update_activity(session_key, agent_session_id)

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                agent_session_id = new_session_id
                self.session_mapper.update_activity(session_key, new_session_id)

            elif event_type == "transfer_human":
                data = json.loads(event["data"])
                reason = data.get("reason", "正在为您转接人工客服，请稍候。")
                await self.message_sender.send_text(
                    f"<@{user_id}> {reason}",
                    response_url=response_url,
                    webhook_url=webhook_url,
                )
                answered = True
                t = PerfTimer.current()
                if t:
                    t.done()
                break

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])
                self.session_mapper.set_pending_questions(session_key, questions)
                if agent_session_id:
                    await self.session_service.interrupt(agent_session_id)
                    cache = get_cache()
                    if cache:
                        await cache.release(agent_session_id, healthy=False)
                for question in questions:
                    await self.message_sender.send_text(
                        f"<@{user_id}> {self._format_question(question)}",
                        response_url=response_url,
                        webhook_url=webhook_url,
                    )
                answered = True
                t = PerfTimer.current()
                if t:
                    t.done()
                break

            elif event_type == "result":
                result_data = json.loads(event.get("data", "{}"))
                answer = result_data.get("result", "")
                if answer:
                    await self.message_sender.send_text(
                        f"<@{user_id}> {answer}",
                        response_url=response_url,
                        webhook_url=webhook_url,
                    )
                    answered = True
                t = PerfTimer.current()
                if t:
                    t.done()

            elif event_type == "error":
                error_data = json.loads(event.get("data", "{}"))
                await self.message_sender.send_text(
                    f"<@{user_id}> 抱歉，处理时出现错误：{error_data.get('message', '未知错误')}",
                    response_url=response_url,
                    webhook_url=webhook_url,
                )
                answered = True
                t = PerfTimer.current()
                if t:
                    t.done()

        if not answered:
            await self.message_sender.send_text(
                f"<@{user_id}> 抱歉，未能获取到答案，请稍后再试。",
                response_url=response_url,
                webhook_url=webhook_url,
            )
            t = PerfTimer.current()
            if t:
                t.done()

    async def _handle_stop_command(
        self, user_id: str, session_key: str, response_url: str, webhook_url: str
    ):
        agent_session_id = self.session_mapper.get_or_create(session_key)
        if agent_session_id:
            success = await self.session_service.interrupt(agent_session_id)
            if success:
                await self.message_sender.send_text(
                    f"<@{user_id}> ✅ 已停止当前任务。",
                    response_url=response_url,
                    webhook_url=webhook_url,
                )
            else:
                await self.message_sender.send_text(
                    f"<@{user_id}> ⚠️ 停止失败，会话可能已结束。",
                    response_url=response_url,
                    webhook_url=webhook_url,
                )
        else:
            await self.message_sender.send_text(
                f"<@{user_id}> 当前没有正运行的任务。",
                response_url=response_url,
                webhook_url=webhook_url,
            )

    def _is_stop_command(self, content: str) -> bool:
        if len(content) > MAX_STOP_COMMAND_LENGTH:
            return False
        return any(kw in content.lower() for kw in STOP_KEYWORDS)

    def _format_question(self, question: dict) -> str:
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
        return self.session_mapper.get_stats()
