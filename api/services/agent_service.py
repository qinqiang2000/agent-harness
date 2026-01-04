"""Agent business logic service."""

import asyncio
import logging
from typing import Optional, AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from api.models.requests import QueryRequest
from api.core.streaming import StreamProcessor
from api.utils import build_initial_prompt, format_sse_message
from api.constants import AGENTS_ROOT

logger = logging.getLogger(__name__)


class AgentService:
    """
    Agent business logic service.

    Responsibilities:
    - Assemble prompts
    - Configure Claude SDK options
    - Coordinate streaming processing
    - Does not directly depend on session_manager (uses dependency injection)
    """

    def __init__(self, session_service=None):
        """
        Args:
            session_service: Session service (dependency injection, default None = not used)
        """
        self.session_service = session_service

    async def process_query(
        self,
        request: QueryRequest,
        context_file_path: Optional[str] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Process Agent query request and return SSE stream.

        Args:
            request: Query request
            context_file_path: Context file path

        Yields:
            SSE formatted messages
        """
        # Heartbeat
        yield format_sse_message("heartbeat", {"status": "connecting"})

        try:
            # Build prompt
            if request.session_id:
                prompt = request.prompt
                logger.info(f"Resuming session: {request.session_id}")
            else:
                prompt = build_initial_prompt(
                    tenant_id=request.tenant_id,
                    user_prompt=request.prompt,
                    skill=request.skill,
                    language=request.language,
                    context_file_path=context_file_path,
                    metadata=request.metadata,
                )
                logger.info(f"Starting new session")

            # Configure Claude SDK
            options = ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code"},
                setting_sources=["project"],
                allowed_tools=["Skill", "Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch"],
                resume=request.session_id,
                max_buffer_size=10 * 1024 * 1024,
                cwd=str(AGENTS_ROOT),
                add_dirs=[]
            )

            logger.info(f"Claude SDK config: cwd={AGENTS_ROOT}, tenant={request.tenant_id}")
            logger.info("Creating ClaudeSDKClient...")

            # Stream responses
            async with ClaudeSDKClient(options=options) as client:
                logger.info("ClaudeSDKClient connected, sending query...")
                yield format_sse_message("heartbeat", {"status": "connected"})

                await client.query(prompt)
                logger.info("Query sent, waiting for response...")
                yield format_sse_message("heartbeat", {"status": "processing"})

                # Use StreamProcessor to handle message stream
                processor = StreamProcessor(
                    client=client,
                    request=request,
                    session_service=self.session_service
                )

                async for message in processor.process():
                    yield message

        except Exception as e:
            # Suppress cancel scope errors from interrupt (expected behavior)
            error_msg = str(e)
            if "cancel scope" in error_msg.lower() or isinstance(e, (GeneratorExit, asyncio.CancelledError)):
                logger.info(f"Stream interrupted: {type(e).__name__}")
            else:
                logger.error(f"Error in process_query: {str(e)}", exc_info=True)
                yield format_sse_message("error", {
                    "message": str(e),
                    "type": type(e).__name__
                })
