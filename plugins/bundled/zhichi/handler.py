"""智齿消息处理器 - 主协调器."""

import json
import logging
import os
from typing import Optional


from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

from plugins.bundled.zhichi.message_sender import ZhichiMessageSender
from plugins.bundled.zhichi.models import ThirdAlgorithmReqVo

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
        message_sender: ZhichiMessageSender,
        config: dict,
    ):
        self.agent_service = agent_service
        self.session_service = session_service
        self.message_sender = message_sender
        self.default_skill = config.get("default_skill", "customer-service")
        session_timeout = config.get("session_timeout", 3600)

        self.session_mapper = PluginSessionMapper(
            timeout_seconds=session_timeout,
            channel_id="zhichi",
        )
        self._transfer_counts: dict[str, int] = {}

    async def process_message(
        self,
        req: ThirdAlgorithmReqVo,
        skill: Optional[str] = None,
    ) -> None:
        """处理智齿消息."""
        cid = req.ai_agent_cid
        effective_skill = skill or self.default_skill
        logger.info(
            f"[Zhichi] Processing: cid={cid}, skill={effective_skill}, "
            f"question={req.question[:50]}..."
        )

        runtimeid = req.runtimeid

        try:
            # 0. 清理过期会话
            self.session_mapper.cleanup_expired()

            # 1. 检测停止命令
            if self._is_stop_command(req.question):
                await self._handle_stop_command(cid, req.req_stream)
                return

            # 2. 获取或创建 agent session
            agent_session_id = self.session_mapper.get_or_create(cid)
            if agent_session_id:
                logger.info(f"[Zhichi] Resuming agent session: {agent_session_id}")
            else:
                logger.info(f"[Zhichi] Creating new agent session for cid: {cid}")

            # 3. 构建 prompt（检查是否有待回答的问题）
            prompt = req.question
            if agent_session_id:
                pending_questions = self.session_mapper.get_and_clear_pending_questions(cid)
                if pending_questions:
                    prompt = self._build_answer_prompt(req.question, pending_questions)
                    logger.info("[Zhichi] Enriched prompt with pending question context")

            # 4. 构建请求
            request = QueryRequest(
                prompt=prompt,
                skill=effective_skill,
                tenant_id="zhichi",
                language="中文",
                session_id=agent_session_id,
            )

            # 5. 处理 Agent 消息流
            await self._process_agent_stream(request, cid, req.req_stream, runtimeid)

        except Exception as e:
            logger.error(f"[Zhichi] Error processing message: {e}", exc_info=True)
            await self.message_sender.send_error_answer(cid, req_stream=req.req_stream, runtimeid=runtimeid)

    async def _process_agent_stream(
        self,
        request: QueryRequest,
        cid: str,
        req_stream: bool,
        runtimeid: Optional[str] = None,
    ) -> None:
        """处理 Agent 消息流."""
        agent_session_id = request.session_id
        answer_sent = False

        if agent_session_id:
            self.session_mapper.update_activity(cid, agent_session_id)

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                agent_session_id = new_session_id
                self.session_mapper.update_activity(cid, new_session_id)
                logger.info(f"[Zhichi] Session mapping: {cid} -> {new_session_id}")

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])

                # 将问题发回智齿，用户在智齿界面看到
                for question in questions:
                    question_text = self._format_question(question)
                    await self.message_sender.send_answer(
                        ai_agent_cid=cid,
                        llm_answer=question_text,
                        req_stream=req_stream,
                        runtimeid=runtimeid,
                        message_end=False,
                    )
                    answer_sent = True

                # 保存待回答的问题，下次消息到来时携带上下文
                self.session_mapper.set_pending_questions(cid, questions)

                # 中断 SDK 会话，等待用户回复
                if agent_session_id:
                    await self.session_service.interrupt(agent_session_id)
                logger.info(f"[Zhichi] Session paused awaiting user reply: {agent_session_id}")
                break

            elif event_type == "result":
                result_data = json.loads(event.get("data", "{}"))
                final_result = result_data.get("result", "")

                if final_result:
                    await self.message_sender.send_answer(
                        ai_agent_cid=cid,
                        llm_answer=final_result,
                        req_stream=req_stream,
                        runtimeid=runtimeid,
                    )
                    answer_sent = True
                    logger.info(
                        f"[Zhichi] Result sent: cid={cid}, "
                        f"duration={result_data.get('duration_ms')}ms, "
                        f"turns={result_data.get('num_turns')}"
                    )
                else:
                    logger.error("[Zhichi] Empty result content")

            elif event_type == "error":
                error_data = json.loads(event.get("data", "{}"))
                error_msg = error_data.get("message", "未知错误")
                logger.error(f"[Zhichi] Agent error: {error_msg}")
                await self.message_sender.send_error_answer(
                    cid,
                    error_text=f"抱歉，处理时出现错误：{error_msg}",
                    req_stream=req_stream,
                    runtimeid=runtimeid,
                )
                answer_sent = True

        if not answer_sent:
            logger.warning(f"[Zhichi] No answer sent for cid={cid}, sending fallback")
            await self.message_sender.send_error_answer(cid, req_stream=req_stream, runtimeid=runtimeid)

    async def _handle_stop_command(self, cid: str, req_stream: bool) -> None:
        """处理停止命令."""
        agent_session_id = self.session_mapper.get_or_create(cid)
        if agent_session_id:
            success = await self.session_service.interrupt(agent_session_id)
            if success:
                await self.message_sender.send_answer(cid, "已停止当前任务", req_stream=req_stream)
                logger.info(f"[Zhichi] Session interrupted: {agent_session_id}")
            else:
                await self.message_sender.send_answer(cid, "停止失败，会话可能已结束", req_stream=req_stream)
        else:
            await self.message_sender.send_answer(cid, "当前没有正在运行的任务", req_stream=req_stream)

    def _is_stop_command(self, content: str) -> bool:
        if len(content) > MAX_STOP_COMMAND_LENGTH:
            return False
        lower = content.lower().strip()
        return any(kw in lower for kw in STOP_KEYWORDS)

    def _build_answer_prompt(self, user_reply: str, questions: list) -> str:
        """构建携带上下文的 prompt."""
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

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                self.session_mapper.update_activity(cid, new_session_id)

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])
                self.session_mapper.set_pending_questions(cid, questions)
                if questions:
                    answer = self._format_question(questions[0])
                    transfer, group_name = await self._check_transfer(cid, answer)
                    yield answer, True, transfer, group_name
                return

            elif event_type == "result":
                result_data = json.loads(event.get("data", "{}"))
                answer = result_data.get("result", "抱歉，处理您的问题时出现错误，请稍后再试。")
                transfer, group_name = await self._check_transfer(cid, answer)
                yield answer, True, transfer, group_name
                return

            elif event_type == "error":
                error_data = json.loads(event.get("data", "{}"))
                yield f"抱歉，处理时出现错误：{error_data.get('message', '未知错误')}", True, False, ""
                return

        yield "抱歉，处理您的问题时出现错误，请稍后再试。", True, False, ""

    async def get_answer(self, req: ThirdAlgorithmReqVo) -> tuple[str, bool, str]:
        """同步处理消息，返回 (llm_answer, third_transfer_flag, group_name)."""
        async for llm_answer, _, transfer, group_name in self.stream_answer(req):
            return llm_answer, transfer, group_name
        return "抱歉，处理您的问题时出现错误，请稍后再试。", False, ""

    async def _check_transfer(self, cid: str, answer: str) -> tuple[bool, str]:
        """用 AI 判断答案是否建议转人工，累计 2 次则触发，同时返回目标技能组名."""
        should_transfer, group_name = await self._should_transfer_ai(answer)
        if not should_transfer:
            return False, ""
        self._transfer_counts[cid] = self._transfer_counts.get(cid, 0) + 1
        count = self._transfer_counts[cid]
        logger.info(f"[Zhichi] Transfer intent detected: cid={cid}, count={count}, group={group_name}")
        if count >= 2:
            self._transfer_counts.pop(cid, None)
            logger.info(f"[Zhichi] Transfer to human triggered: cid={cid}, group={group_name}")
            return True, group_name
        return False, ""

    async def _should_transfer_ai(self, answer: str) -> tuple[bool, str]:
        """调用 LLM 判断回复是否建议转人工，组名暂时固定返回"测试技能组"."""
        return False, "测试技能组"

    def get_session_stats(self) -> dict:
        """获取会话统计信息."""
        return self.session_mapper.get_stats()
