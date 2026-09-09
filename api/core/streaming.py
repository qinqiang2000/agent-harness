"""Claude SDK streaming response processor."""

import asyncio
import json
import logging
import os
import re
import sys
from typing import AsyncGenerator

# asyncio.timeout 在 Python 3.11+ 才引入，3.10 用 async_timeout 兼容
if sys.version_info >= (3, 11):
    _asyncio_timeout = asyncio.timeout
else:
    try:
        from async_timeout import timeout as _asyncio_timeout
    except ImportError:
        import contextlib

        @contextlib.asynccontextmanager
        async def _asyncio_timeout(delay):
            """asyncio.timeout 的简单 fallback，Python 3.10 无 async_timeout 时使用。"""
            task = asyncio.current_task()
            handle = asyncio.get_event_loop().call_later(delay, task.cancel)
            try:
                yield
            except asyncio.CancelledError:
                raise asyncio.TimeoutError()
            finally:
                handle.cancel()


from claude_agent_sdk import (
    ClaudeSDKClient,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from api.models.requests import QueryRequest
from api.utils import format_sse_message, extract_todos_from_tool, redact, should_redact
from api.utils.sdk_logger import SDKLogger
from api.utils.perf_timer import PerfTimer, set_session_id

logger = logging.getLogger(__name__)


_TRANSFER_PATTERN = re.compile(r"\[TRANSFER:([^\]]*)\]\s*")


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
        usage_sink=None,
    ):
        """
        Args:
            client: Claude SDK client
            request: Query request
            session_service: Session service (optional, dependency injection)
            on_session_id: async callable(session_id) — 新会话拿到真实 session_id 时调用
            usage_sink: callable(dict) — 流结束时回调，接收本次请求的 token 用量与
                归因明细（session 汇总 + turn 级增量 + 工具返回体积），由上层落库。
                任何异常都在内部吞掉，不影响回答链路。
        """
        self.client = client
        self.request = request
        self.session_service = session_service
        self.on_session_id = on_session_id
        self.usage_sink = usage_sink
        self.session_id_sent = False
        self.actual_session_id = request.session_id
        self.first_message_received = False
        self.session_registered = False
        self.sdk_logger = SDKLogger(logger)  # Enhanced SDK message logger

        # ---- token 用量采集状态 ----
        self._turn_idx = 0            # 主 agent 轮次计数
        self._tool_volume = []        # 工具返回内容体积（口径 B）
        self._tool_targets = {}       # tool_use_id → (工具名, 目标描述)
        self._usage_reported = False  # 防止 result 事件重复上报

    async def _ensure_session_registered(self, session_id: str):
        """确保会话已注册（消除重复逻辑）

        Args:
            session_id: 会话 ID
        """
        if not self.session_registered and self.session_service:
            await self.session_service.register(session_id, self.client)
            self.session_registered = True

    async def _emit_session_created(
        self, session_id: str
    ) -> AsyncGenerator[dict, None]:
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
            set_session_id(self.request.session_id)
            await self._ensure_session_registered(self.request.session_id)

        timeout_ms = int(os.environ.get("API_TIMEOUT_MS", "1800000"))
        timeout_s = timeout_ms / 1000.0

        try:
            async with _asyncio_timeout(timeout_s):
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

                    elif isinstance(msg, UserMessage):
                        # UserMessage 承载 tool_result，只用于统计工具返回体积，
                        # 不产生任何 SSE 事件，因此不进入 yield 链路。
                        self._collect_tool_results(msg)

                    elif isinstance(msg, ResultMessage):
                        async for sse_msg in self._handle_result_message(msg):
                            yield sse_msg

            if not self.first_message_received:
                logger.warning("No messages received from Claude SDK")

        except asyncio.TimeoutError:
            logger.error(
                f"Stream timed out after {timeout_s:.0f}s (API_TIMEOUT_MS={timeout_ms})"
            )
            yield format_sse_message(
                "error", {"message": f"模型响应超时（{timeout_s:.0f}秒），请稍后重试。"}
            )
        finally:
            # Clean up session
            if (
                self.session_registered
                and self.actual_session_id
                and self.session_service
            ):
                await self.session_service.unregister(self.actual_session_id)

    async def _handle_system_message(
        self, msg: SystemMessage
    ) -> AsyncGenerator[dict, None]:
        """Handle system message."""
        self.sdk_logger.log_system_message(msg)

        if (
            hasattr(msg, "subtype")
            and msg.subtype == "init"
            and not self.request.session_id
            and not self.session_id_sent
        ):

            if isinstance(msg.data, dict) and "session_id" in msg.data:
                self.actual_session_id = msg.data["session_id"]
                set_session_id(self.actual_session_id)

                # Emit session created event (also triggers on_session_id callback)
                async for sse_msg in self._emit_session_created(self.actual_session_id):
                    yield sse_msg

                # Register session
                await self._ensure_session_registered(self.actual_session_id)

    def _record_turn_usage(self, msg: AssistantMessage) -> None:
        """统计主 agent 轮次，并暂存本轮调用的工具，供后续归因定位。

        注意：SDK 在流式模式下不填充 AssistantMessage.usage（实测恒为
        {"input_tokens": 0, "output_tokens": 0}），因此无法在此拿到逐轮 token。
        归因改由 tool_volume 的内容体积按轮次加权推算，总量以 ResultMessage
        的真实 usage 为锚，见 token_usage_store.attribute_buckets。

        Args:
            msg: SDK 的 AssistantMessage

        Returns:
            None
        """
        # 子 agent（parent_tool_use_id 非空）不占主 agent 的上下文轮次
        if not msg.parent_tool_use_id:
            self._turn_idx += 1

    def _collect_tool_results(self, msg: UserMessage) -> None:
        """统计工具返回内容的字符数，用于体积归因（口径 B）。

        回答"具体哪个文件 / 哪次 ELK 查询最肥"，与增量归因互补。

        Args:
            msg: SDK 的 UserMessage，其 content 中可能含 ToolResultBlock

        Returns:
            None。采集失败只记 debug 日志。
        """
        try:
            if not isinstance(msg.content, list):
                return
            for block in msg.content:
                if not isinstance(block, ToolResultBlock):
                    continue
                content = block.content
                if isinstance(content, str):
                    chars = len(content)
                elif isinstance(content, list):
                    chars = sum(
                        len(str(item.get("text", "")))
                        for item in content
                        if isinstance(item, dict)
                    )
                else:
                    chars = 0
                name, target = self._tool_targets.get(
                    block.tool_use_id, ("unknown", "")
                )
                self._tool_volume.append(
                    {
                        "tool_name": name,
                        "target": target,
                        "result_chars": chars,
                        "turn_idx": max(self._turn_idx - 1, 0),
                        "is_subagent": bool(msg.parent_tool_use_id),
                    }
                )
        except Exception as e:
            logger.debug(f"[TokenUsage] 统计工具返回体积失败: {e}")

    def _report_usage(self, msg: ResultMessage) -> None:
        """把本次请求的完整用量与归因明细交给 usage_sink 落库。

        Args:
            msg: SDK 的 ResultMessage，含 usage / total_cost_usd / model_usage

        Returns:
            None。sink 抛异常只记 warning，绝不影响 SSE 输出。
        """
        if self._usage_reported or not self.usage_sink:
            return
        self._usage_reported = True
        try:
            model = None
            if isinstance(msg.model_usage, dict) and msg.model_usage:
                model = next(iter(msg.model_usage.keys()), None)
            self.usage_sink(
                {
                    "session_id": msg.session_id,
                    "usage": msg.usage,
                    "model_usage": msg.model_usage,
                    "cost_sdk_usd": msg.total_cost_usd,
                    "model": model,
                    "num_turns": msg.num_turns,
                    "duration_ms": msg.duration_ms,
                    "status": "error" if msg.is_error else "success",
                    "total_turns": self._turn_idx,
                    "tool_volume": self._tool_volume,
                }
            )
        except Exception as e:
            logger.warning(f"[TokenUsage] usage_sink 上报失败: {e}")

    async def _handle_assistant_message(
        self, msg: AssistantMessage
    ) -> AsyncGenerator[dict, None]:
        """Handle assistant message."""
        self._record_turn_usage(msg)
        tool_blocks = [b for b in msg.content if isinstance(b, ToolUseBlock)]
        for b in tool_blocks:
            self._tool_targets[b.id] = (b.name, _tool_target(b))
        if len(tool_blocks) > 1:
            tool_names = [b.name for b in tool_blocks]
            logger.info(f"[Turn] {len(tool_blocks)} parallel tool calls: {tool_names}")
        for block in msg.content:
            if isinstance(block, TextBlock):
                self.sdk_logger.log_text_block(block)
                if (
                    block.text
                    and block.text.strip()
                    and block.text.strip() != "(empty)"
                ):
                    text = (
                        redact(block.text)
                        if should_redact(self.request.skill, self.request.tenant_id)
                        else block.text
                    )
                    # 过滤非 Claude 模型泄漏的内部标记（DeepSeek/Qwen 等模型的工具调用格式）
                    INTERNAL_MARKERS = [
                        "<｜DSML｜",
                        "<|tool_calls|>",
                        "<|im_start|>",
                        "<|im_end|>",
                        "<|endoftext|>",
                    ]
                    if any(marker in text for marker in INTERNAL_MARKERS):
                        logger.warning(
                            f"[StreamFilter] Suppressed output containing internal marker, session={self.request.session_id}"
                        )
                    else:
                        yield format_sse_message("assistant_message", text)

            elif isinstance(block, ToolUseBlock):
                self.sdk_logger.log_tool_use(block)
                yield format_sse_message(
                    "tool_use", {"name": block.name, "input": block.input}
                )

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
                                logger.error(
                                    f"[AskUserQuestion] Failed to parse questions string: {questions[:100]}"
                                )
                                yield format_sse_message(
                                    "assistant_message", "抱歉，agent异常，请稍后再试。"
                                )
                                questions = []
                        if questions and isinstance(questions, list):
                            logger.info(
                                f"[AskUserQuestion] Emitting {len(questions)} question(s)"
                            )
                            yield format_sse_message(
                                "ask_user_question", {"questions": questions}
                            )

    async def _handle_result_message(
        self, msg: ResultMessage
    ) -> AsyncGenerator[dict, None]:
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
            "num_turns": msg.num_turns,
        }

        # token 用量透出到 SSE，同时上报给 usage_sink 落库
        usage = msg.usage or {}
        if usage:
            result_data["usage"] = usage
        if msg.total_cost_usd is not None:
            result_data["total_cost_usd"] = msg.total_cost_usd
        self._report_usage(msg)

        # Include result field if present (SDK final output)
        if msg.result:
            m = _TRANSFER_PATTERN.search(msg.result)
            if m:
                group_name = m.group(1).strip()
                reason = (
                    msg.result[m.end() :].strip() or msg.result[: m.start()].strip()
                )
                logger.info(f"[Transfer] Detected transfer signal: group={group_name}")
                yield format_sse_message(
                    "transfer_human", {"group": group_name, "reason": reason}
                )
                result_data["result"] = reason
            else:
                # 过滤内部标记（DeepSeek/Qwen 等模型 rate-limiting 时泄漏的残留片段）
                INTERNAL_MARKERS = [
                    "<｜DSML｜",
                    "<|tool_calls|>",
                    "<|im_start|>",
                    "<|im_end|>",
                    "<|endoftext|>",
                    "<COR",
                    "<-limiting",
                    "<rate",
                ]
                result = msg.result
                if any(marker in result for marker in INTERNAL_MARKERS):
                    logger.warning(
                        f"[StreamFilter] Suppressed result containing internal marker: {result[:50]!r}"
                    )
                    result_data["result"] = "抱歉，处理您的问题时出现错误，请稍后再试。"
                else:
                    result_data["result"] = result

        yield format_sse_message("result", result_data)

        # Log result message with enhanced formatting
        self.sdk_logger.log_result_message(msg)

        # 节点 6：全部完成，打印 SDK 统计的 API 耗时供对比
        t = PerfTimer.current()
        if t:
            t.mark(f"DONE (sdk_api={msg.duration_api_ms}ms turns={msg.num_turns})")


def _tool_target(block: ToolUseBlock) -> str:
    """从工具调用入参中提取可读的目标标识，用于体积归因排行。

    Args:
        block: SDK 的 ToolUseBlock

    Returns:
        目标描述，如文件路径、搜索关键词、子 agent 描述；无法识别时返回空串
    """
    inp = block.input if isinstance(block.input, dict) else {}
    for key in ("file_path", "path", "pattern", "query", "index", "command", "description", "skill"):
        val = inp.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:200]
    return ""
