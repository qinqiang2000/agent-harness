"""Agent business logic service."""

import asyncio
import json
import logging
from typing import Optional, AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from api.models.requests import QueryRequest
from api.core.streaming import StreamProcessor
from api.utils import build_initial_prompt, format_sse_message
from api.constants import AGENTS_ROOT, DATA_DIR, AGENT_CWD

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

    SETTINGS_FILE_NAME = ".custom-settings.json"

    def __init__(self, session_service=None):
        """
        Args:
            session_service: Session service (dependency injection, default None = not used)
        """
        self.session_service = session_service

        # 创建安全配置文件
        security_settings = {
            "permissions": {
                "deny": [
                    "Read(/.env)",
                    "Read(/.env.*)",
                    "Read(/secrets/**)",
                    "Read(/*.pem)",
                    "Read(/*.key)",
                    "Bash(printenv)",
                    "Bash(export)",
                    "Read(/**/settings*.json)",
                    "Write(/**/settings*.json)",
                    "Edit(/**/settings*.json)",
                    "Bash(rm /**/settings*.json)",
                    "Bash(mv /**/settings*.json *)",
                ]
            }
        }
        self.settings_file = AGENTS_ROOT / self.SETTINGS_FILE_NAME
        with open(self.settings_file, "w") as f:
            json.dump(security_settings, f, indent=2)

    async def process_query(
        self, request: QueryRequest, context_file_path: Optional[str] = None
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
                model="claude-sonnet-4-5",
                system_prompt={"type": "preset", "preset": "claude_code"},
                setting_sources=["project"],
                settings=str(self.settings_file),
                allowed_tools=[
                    "Skill",
                    "Read",
                    "Grep",
                    "Glob",
                    "Bash",
                    "WebFetch",
                    "WebSearch",
                    "AskUserQuestion",
                ],
                resume=request.session_id,
                max_buffer_size=10 * 1024 * 1024,
                cwd=str(AGENT_CWD),
                add_dirs=[],
            )

            logger.info(
                f"Claude SDK config: cwd={AGENT_CWD}, tenant={request.tenant_id}"
            )
            logger.info("Creating ClaudeSDKClient...")

            # Stream responses
            async with ClaudeSDKClient(options=options) as client:
                logger.info("ClaudeSDKClient connected, sending query...")
                yield format_sse_message("heartbeat", {"status": "connected"})

                await client.query(prompt)
                logger.info(f"Query sent: {prompt}")
                yield format_sse_message("heartbeat", {"status": "processing"})

                # Use StreamProcessor to handle message stream
                processor = StreamProcessor(
                    client=client, request=request, session_service=self.session_service
                )

                async for message in processor.process():
                    yield message

        except Exception as e:
            # Suppress cancel scope errors from interrupt (expected behavior)
            error_msg = str(e)
            if "cancel scope" in error_msg.lower() or isinstance(
                e, (GeneratorExit, asyncio.CancelledError)
            ):
                logger.info(f"Stream interrupted: {type(e).__name__}")
            else:
                logger.error(f"Error in process_query: {str(e)}", exc_info=True)
                yield format_sse_message(
                    "error", {"message": str(e), "type": type(e).__name__}
                )
