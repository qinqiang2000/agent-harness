"""Agent business logic service."""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import replace as dc_replace
from typing import Optional, AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from api.models.requests import QueryRequest
from api.core.streaming import StreamProcessor
from api.utils import build_initial_prompt, format_sse_message
from api.utils.perf_timer import PerfTimer
from api.constants import AGENTS_ROOT, DATA_DIR, AGENT_CWD
from api.services.sdk_pool import get_cache

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
    CLAUDE_SETTINGS_FILE = AGENT_CWD / ".claude" / "settings.json"

    def __init__(self, session_service=None):
        """
        Args:
            session_service: Session service (dependency injection, default None = not used)
        """
        self.session_service = session_service

        # 从项目 settings.json 加载 MCP 服务器配置
        self.mcp_servers: dict = {}
        if self.CLAUDE_SETTINGS_FILE.exists():
            try:
                with open(self.CLAUDE_SETTINGS_FILE, encoding="utf-8") as f:
                    claude_settings = json.load(f)
                self.mcp_servers = claude_settings.get("mcpServers", {})
                if self.mcp_servers:
                    logger.info(f"Loaded MCP servers: {list(self.mcp_servers.keys())}")
            except Exception:
                logger.warning("Failed to load MCP server config from settings.json", exc_info=True)

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

    def build_default_options(self) -> ClaudeAgentOptions:
        """构建默认 SDK options。"""
        from api.dependencies import get_config_service
        _current_config = get_config_service().get_current_config()
        _env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        return ClaudeAgentOptions(
            model=_current_config.model or "claude-sonnet-4-6",
            env=_env,
            stderr=lambda line: logger.error(f"[CLI stderr] {line.rstrip()}"),
            max_turns=40,
            system_prompt={"type": "preset", "preset": "claude_code"},
            mcp_servers=self.mcp_servers,
            setting_sources=["project"],
            settings=str(self.settings_file),
            allowed_tools=[
                "Skill", "Read", "Grep", "Glob", "Bash",
                "WebFetch", "WebSearch", "AskUserQuestion",
                "mcp__elastic__searchTraceOrKeyWordsLog",
                "mcp__gitlab__get_file_contents",
                "mcp__gitlab__get_repository_tree",
                "mcp__gitlab__get_project",
                "mcp__gitlab__list_issues",
                "mcp__gitlab__get_issue",
                "mcp__gitlab__list_merge_requests",
                "mcp__gitlab__get_merge_request",
                "mcp__gitlab__get_merge_request_diffs",
                "mcp__gitlab__list_commits",
                "mcp__gitlab__get_commit",
                "mcp__gitlab__get_commit_diff",
                "mcp__gitlab__get_branch_diffs",
                "mcp__gitlab__search_repositories",
            ],
            max_buffer_size=10 * 1024 * 1024,
            cwd=str(AGENT_CWD),
            add_dirs=[],
        )

    async def process_query(
        self, request: QueryRequest, context_file_path: Optional[str] = None,
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

            # 节点 2：prompt 构建完成
            t = PerfTimer.current()
            if t:
                t.mark("PROMPT_BUILT")

            # Configure Claude SDK
            # Allow model/max_turns override via request.metadata (e.g. for audit plugin)
            _meta = request.metadata or {}
            _base_options = self.build_default_options()
            options = dc_replace(
                _base_options,
                model=_meta.get("model") or _base_options.model,
                max_turns=int(_meta.get("max_turns", 40)),
                resume=request.session_id,
            )

            logger.info(
                f"Claude SDK config: cwd={AGENT_CWD}, tenant={request.tenant_id}"
            )

            cache = get_cache()
            cache_key = request.session_id or str(uuid.uuid4())
            healthy = True

            if cache:
                client = await cache.get_or_create(cache_key, options)
            else:
                logger.info("ClaudeSDKClient: 按需创建连接（缓存未初始化）...")
                client = ClaudeSDKClient(options=options)
                await client.connect()

            try:
                # 节点 3：SDK 初始化完成
                t = PerfTimer.current()
                if t:
                    t.mark("SDK_CONNECTED")
                yield format_sse_message("heartbeat", {"status": "connected"})

                await client.query(prompt, session_id=request.session_id or "default")
                logger.info(f"Query sent: {prompt[:80]}...")
                yield format_sse_message("heartbeat", {"status": "processing"})

                # Use StreamProcessor to handle message stream
                processor = StreamProcessor(
                    client=client, request=request, session_service=self.session_service
                )

                async for message in processor.process():
                    yield message

            except Exception:
                healthy = False
                raise
            finally:
                if cache:
                    await cache.release(cache_key, healthy=healthy)
                else:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

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
