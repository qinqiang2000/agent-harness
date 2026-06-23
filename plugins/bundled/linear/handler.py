"""Linear Agent 简洁版事件处理器。

created 事件：直接将 issue 信息拼成 prompt 调用 AgentService，结果回写 Linear Activity。
prompted 事件：暂不支持续接，返回提示。
stopped 事件：记录日志（当前调用为一次性，无需取消）。
"""

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, Optional

from api.services.agent_service import AgentService

from plugins.bundled.linear.linear_client import LinearClient, LinearAPIError
from plugins.bundled.linear.token_store import TokenStore

logger = logging.getLogger(__name__)


def _new_trace_id() -> str:
    return uuid.uuid4().hex[:8]


class LinearSessionHandler:
    """处理 Linear AgentSession 事件，收到 created 后直接调用 AgentService。"""

    def __init__(
        self,
        agent_service: AgentService,
        token_store: TokenStore,
        config: Dict[str, Any],
    ):
        self.agent_service = agent_service
        self.token_store = token_store
        self.config = config
        # 正在处理中的 session 集合（幂等保护）
        self._active_sessions: set = set()
        # linear_session_id -> claude_session_id 映射，支持多轮续接
        self._session_map: Dict[str, str] = {}

    # ── 公共入口 ─────────────────────────────────────────────────────────────

    async def handle_created(self, payload: Dict[str, Any]) -> None:
        """处理 AgentSession created 事件，构建 prompt 并调用 AgentService。

        Args:
            payload: Linear Webhook 原始 payload
        """
        agent_session = payload.get("agentSession", {})
        session_id = agent_session.get("id")
        issue_id = agent_session.get("issueId")
        workspace_id = payload.get("organizationId", "")

        # promptContext 优先，其次取 issue description
        prompt_context = payload.get("promptContext", "")
        if not prompt_context:
            prompt_context = agent_session.get("issue", {}).get("description", "")

        if not session_id:
            logger.error("[Linear] handle_created: missing session_id")
            return

        # 幂等保护：同一 session_id 已处理则跳过
        if session_id in self._active_sessions:
            logger.info(
                f"[Linear] Duplicate created event, skipping: session={session_id}"
            )
            return

        self._active_sessions.add(session_id)
        trace_id = _new_trace_id()

        try:
            await self._process(
                session_id=session_id,
                issue_id=issue_id,
                prompt_context=prompt_context,
                workspace_id=workspace_id,
                trace_id=trace_id,
            )
        finally:
            self._active_sessions.discard(session_id)

    async def handle_prompted(self, payload: Dict[str, Any]) -> None:
        """处理 AgentSession prompted 事件（用户追加消息）。

        从 payload 中取用户新消息，续接原 Claude session 进行多轮对话。

        Args:
            payload: Linear Webhook 原始 payload
        """
        agent_session = payload.get("agentSession", {})
        session_id = agent_session.get("id")
        workspace_id = payload.get("organizationId", "")

        # prompted payload 结构：用户消息在顶层 agentActivity.content.body
        prompt_context = ""
        agent_activity = payload.get("agentActivity", {})
        if agent_activity:
            content = agent_activity.get("content", {})
            if isinstance(content, dict) and content.get("type") == "prompt":
                prompt_context = content.get("body", "")
        # 兜底：从 promptContext 取
        if not prompt_context:
            prompt_context = payload.get("promptContext", "")

        if not session_id:
            return

        if not prompt_context:
            logger.warning(
                f"[Linear] handle_prompted: cannot find user message, payload keys={list(payload.keys())}, agentSession keys={list(agent_session.keys())}"
            )
            return

        trace_id = _new_trace_id()
        claude_session_id = self._session_map.get(session_id)
        logger.info(
            f"[{trace_id}][Linear] prompted: linear_session={session_id}, claude_session={claude_session_id}"
        )

        token = self._get_token(workspace_id)
        if not token:
            logger.error(
                f"[{trace_id}][Linear] handle_prompted: no token for workspace={workspace_id}"
            )
            return

        client = LinearClient(token)

        try:
            await client.send_thought(session_id, "已收到，正在处理中...")
        except Exception:
            pass

        result_text = ""
        error_text = ""
        try:
            from api.models.requests import QueryRequest

            request = QueryRequest(
                prompt=prompt_context,
                language="中文",
                session_id=claude_session_id,
            )
            new_claude_session_id = claude_session_id
            async for event in self.agent_service.process_query(request):
                event_type = event.get("type") or event.get("event", "")
                data = event.get("data", {})
                if isinstance(data, str):
                    import json

                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                if event_type == "session_created":
                    new_claude_session_id = data.get(
                        "session_id", new_claude_session_id
                    )
                elif event_type == "assistant_message":
                    text = data.get("content", "")
                    if text:
                        try:
                            await client.send_thought(session_id, text[:300])
                        except Exception:
                            pass
                elif event_type == "result":
                    result_text = data.get("result", "") or data.get("content", "")
                elif event_type == "error":
                    error_text = data.get("error", "") or str(data)

            if new_claude_session_id:
                self._session_map[session_id] = new_claude_session_id

        except Exception as e:
            error_text = str(e)
            logger.error(
                f"[{trace_id}][Linear] prompted AgentService call failed: {e}",
                exc_info=True,
            )

        try:
            if error_text:
                await client.send_error(session_id, f"处理失败：{error_text}")
            else:
                await client.send_response(
                    session_id, result_text or "Agent 已处理完成，无输出内容。"
                )
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send prompted result", exc_info=True
            )

    async def handle_stopped(self, payload: Dict[str, Any]) -> None:
        """处理 stop 信号，记录日志。

        当前简洁版每次调用为一次性，stop 仅记录日志。

        Args:
            payload: Linear Webhook 原始 payload
        """
        session_id = payload.get("agentSession", {}).get("id", "")
        logger.info(f"[Linear] Stop signal received: session={session_id}")

    # ── 核心处理流程 ──────────────────────────────────────────────────────────

    async def _process(
        self,
        session_id: str,
        issue_id: Optional[str],
        prompt_context: str,
        workspace_id: str,
        trace_id: str,
    ) -> None:
        """拉取 Issue 信息，构建 prompt，调用 AgentService，结果回写 Linear。

        Args:
            session_id: AgentSession ID
            issue_id: Linear Issue UUID
            prompt_context: 来自 webhook 的 promptContext 或 issue description
            workspace_id: Linear workspace/organization ID
            trace_id: 本次请求追踪 ID
        """
        token = self._get_token(workspace_id)
        if not token:
            logger.error(f"[{trace_id}][Linear] No token for workspace={workspace_id}")
            return

        client = LinearClient(token)

        # 发送 thought，让用户知道 Agent 已收到
        try:
            await client.send_thought(session_id, "已收到，正在处理中...")
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send initial thought", exc_info=True
            )

        # 拉取 Issue 详情，补充到 prompt
        issue_info = ""
        issue_identifier = ""
        if issue_id:
            try:
                issue = await client.get_issue(issue_id)
                issue_identifier = issue.get("identifier", "")
                title = issue.get("title", "")
                description = issue.get("description", "")
                state = issue.get("state", {}).get("name", "")
                priority = issue.get("priorityLabel", "")
                issue_info = (
                    f"Issue: {issue_identifier} — {title}\n"
                    f"状态: {state} | 优先级: {priority}\n"
                    f"描述:\n{description}"
                )
                # 将 Issue 置为 started 状态
                await self._set_issue_in_progress(
                    client, issue_id, workspace_id, trace_id
                )
            except Exception:
                logger.warning(
                    f"[{trace_id}][Linear] Failed to fetch issue detail",
                    exc_info=True,
                )

        # 构建最终 prompt
        system_prompt = self.config.get("system_prompt", "")
        prompt_parts = []
        if system_prompt:
            prompt_parts.append(system_prompt)
        if issue_info:
            prompt_parts.append(issue_info)
        if prompt_context and prompt_context != issue_info:
            prompt_parts.append(f"用户输入:\n{prompt_context}")

        final_prompt = "\n\n".join(prompt_parts) if prompt_parts else prompt_context

        logger.info(
            f"[{trace_id}][Linear] Calling AgentService: session={session_id}, "
            f"issue={issue_identifier or issue_id}"
        )

        # 调用 AgentService
        result_text = ""
        error_text = ""
        try:
            from api.models.requests import QueryRequest

            request = QueryRequest(
                prompt=final_prompt,
                skill="issue-diagnosis-billing",
                language="中文",
            )
            async for event in self.agent_service.process_query(request):
                event_type = event.get("type") or event.get("event", "")
                data = event.get("data", {})
                if isinstance(data, str):
                    import json

                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                if event_type == "session_created":
                    # 保存 linear_session_id -> claude_session_id 映射，供 prompted 续接
                    claude_session_id = data.get("session_id")
                    if claude_session_id:
                        self._session_map[session_id] = claude_session_id
                        logger.info(
                            f"[{trace_id}][Linear] session mapped: {session_id} -> {claude_session_id}"
                        )
                elif event_type == "assistant_message":
                    text = data.get("content", "")
                    if text:
                        try:
                            await client.send_thought(session_id, text[:300])
                        except Exception:
                            pass
                elif event_type == "result":
                    result_text = data.get("result", "") or data.get("content", "")
                elif event_type == "error":
                    error_text = data.get("error", "") or str(data)
        except Exception as e:
            error_text = str(e)
            logger.error(
                f"[{trace_id}][Linear] AgentService call failed: {e}", exc_info=True
            )

        # 回写结果到 Linear
        try:
            if error_text:
                await client.send_error(session_id, f"处理失败：{error_text}")
            else:
                response = result_text or "Agent 已处理完成，无输出内容。"
                await client.send_response(session_id, response)
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send result to Linear",
                exc_info=True,
            )

        # 仅结论类型为 CODE_BUG 且 skill 内部未完成修复时，由 handler 层兜底触发 code-fix
        if (
            not error_text
            and result_text
            and "【结论类型】CODE_BUG" in result_text
            and "修复完成" not in result_text
        ):
            await self._trigger_code_fix(
                session_id=session_id,
                result_text=result_text,
                workspace_id=workspace_id,
                trace_id=trace_id,
                client=client,
            )

        logger.info(f"[{trace_id}][Linear] Completed: session={session_id}")

    async def _set_issue_in_progress(
        self,
        client: LinearClient,
        issue_id: str,
        workspace_id: str,
        trace_id: str,
    ) -> None:
        """将 Issue 置为配置的目标状态，并置 delegate 为 bot 用户。

        状态变更受 LINEAR_ISSUE_START_STATE 配置控制：
        - 配置了状态名 → 按名称精确匹配，找到则更新，找不到则不改状态
        - 未配置 → 不改状态，只设置 delegate

        Args:
            client: LinearClient 实例
            issue_id: Linear Issue UUID
            workspace_id: Linear workspace ID
            trace_id: 追踪 ID
        """
        try:
            issue = await client.get_issue(issue_id)
            team_id = issue.get("team", {}).get("id")
            if not team_id:
                return

            app_user_id = self.token_store.get_app_user_id(workspace_id)
            update_kwargs: Dict[str, Any] = {}

            # 按配置的状态名更新，未配置则不改状态
            start_state_name = self.config.get(
                "issue_start_state", ""
            ) or os.environ.get("LINEAR_ISSUE_START_STATE", "")
            if start_state_name:
                state_id = await client.get_state_id_by_name(team_id, start_state_name)
                if state_id:
                    update_kwargs["state_id"] = state_id
                else:
                    logger.warning(
                        f"[{trace_id}][Linear] State '{start_state_name}' not found in team, skipping state update"
                    )

            if app_user_id:
                update_kwargs["delegate_id"] = app_user_id
            if update_kwargs:
                await client.update_issue(issue_id, **update_kwargs)
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to set issue in-progress",
                exc_info=True,
            )

    # ── 辅助方法 ──────────────────────────────────────────────────────────────

    def _get_token(self, workspace_id: str) -> Optional[str]:
        """获取 workspace 对应的 access token。

        Args:
            workspace_id: Linear workspace ID，空字符串时取第一个已安装的 workspace

        Returns:
            access token 或 None
        """
        if workspace_id:
            return self.token_store.get_token(workspace_id)
        ws_id = self.token_store.get_first_workspace_id()
        return self.token_store.get_token(ws_id) if ws_id else None

    async def _trigger_code_fix(
        self,
        session_id: str,
        result_text: str,
        workspace_id: str,
        trace_id: str,
        client: "LinearClient",
    ) -> None:
        """诊断为代码问题后，自动发起 code-fix 调用并将结果回写 Linear。

        Args:
            session_id: Linear AgentSession ID
            result_text: issue-diagnosis 的诊断结论，作为 code-fix 的上下文
            workspace_id: Linear workspace ID
            trace_id: 追踪 ID
            client: LinearClient 实例
        """
        logger.info(f"[{trace_id}][Linear] Code issue detected, triggering code-fix")
        try:
            await client.send_thought(session_id, "检测到代码问题，正在自动修复...")
        except Exception:
            pass

        fix_result = ""
        fix_error = ""
        try:
            from api.models.requests import QueryRequest

            # 将诊断结论作为上下文，指定使用 code-fix skill
            request = QueryRequest(
                prompt=result_text,
                skill="code-fix",
                language="中文",
            )
            async for event in self.agent_service.process_query(request):
                event_type = event.get("type") or event.get("event", "")
                data = event.get("data", {})
                if isinstance(data, str):
                    import json

                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                if event_type == "result":
                    fix_result = data.get("result", "") or data.get("content", "")
                elif event_type == "assistant_message":
                    text = data.get("content", "")
                    if text:
                        try:
                            await client.send_thought(session_id, text[:300])
                        except Exception:
                            pass
                elif event_type == "error":
                    fix_error = data.get("error", "") or str(data)
        except Exception as e:
            fix_error = str(e)
            logger.error(
                f"[{trace_id}][Linear] code-fix AgentService call failed: {e}",
                exc_info=True,
            )

        try:
            if fix_error:
                await client.send_response(session_id, f"自动修复失败：{fix_error}")
            elif fix_result:
                await client.send_response(session_id, fix_result)
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send code-fix result", exc_info=True
            )
