"""Claude SDK streaming response processor."""

import logging
from typing import AsyncGenerator, Optional
from claude_agent_sdk import (
    ClaudeSDKClient,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock
)

from api.models.requests import QueryRequest
from api.utils import format_sse_message, extract_todos_from_tool
from api.utils.sdk_logger import SDKLogger

logger = logging.getLogger(__name__)


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
        session_service=None
    ):
        """
        Args:
            client: Claude SDK client
            request: Query request
            session_service: Session service (optional, dependency injection)
        """
        self.client = client
        self.request = request
        self.session_service = session_service
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
        """发送 session_created 事件（消除重复）

        Args:
            session_id: 会话 ID

        Yields:
            SSE 格式的 session_created 消息
        """
        if not self.session_id_sent:
            yield format_sse_message("session_created", {"session_id": session_id})
            self.session_id_sent = True

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

                # Emit session created event
                async for sse_msg in self._emit_session_created(self.actual_session_id):
                    yield sse_msg

                # Register session
                await self._ensure_session_registered(self.actual_session_id)

    async def _handle_assistant_message(self, msg: AssistantMessage) -> AsyncGenerator[dict, None]:
        """Handle assistant message."""
        for block in msg.content:
            if isinstance(block, TextBlock):
                self.sdk_logger.log_text_block(block)
                yield format_sse_message("assistant_message", block.text)

            elif isinstance(block, ToolUseBlock):
                self.sdk_logger.log_tool_use(block)

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
                        if questions:
                            logger.info(f"[AskUserQuestion] Emitting {len(questions)} question(s)")
                            yield format_sse_message("ask_user_question", {
                                "questions": questions
                            })

    async def _handle_result_message(self, msg: ResultMessage) -> AsyncGenerator[dict, None]:
        """Handle result message."""
        self.actual_session_id = msg.session_id

        # Send session_created (fallback)
        if not self.request.session_id and not self.session_id_sent:
            # Emit session created event
            async for sse_msg in self._emit_session_created(msg.session_id):
                yield sse_msg

            # Register session (fallback)
            await self._ensure_session_registered(msg.session_id)

        # Send final result with result field
        result_data = {
            "session_id": msg.session_id,
            "duration_ms": msg.duration_ms,
            "is_error": msg.is_error,
            "num_turns": msg.num_turns
        }

        # Include result field if present (SDK final output)
        if msg.result:
            result_data["result"] = msg.result

        yield format_sse_message("result", result_data)

        # Log result message with enhanced formatting
        self.sdk_logger.log_result_message(msg)
