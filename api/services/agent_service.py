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
from api.utils.image_loader import load_image_blocks, ImageLoadError
from api.services.vision_service import describe_images, VisionFallbackError

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

        # 从项目 settings.json 加载 MCP 服务器配置和权限配置
        self.mcp_servers: dict = {}
        extra_allow: list = []
        extra_deny: list = []
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
                extra_deny = claude_settings.get("permissions", {}).get("deny", [])
                if extra_deny:
                    logger.info(f"Loaded extra deny permissions: {extra_deny}")
            except Exception:
                logger.warning("Failed to load MCP server config from settings.json", exc_info=True)

        # 创建安全配置文件
        _base_deny = [
            # allowed_tools 只是自动批准列表；不在其中的工具仍可能被调用，
            # 必须在此显式拒绝以下"与问题定位无关"的能力：
            # - 联网/检索：WebFetch / WebSearch
            # - 定时/延迟/调度：ScheduleWakeup / CronCreate / CronList / CronDelete
            # - 后台任务/监控/远程触发：Monitor / RemoteTrigger
            # - Jupyter：NotebookEdit
            # - Worktree / Plan Mode：EnterWorktree / ExitWorktree / EnterPlanMode / ExitPlanMode
            "WebFetch",
            "WebSearch",
            "ScheduleWakeup",
            "CronCreate",
            "CronList",
            "CronDelete",
            "Monitor",
            "RemoteTrigger",
            "NotebookEdit",
            "EnterWorktree",
            "ExitWorktree",
            "EnterPlanMode",
            "ExitPlanMode",
            "Read(**/.env)",
            "Read(**/.env.*)",
            "Read(**/secrets/**)",
            "Read(**/*.pem)",
            "Read(**/*.key)",
            "Bash(printenv)",
            "Bash(export)",
            "Read(**/settings*.json)",
            "Write(**/settings*.json)",
            "Edit(**/settings*.json)",
            "Bash(rm **/settings*.json)",
            "Bash(mv **/settings*.json *)",
            "Bash(cat **/settings*.json)",
            "Bash(cat **/.env*)",
            "Bash(cat **/*.pem)",
            "Bash(cat **/*.key)",
            "Bash(grep * **/.env*)",
            "Bash(grep * **/settings*.json)",
        ]
        security_settings = {
            "permissions": {
                "allow": extra_allow,
                "deny": _base_deny + extra_deny,
            }
        }
        self.settings_file = AGENTS_ROOT / self.SETTINGS_FILE_NAME
        with open(self.settings_file, "w") as f:
            json.dump(security_settings, f, indent=2)

    # 单一事实源：工具及其可选路径模式。
    # - `tools` 参数只接受裸工具名（Skill/Read/...），决定模型 system prompt 里能看到哪些工具；
    # - `allowed_tools` 可以带路径模式（`Write(pattern)`），用于自动批准；
    # 所以这里以"带模式"的形式集中声明，`_build_tools` 会自动剥离模式得到裸名。
    _BASE_ALLOWED_TOOLS = [
        "Skill", "Read", "Grep", "Glob", "Bash",
        "Write(**/data/issue-diagnosis/instincts/**)",
        "Edit(**/data/issue-diagnosis/instincts/**)",
        "AskUserQuestion",
    ]

    # 真·工具白名单：传给 SDK 的 `tools` 参数会替换 claude_code preset 的默认工具列表，
    # 只有列出的工具会进入模型 system prompt —— 未列出的工具模型根本看不见，
    # 从源头阻止它去"尝试调用 WebFetch / ScheduleWakeup / Monitor / CronCreate 等无关工具"。
    # 注意：只接受裸工具名，不支持 `Tool(pattern)` 模式；模式匹配仍由 allowed_tools / deny 处理。
    _BASE_TOOLS = [
        "Skill",
        "Read", "Grep", "Glob", "Bash",
        "Write", "Edit",
        "AskUserQuestion",
    ]

    def _build_allowed_tools(self) -> list[str]:
        """合并基础工具和环境变量配置的 MCP 工具。"""
        mcp_tools_env = os.getenv("ALLOWED_MCP_TOOLS", "")
        mcp_tools = [t.strip() for t in mcp_tools_env.split(",") if t.strip()]
        return self._BASE_ALLOWED_TOOLS + mcp_tools

    def _build_tools(self) -> list[str]:
        """白名单工具（进入 model system prompt 的工具集）。"""
        mcp_tools_env = os.getenv("ALLOWED_MCP_TOOLS", "")
        mcp_tools = [t.strip() for t in mcp_tools_env.split(",") if t.strip()]
        return self._BASE_TOOLS + mcp_tools

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
            tools=self._build_tools(),
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
            _meta = request.metadata or {}

            # Vision capability gate:
            # - supports_vision=True:  直接放行（下方 load_image_blocks 会构造 inline base64）
            # - supports_vision=False + vision_helper: 走降级（由 helper 识图 → 文字注入 prompt → 清空 images）
            # - supports_vision=False + 无 helper:   立即返回 error
            vision_descriptions: list[str] = []
            if request.images:
                from api.dependencies import get_config_service
                from api.services.config_service import PREDEFINED_CONFIGS
                _cfg = get_config_service().get_current_config()
                if _cfg.supports_vision is False:
                    helper_name = _cfg.vision_helper
                    if not helper_name:
                        msg = f"当前模型 {_cfg.name} 不支持图片识别，请切换到 claude 等多模态模型后重试。"
                        logger.warning(msg)
                        yield format_sse_message("error", {"message": msg})
                        return
                    helper_cfg = PREDEFINED_CONFIGS.get(helper_name)
                    if helper_cfg is None:
                        msg = f"vision_helper 配置 '{helper_name}' 不存在"
                        logger.error(msg)
                        yield format_sse_message("error", {"message": msg})
                        return
                    logger.info(
                        f"Vision fallback: {_cfg.name} → {helper_cfg.name} "
                        f"(model={helper_cfg.vision_model})"
                    )
                    try:
                        image_blocks_for_helper = await load_image_blocks(request.images)
                        vision_descriptions = await describe_images(
                            image_blocks_for_helper, request.prompt, helper_cfg
                        )
                    except (ImageLoadError, VisionFallbackError) as e:
                        logger.warning(f"Vision fallback failed: {e}")
                        yield format_sse_message("error", {"message": f"图片识别失败: {e}"})
                        return
                    # 降级路径：把图片描述拼进 prompt，images 清空
                    desc_block = "\n\n".join(
                        f"【用户上传的图片 {i + 1} 识别结果】\n{d}"
                        for i, d in enumerate(vision_descriptions)
                    )
                    request = request.model_copy(update={
                        "prompt": f"{request.prompt}\n\n{desc_block}",
                        "images": None,
                    })

            _base_options = self.build_default_options()
            _current_model = _base_options.model

            if request.session_id:
                prompt = request.prompt
                if request.images:
                    prompt += f"\n\n（本轮附带 {len(request.images)} 张图片，已随消息一同送达，请直接识别分析。）"
                logger.info(f"Resuming session: {request.session_id}")
            else:
                prompt = await build_initial_prompt(
                    tenant_id=request.tenant_id,
                    user_prompt=request.prompt,
                    skill=request.skill,
                    language=request.language,
                    context_file_path=context_file_path,
                    metadata=request.metadata,
                    images=request.images,
                )
                logger.info(f"Starting new session")
            logger.info(prompt)
            # 节点 2：prompt 构建完成
            t = PerfTimer.current()
            if t:
                t.mark("PROMPT_BUILT")

            # Configure Claude SDK
            # Allow model/max_turns override via request.metadata (e.g. for audit plugin)
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

            image_blocks: list[dict] = []
            if request.images:
                image_blocks = await load_image_blocks(request.images)
                logger.info(f"Loaded {len(image_blocks)} image block(s) as base64")

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

                    sdk_session_id = request.session_id or "default"
                    if image_blocks:
                        content_blocks: list[dict] = [{"type": "text", "text": prompt}]
                        content_blocks.extend(image_blocks)

                        async def _stream_user_message() -> AsyncGenerator[dict, None]:
                            yield {
                                "type": "user",
                                "message": {"role": "user", "content": content_blocks},
                                "parent_tool_use_id": None,
                                "session_id": sdk_session_id,
                            }

                        await client.query(_stream_user_message(), session_id=sdk_session_id)
                    else:
                        await client.query(prompt, session_id=sdk_session_id)
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

        except ImageLoadError as e:
            logger.warning(f"Image load error: {e}")
            yield format_sse_message("error", {"message": str(e)})
            return

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
