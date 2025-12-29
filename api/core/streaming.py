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

    async def process(self) -> AsyncGenerator[dict, None]:
        """
        Process message stream.

        Yields:
            SSE formatted message dictionaries
        """
        # If resuming session, register immediately
        if self.request.session_id and self.session_service:
            await self.session_service.register(self.request.session_id, self.client)
            self.session_registered = True

        try:
            async for msg in self.client.receive_response():
                if not self.first_message_received:
                    self.first_message_received = True
                    logger.info(f"First message received: {type(msg).__name__}")

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
        logger.debug(f"SystemMessage: subtype={getattr(msg, 'subtype', None)}")

        if (hasattr(msg, 'subtype') and msg.subtype == 'init'
            and not self.request.session_id and not self.session_id_sent):

            if isinstance(msg.data, dict) and 'session_id' in msg.data:
                self.actual_session_id = msg.data['session_id']
                yield format_sse_message("session_created", {
                    "session_id": self.actual_session_id
                })
                self.session_id_sent = True
                logger.info(f"Created new session: {self.actual_session_id}")

                # Register session
                if self.session_service:
                    await self.session_service.register(
                        self.actual_session_id,
                        self.client
                    )
                    self.session_registered = True

    async def _handle_assistant_message(self, msg: AssistantMessage) -> AsyncGenerator[dict, None]:
        """Handle assistant message."""
        for block in msg.content:
            if isinstance(block, TextBlock):
                logger.info(f"[Agent] {block.text}")
                yield format_sse_message("assistant_message", block.text)

            elif isinstance(block, ToolUseBlock):
                logger.info(f"[Tool] {block.name} - Input: {block.input}")

                # Extract and emit todos
                if block.name == "TodoWrite":
                    todos = extract_todos_from_tool(block)
                    if todos:
                        logger.info(f"[TodoWrite] Emitting {len(todos)} todos")
                        yield format_sse_message("todos_update", {"todos": todos})

    async def _handle_result_message(self, msg: ResultMessage) -> AsyncGenerator[dict, None]:
        """Handle result message."""
        self.actual_session_id = msg.session_id

        # Send session_created (fallback)
        if not self.request.session_id and not self.session_id_sent:
            yield format_sse_message("session_created", {
                "session_id": msg.session_id
            })
            self.session_id_sent = True
            logger.info(f"Created new session (from result): {msg.session_id}")

            # Register session (fallback)
            if not self.session_registered and self.session_service:
                await self.session_service.register(msg.session_id, self.client)
                self.session_registered = True

        # Send final result
        yield format_sse_message("result", {
            "session_id": msg.session_id,
            "duration_ms": msg.duration_ms,
            "is_error": msg.is_error,
            "num_turns": msg.num_turns
        })

        logger.info(
            f"Session {msg.session_id} completed: "
            f"duration={msg.duration_ms}ms, turns={msg.num_turns}, error={msg.is_error}"
        )
