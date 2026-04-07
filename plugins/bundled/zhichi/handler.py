"""智齿消息处理器 - 主协调器."""

import json
import logging
from typing import Optional

from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.session_service import SessionService
from api.utils.perf_timer import PerfTimer

from plugins.bundled.zhichi.models import ThirdAlgorithmReqVo

# from plugins.bundled.zhichi.message_sender import ZhichiMessageSender

logger = logging.getLogger(__name__)

# 停止命令关键词
STOP_KEYWORDS = ["停止", "stop", "取消", "cancel"]
MAX_STOP_COMMAND_LENGTH = 10


class ZhichiHandler:
    """智齿消息处理器."""

    def __init__(
        self,
        agent_service: AgentService,
        session_service: SessionService,
        config: dict,
        # message_sender: ZhichiMessageSender,
    ):
        self.agent_service = agent_service
        self.session_service = session_service
        # self.message_sender = message_sender
        self.default_skill = config.get("default_skill", "customer-service")
        self.transfer_group = config.get("transfer_group", "")
        session_timeout = config.get("session_timeout", 3600)

        self.session_mapper = PluginSessionMapper(
            timeout_seconds=session_timeout,
            channel_id="zhichi",
        )

    # async def process_message(self, req: ThirdAlgorithmReqVo, skill=None):
    #     """异步回调模式 - 已停用，智齿无回调接口."""
    #     ...

    # async def _process_agent_stream(self, request, cid, req_stream, runtimeid=None):
    #     """异步回调模式 - 已停用."""
    #     ...

    # async def _handle_stop_command(self, cid, req_stream):
    #     """异步回调模式 - 已停用."""
    #     ...

    # def _is_stop_command(self, content):
    #     ...

    def _build_answer_prompt(self, user_reply: str, questions: list) -> str:
        """构建携带上下文的 prompt.

        Session 历史已包含 AskUserQuestion 调用记录，只需提供用户回答即可，
        避免重复问题文本导致 LLM 再次输出问题内容。
        """
        return f"用户回答: {user_reply}\n请根据用户的回答继续处理。"

    def _format_question(self, question: dict) -> str:
        """将 AskUserQuestion 格式化为纯文本."""
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

    async def stream_answer(self, req: ThirdAlgorithmReqVo):
        """流式处理消息，yield (llm_answer, message_end) 元组."""
        cid = req.ai_agent_cid
        self.session_mapper.cleanup_expired()
        perf = PerfTimer(request_id=cid[:8] if cid else None)
        perf.attach()

        agent_session_id = self.session_mapper.get_or_create(cid)
        prompt = req.question
        if agent_session_id:
            pending_questions = self.session_mapper.get_and_clear_pending_questions(cid)
            if pending_questions:
                prompt = self._build_answer_prompt(req.question, pending_questions)

        request = QueryRequest(
            prompt=prompt,
            skill=self.default_skill,
            tenant_id="zhichi",
            language="中文",
            session_id=agent_session_id,
        )

        answered = False

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                self.session_mapper.update_activity(cid, new_session_id)

            elif event_type == "transfer_human":
                data = json.loads(event["data"])
                group_name = self.transfer_group or data.get("group", "通用客服组")
                reason = data.get("reason", "正在为您转接人工客服，请稍候。")
                logger.info(f"[Zhichi] Transfer to human: group={group_name}")
                t = PerfTimer.current()
                if t:
                    t.done()
                answered = True
                yield reason, True, True, group_name
                return

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])
                self.session_mapper.set_pending_questions(cid, questions)
                t = PerfTimer.current()
                if t:
                    t.done()
                answered = True
                if questions:
                    answer = self._format_question(questions[0])
                    yield answer, True, False, ""
                return

            elif event_type == "result":
                result_data = json.loads(event.get("data", "{}"))
                answer = result_data.get("result", "抱歉，处理您的问题时出现错误，请稍后再试。")
                # 节点 6：智齿消息发送开始
                t = PerfTimer.current()
                if t:
                    t.mark("ZHICHI_SEND_START")
                answered = True
                yield answer, True, False, ""
                t = PerfTimer.current()
                if t:
                    t.done()
                # 不 return，让循环自然耗尽 process_query，
                # 确保其 finally 以 healthy=True 归还连接，实现多轮热复用。

            elif event_type == "error":
                error_data = json.loads(event.get("data", "{}"))
                t = PerfTimer.current()
                if t:
                    t.done()
                answered = True
                yield f"抱歉，处理时出现错误：{error_data.get('message', '未知错误')}", True, False, ""
                return

        if not answered:
            t = PerfTimer.current()
            if t:
                t.done()
            yield "抱歉，处理您的问题时出现错误，请稍后再试。", True, False, ""

    async def get_answer(self, req: ThirdAlgorithmReqVo) -> tuple[str, bool, str]:
        """同步处理消息，返回 (llm_answer, third_transfer_flag, group_name)."""
        async for llm_answer, _, transfer, group_name in self.stream_answer(req):
            return llm_answer, transfer, group_name
        return "抱歉，处理您的问题时出现错误，请稍后再试。", False, ""

    def get_session_stats(self) -> dict:
        """获取会话统计信息."""
        return self.session_mapper.get_stats()
