"""Agent business logic service."""

import asyncio
import json
import logging
import os
from dataclasses import replace as dc_replace
from typing import Optional, AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from api.models.requests import QueryRequest
from api.core.streaming import StreamProcessor
from api.utils import build_initial_prompt, format_sse_message
from api.utils.perf_timer import PerfTimer
from api.utils.interaction_logger import interaction_logger, FALLBACK_PHRASE
from api.constants import AGENTS_ROOT, DATA_DIR, AGENT_CWD
from api.services.sdk_pool import get_cache, CachedSession

logger = logging.getLogger(__name__)

_SECURITY_APPEND = """
# 安全输出限制

以下内容严禁在任何回复中输出或暗示：

1. **认证凭证**：API Key、Token、OAuth Token、密码等（如 GLM_AUTH_TOKEN、CLAUDE_CODE_OAUTH_TOKEN、LITELLM_API_KEY、APIFOX_TOKEN、OPEN_API_APP_KEY 等环境变量的值）
2. **数据库配置**：数据库地址、端口、用户名、密码、数据库名（POSTGRES_HOST/PORT/USER/PASSWORD/DATABASE）
3. **服务内部配置**：内部服务地址、代理地址、MCP 服务器地址、模型路由配置
4. **日志打印外部供应商凭证** ： 航信订单code，新时代appid,企响应appId,appSecretkey等，如返回需要脱敏

如果用户询问上述信息，回复"该信息涉及系统安全，无法提供"，不做任何解释或变通。
"""


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

        # 从项目 settings.json 加载 MCP 服务器配置和权限配置
        self.mcp_servers: dict = {}
        extra_allow: list = []
        if self.CLAUDE_SETTINGS_FILE.exists():
            try:
                with open(self.CLAUDE_SETTINGS_FILE, encoding="utf-8") as f:
                    claude_settings = json.load(f)
                self.mcp_servers = claude_settings.get("mcpServers", {})
                if self.mcp_servers:
                    logger.info(f"Loaded MCP servers: {list(self.mcp_servers.keys())}")
                extra_allow = claude_settings.get("permissions", {}).get("allow", [])
                if extra_allow:
                    logger.info(f"Loaded extra allow permissions: {extra_allow}")
            except Exception:
                logger.warning("Failed to load MCP server config from settings.json", exc_info=True)

        # 创建安全配置文件
        security_settings = {
            "permissions": {
                "allow": extra_allow,
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

    _BASE_ALLOWED_TOOLS = [
        "Skill", "Read", "Write", "Edit", "Grep", "Glob", "Bash",
        "AskUserQuestion",
    ]

    def _build_allowed_tools(self) -> list[str]:
        """合并基础工具和环境变量配置的 MCP 工具。"""
        mcp_tools_env = os.getenv("ALLOWED_MCP_TOOLS", "")
        mcp_tools = [t.strip() for t in mcp_tools_env.split(",") if t.strip()]
        return self._BASE_ALLOWED_TOOLS + mcp_tools

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
            system_prompt={"type": "preset", "preset": "claude_code", "append": _SECURITY_APPEND},
            mcp_servers=self.mcp_servers,
            setting_sources=["project"],
            settings=str(self.settings_file),
            allowed_tools=self._build_allowed_tools(),
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
            logger.info(prompt)
            # 节点 2：prompt 构建完成
            t = PerfTimer.current()
            if t:
                t.mark("PROMPT_BUILT")

            # Configure Claude SDK
            # Allow model/max_turns override via request.metadata (e.g. for audit plugin)
            _meta = request.metadata or {}
            _base_options = self.build_default_options()
            _default_skills_env = os.getenv("DEFAULT_SKILLS", "")
            _default_skills = [s.strip() for s in _default_skills_env.split(",") if s.strip()] if _default_skills_env else None
            if request.skill and not request.session_id:
                skills = [request.skill]
            elif not request.session_id:
                skills = _default_skills
            else:
                skills = None
            options = dc_replace(
                _base_options,
                model=_meta.get("model") or _base_options.model,
                max_turns=int(_meta.get("max_turns", 40)),
                resume=request.session_id,
                skills=skills,
            )

            t = PerfTimer.current()
            if t:
                t.mark("OPTIONS_BUILT")

            logger.info(
                f"Claude SDK config: cwd={AGENT_CWD}, tenant={request.tenant_id}"
            )

            cache = get_cache()
            cache_key = request.session_id  # 只有 resume 时才有值

            for attempt in range(2):
                healthy = True

                if cache and cache_key:
                    client = await cache.get_or_create(cache_key, options)
                    t = PerfTimer.current()
                    if t:
                        t.mark("SDK_CACHE_HIT" if attempt == 0 else "SDK_CACHE_RETRY")
                else:
                    client = ClaudeSDKClient(options=options)
                    await client.connect()
                    t = PerfTimer.current()
                    if t:
                        t.mark("SDK_COLD_START")

                async def _on_session_id(real_sid: str) -> None:
                    nonlocal cache_key
                    if cache and not cache_key:
                        async with cache._lock:
                            if real_sid not in cache._cache:
                                cache._cache[real_sid] = CachedSession(client=client, in_use=True)
                        cache_key = real_sid
                        logger.info(f"[SessionCache] 新会话存入缓存: {real_sid}")

                asked_user_question = False
                got_message = False
                try:
                    t = PerfTimer.current()
                    if t:
                        t.mark("SDK_CONNECTED")
                    yield format_sse_message("heartbeat", {"status": "connected"})

                    await client.query(prompt, session_id=request.session_id or "default")
                    t = PerfTimer.current()
                    if t:
                        t.mark("QUERY_SENT")
                    logger.info(f"Query sent: {prompt[:80]}...")
                    yield format_sse_message("heartbeat", {"status": "processing"})

                    processor = StreamProcessor(
                        client=client, request=request, session_service=self.session_service,
                        on_session_id=_on_session_id if not request.session_id else None,
                    )

                    answer_parts = []

                    async for message in processor.process():
                        got_message = True
                        event = message.get("event")
                        if event == "assistant_message":
                            try:
                                answer_parts.append(json.loads(message["data"]).get("content", ""))
                            except Exception:
                                pass
                        elif event == "ask_user_question":
                            asked_user_question = True
                        elif event == "result":
                            try:
                                data = json.loads(message["data"])
                                answer = "".join(answer_parts)
                                await interaction_logger.log({
                                    "question": request.prompt,
                                    "answer": answer,
                                    "skill": request.skill,
                                    "tenant_id": request.tenant_id,
                                    "session_id": data.get("session_id"),
                                    "num_turns": data.get("num_turns"),
                                    "duration_ms": data.get("duration_ms"),
                                    "status": "error" if data.get("is_error") else "success",
                                    "has_doc_url": "http" in answer,
                                    "used_fallback_phrase": FALLBACK_PHRASE in answer,
                                    "asked_user_question": asked_user_question,
                                    "product_selected": (request.metadata or {}).get("product_selected"),
                                })
                            except Exception as e:
                                logger.warning(f"Failed to log interaction: {e}")
                        yield message

                except Exception:
                    healthy = False
                    raise
                except GeneratorExit:
                    raise
                except BaseException:
                    healthy = False
                    raise
                finally:
                    if asked_user_question:
                        healthy = False
                    if cache and cache_key:
                        await cache.release(cache_key, healthy=healthy)
                    elif not cache:
                        try:
                            await client.disconnect()
                        except Exception:
                            pass

                if got_message:
                    break

                # 空响应：连接已死，重试一次（仅对 resume 场景有意义）
                if attempt == 0 and cache and cache_key:
                    logger.warning(f"Empty response on cached connection, retrying with fresh: {cache_key}")
                else:
                    break

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
