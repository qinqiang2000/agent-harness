"""Claude SDK streaming response processor."""

import json
import logging
import re
from typing import AsyncGenerator
from claude_agent_sdk import (
    ClaudeSDKClient,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock
)

from api.models.requests import QueryRequest
from api.utils import format_sse_message, extract_todos_from_tool, redact, should_redact
from api.utils.sdk_logger import SDKLogger
from api.utils.perf_timer import PerfTimer
logger = logging.getLogger(__name__)


_TRANSFER_PATTERN = re.compile(r'\[TRANSFER:([^\]]*)\]\s*')


class StreamProcessor:
    """
    Streaming response processor for Claude SDK.

    Responsibilities:
    - Process Claude SDK message stream
    - Manage session registration/unregistration
    - Extract and emit todos
    - Format SSE messages
    """

    def __init__(
        self,
        client: ClaudeSDKClient,
        request: QueryRequest,
        session_service=None,
        on_session_id=None,
    ):
        """
        Args:
            client: Claude SDK client
            request: Query request
            session_service: Session service (optional, dependency injection)
            on_session_id: async callable(session_id) — 新会话拿到真实 session_id 时调用
        """
        self.client = client
        self.request = request
        self.session_service = session_service
        self.on_session_id = on_session_id
        self.session_id_sent = False
        self.actual_session_id = request.session_id
        self.first_message_received = False
        self.session_registered = False
        self.sdk_logger = SDKLogger(logger)  # Enhanced SDK message logger

    async def _ensure_session_registered(self, session_id: str):
        """确保会话已注册（消除重复逻辑）

        Args:
            session_id: 会话 ID
        """
        if not self.session_registered and self.session_service:
            await self.session_service.register(session_id, self.client)
            self.session_registered = True

    async def _emit_session_created(self, session_id: str) -> AsyncGenerator[dict, None]:
        """发送 session_created 事件，同时触发 on_session_id 回调（两者原子绑定）。"""
        if not self.session_id_sent:
            self.session_id_sent = True
            if self.on_session_id:
                await self.on_session_id(session_id)
            yield format_sse_message("session_created", {"session_id": session_id})

    async def process(self) -> AsyncGenerator[dict, None]:
        """
        Process message stream.

        Yields:
            SSE formatted message dictionaries
        """
        # If resuming session, register immediately
        if self.request.session_id:
            await self._ensure_session_registered(self.request.session_id)

        try:
            async for msg in self.client.receive_response():
                if not self.first_message_received:
                    self.first_message_received = True
                    # 节点 4：首条消息到达
                    t = PerfTimer.current()
                    if t:
                        t.mark("FIRST_MESSAGE")

                # Handle different message types
                if isinstance(msg, SystemMessage):
                    async for sse_msg in self._handle_system_message(msg):
                        yield sse_msg

                elif isinstance(msg, AssistantMessage):
                    async for sse_msg in self._handle_assistant_message(msg):
                        yield sse_msg

                elif isinstance(msg, ResultMessage):
                    async for sse_msg in self._handle_result_message(msg):
                        yield sse_msg

            if not self.first_message_received:
                logger.warning("No messages received from Claude SDK")

        finally:
            # Clean up session
            if self.session_registered and self.actual_session_id and self.session_service:
                await self.session_service.unregister(self.actual_session_id)

    async def _handle_system_message(self, msg: SystemMessage) -> AsyncGenerator[dict, None]:
        """Handle system message."""
        self.sdk_logger.log_system_message(msg)

        if (hasattr(msg, 'subtype') and msg.subtype == 'init'
            and not self.request.session_id and not self.session_id_sent):

            if isinstance(msg.data, dict) and 'session_id' in msg.data:
                self.actual_session_id = msg.data['session_id']

                # Emit session created event (also triggers on_session_id callback)
                async for sse_msg in self._emit_session_created(self.actual_session_id):
                    yield sse_msg

                # Register session
                await self._ensure_session_registered(self.actual_session_id)

    async def _handle_assistant_message(self, msg: AssistantMessage) -> AsyncGenerator[dict, None]:
        """Handle assistant message."""
        tool_blocks = [b for b in msg.content if isinstance(b, ToolUseBlock)]
        if len(tool_blocks) > 1:
            tool_names = [b.name for b in tool_blocks]
            logger.info(f"[Turn] {len(tool_blocks)} parallel tool calls: {tool_names}")
        for block in msg.content:
            if isinstance(block, TextBlock):
                self.sdk_logger.log_text_block(block)
                if block.text and block.text.strip() and block.text.strip() != "(empty)":
                    text = redact(block.text) if should_redact(self.request.skill, self.request.tenant_id) else block.text
                    yield format_sse_message("assistant_message", text)

            elif isinstance(block, ToolUseBlock):
                self.sdk_logger.log_tool_use(block)
                yield format_sse_message("tool_use", {"name": block.name, "input": block.input})

                # Extract and emit todos
                if block.name == "TodoWrite":
                    todos = extract_todos_from_tool(block)
                    if todos:
                        logger.info(f"[TodoWrite] Emitting {len(todos)} todos")
                        yield format_sse_message("todos_update", {"todos": todos})

                # Handle AskUserQuestion
                elif block.name == "AskUserQuestion":
                    if isinstance(block.input, dict):
                        questions = block.input.get("questions", [])
                        if isinstance(questions, str):
                            try:
                                questions = json.loads(questions)
                            except (json.JSONDecodeError, ValueError):
                                logger.error(f"[AskUserQuestion] Failed to parse questions string: {questions[:100]}")
                                yield format_sse_message("assistant_message", "抱歉，agent异常，请稍后再试。")
                                questions = []
                        if questions and isinstance(questions, list):
                            logger.info(f"[AskUserQuestion] Emitting {len(questions)} question(s)")
                            yield format_sse_message("ask_user_question", {
                                "questions": questions
                            })

    async def _handle_result_message(self, msg: ResultMessage) -> AsyncGenerator[dict, None]:
        """Handle result message."""
        self.actual_session_id = msg.session_id

        # Send session_created (fallback)
        if not self.request.session_id and not self.session_id_sent:
            # Emit session created event (also triggers on_session_id callback)
            async for sse_msg in self._emit_session_created(msg.session_id):
                yield sse_msg

            # Register session (fallback)
            await self._ensure_session_registered(msg.session_id)

        # 节点 5：流结束
        t = PerfTimer.current()
        if t:
            t.mark("STREAM_DONE")

        # Send final result with result field
        result_data = {
            "session_id": msg.session_id,
            "duration_ms": msg.duration_ms,
            "is_error": msg.is_error,
            "num_turns": msg.num_turns
        }

        # Include result field if present (SDK final output)
        if msg.result:
            m = _TRANSFER_PATTERN.search(msg.result)
            if m:
                group_name = m.group(1).strip()
                reason = msg.result[m.end():].strip() or msg.result[:m.start()].strip()
                logger.info(f"[Transfer] Detected transfer signal: group={group_name}")
                yield format_sse_message("transfer_human", {"group": group_name, "reason": reason})
                result_data["result"] = reason
            else:
                result_data["result"] = msg.result

        yield format_sse_message("result", result_data)

        # Log result message with enhanced formatting
        self.sdk_logger.log_result_message(msg)

        # 节点 6：全部完成，打印 SDK 统计的 API 耗时供对比
        t = PerfTimer.current()
        if t:
            t.mark(f"DONE (sdk_api={msg.duration_api_ms}ms turns={msg.num_turns})")
