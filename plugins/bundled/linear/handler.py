"""Linear Agent 简洁版事件处理器。

created 事件：直接将 issue 信息拼成 prompt 调用 AgentService，结果回写 Linear Activity。
prompted 事件：暂不支持续接，返回提示。
stopped 事件：记录日志（当前调用为一次性，无需取消）。
"""

import asyncio
import logging
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
            # 人工修复单分流：带 autofix label 的单 → 直接登记并开修，跳过普通 skill 自选。
            handled = False
            if issue_id:
                try:
                    handled = await self._try_manual_repair(
                        session_id=session_id,
                        issue_id=issue_id,
                        workspace_id=workspace_id,
                        trace_id=trace_id,
                    )
                except Exception:
                    logger.error(
                        f"[{trace_id}][Linear] manual repair dispatch failed, "
                        f"fall back to normal flow",
                        exc_info=True,
                    )
                    # 异常发生时修复可能已部分完成（如代码已提交但存库失败），
                    # 检查 store 避免重复触发修复流程。
                    try:
                        from plugins.bundled.repair.coordinator import get_coordinator
                        from plugins.bundled.repair.store import Stage
                        _coordinator = get_coordinator()
                        if _coordinator is not None:
                            _run = _coordinator.store.get(issue_id)
                            if _run is not None and _run.stage != Stage.PENDING_REVIEW:
                                logger.info(
                                    f"[{trace_id}][Linear] repair run exists "
                                    f"(stage={_run.stage}), suppressing fallback"
                                )
                                handled = True
                    except Exception:
                        pass
            if handled:
                return

            await self._process(
                session_id=session_id,
                issue_id=issue_id,
                prompt_context=prompt_context,
                workspace_id=workspace_id,
                trace_id=trace_id,
            )
        finally:
            self._active_sessions.discard(session_id)

    async def _classify_is_repair(self, description: str) -> bool:
        """调 AgentService 判断 issue 是否「要改代码的 bug」。拿不准默认 True。

        失败（异常/空结果）时默认 True，倒向修复（用户决策）。
        """
        from plugins.bundled.repair import prompts

        try:
            from api.models.requests import QueryRequest

            request = QueryRequest(
                prompt=prompts.build_classify_prompt(description),
                language="中文",
            )
            result_text = ""
            async for event in self.agent_service.process_query(request):
                etype = event.get("type") or event.get("event", "")
                data = event.get("data", {})
                if isinstance(data, str):
                    import json

                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                if etype == "result":
                    result_text = data.get("result", "") or data.get("content", "")
            return prompts.parse_is_code_bug(result_text)
        except Exception:
            logger.warning("[Linear] classify_is_repair failed, default to repair", exc_info=True)
            return True

    async def _try_manual_repair(
        self,
        session_id: str,
        issue_id: str,
        workspace_id: str,
        trace_id: str,
    ) -> bool:
        """人工修复单分流。

        @agent 关联到 issue 触发 created → 先分类判断是否「要改代码的 bug」，
        是则直接登记 RepairRun 并调 coordinator.start_manual_repair（created 即开修，
        不经审核门）。返回 True 表示已拦截（调用方不再走普通 skill 自选流程）。

        - repair 插件未启用（coordinator=None）→ 返回 False（走普通流程）。
        - 分类判为非代码 bug（咨询/诊断）→ 返回 False（走普通流程）。
        - 判为代码 bug → 登记 run + 开修，返回 True。repo 从描述解析，
          解析不到留空，由 bug-fix-developer 从描述识别服务名再查表（agent 兜底）。
        """
        try:
            from plugins.bundled.repair.coordinator import get_coordinator
            from plugins.bundled.repair import prompts
            from plugins.bundled.repair.store import RepairRun, Stage
        except Exception:
            logger.debug("[Linear] repair plugin unavailable, skip manual repair", exc_info=True)
            return False

        coordinator = get_coordinator()
        if coordinator is None:
            return False

        token = self._get_token(workspace_id)
        if not token:
            return False
        client = LinearClient(token)

        issue = await client.get_issue(issue_id)
        identifier = issue.get("identifier", "")
        description = issue.get("description", "") or ""
        state = issue.get("state") or {}
        state_type = state.get("type", "")
        state_name = state.get("name", "") or state_type

        # 幂等门 1（Linear 状态，跨进程持久）：开修会把单推到 started，
        # 故已在处理/已完成/已终止的单再次被 @agent 时直接跳过，回会话提示。
        if not prompts.is_repairable_state(state_type):
            logger.info(
                f"[{trace_id}][Linear] {identifier} state={state_name} "
                f"(type={state_type or '空'}) not repairable, skip"
            )
            # 把新的 linear_session_id 绑定到已有 claude_session_id，供后续 prompted 续接
            prev_linear_session_id = self.token_store.get_latest_session_by_issue(issue_id)
            if prev_linear_session_id and session_id and session_id != prev_linear_session_id:
                prev_claude_session_id = self.token_store.get_session(prev_linear_session_id)
                if prev_claude_session_id:
                    self.token_store.save_session(session_id, issue_id, prev_claude_session_id)
                    logger.info(
                        f"[{trace_id}][Linear] re-mapped session: {session_id} -> {prev_claude_session_id}"
                    )
            try:
                await client.send_response(
                    session_id,
                    f"该单当前状态「{state_name}」已在修复流程中或已处理，跳过重复触发。",
                )
            except Exception:
                pass
            return True

        # 幂等门 2（本地 store，防状态尚未翻转时的并发重复 created）：
        # 已有 run 且 stage 已推进出 PENDING_REVIEW，说明流水线在跑，跳过。
        existing = coordinator.store.get(issue_id)
        if existing is not None and existing.stage != Stage.PENDING_REVIEW:
            logger.info(
                f"[{trace_id}][Linear] {identifier} run exists stage={existing.stage}, skip"
            )
            # 把新的 linear_session_id 绑定到已有 claude_session_id，供后续 prompted 续接
            prev_linear_session_id = self.token_store.get_latest_session_by_issue(issue_id)
            if prev_linear_session_id and session_id and session_id != prev_linear_session_id:
                prev_claude_session_id = self.token_store.get_session(prev_linear_session_id)
                if prev_claude_session_id:
                    self.token_store.save_session(session_id, issue_id, prev_claude_session_id)
                    logger.info(
                        f"[{trace_id}][Linear] re-mapped session: {session_id} -> {prev_claude_session_id}"
                    )
            try:
                await client.send_response(
                    session_id, "该单已在修复流程中，跳过重复触发。"
                )
            except Exception:
                pass
            return True

        # 分类：这是不是一个要改代码的 bug？否则走普通流程（诊断/咨询）。
        is_repair = await self._classify_is_repair(description)
        if not is_repair:
            logger.info(
                f"[{trace_id}][Linear] {identifier} classified as non-code-bug, fall through"
            )
            return False

        # repo 标签能解析到就用；解析不到留空，由 bug-fix-developer 从描述
        # 识别服务名再查 service-repo-map 表（agent 兜底）。
        repo = prompts.parse_repo_from_description(description)

        try:
            await client.send_thought(session_id, "已识别为代码修复任务，正在准备修复...")
        except Exception:
            pass

        # 登记 RepairRun（挂到现有单，主键为 issue UUID，幂等 upsert）
        coordinator.store.upsert(
            RepairRun(
                linear_issue_id=issue_id,
                linear_identifier=identifier,
                workspace_id=workspace_id or "",
                stage=Stage.PENDING_REVIEW,
                repo=repo,
                root_cause="（人工单未单列根因，按修复描述处理）",
                repair_plan=description,
                linear_session_id=session_id or "",
            )
        )
        logger.info(
            f"[{trace_id}][Linear] manual repair registered: {identifier} "
            f"repo={repo or '(待 agent 从描述识别)'}, starting"
        )
        await coordinator.start_manual_repair(issue_id, session_id=session_id)
        return True

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

        issue_id = agent_session.get("issueId")
        trace_id = _new_trace_id()
        # 优先按 linear_session_id 查对应的 claude_session_id
        claude_session_id = self.token_store.get_session(session_id) if session_id else None
        logger.info(
            f"[{trace_id}][Linear] prompted: linear_session={session_id}, issue={issue_id}, claude_session={claude_session_id}"
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

            # 修复流水线中的 issue（BUILDING/REJECTED）→ 强制走 bug-fix-developer
            # 注入 issue_id，让 agent 能调 cli.py retrigger-build --issue <id>
            # PENDING_RERUN → 用户确认重修，直接调 coordinator.confirm_rerun
            actual_prompt = prompt_context
            if issue_id:
                try:
                    from plugins.bundled.repair.coordinator import get_coordinator
                    from plugins.bundled.repair.store import Stage
                    _coordinator = get_coordinator()
                    if _coordinator is not None:
                        _run = _coordinator.store.get(issue_id)
                        if _run is not None and _run.stage == Stage.PENDING_RERUN:
                            _confirm_keywords = ("确认重修", "确认", "继续", "重修", "yes", "确定")
                            if any(kw in prompt_context for kw in _confirm_keywords):
                                await _coordinator.confirm_rerun(issue_id, session_id)
                                return
                            else:
                                await client.send_response(
                                    session_id,
                                    "等待您确认是否继续重修，请回复「确认重修」后继续，或回复其他内容取消。"
                                )
                                return
                        elif _run is not None and _run.stage in (Stage.BUILDING, Stage.REJECTED):
                            actual_prompt = (
                                f"严格按 skill: bug-fix-developer 执行任务。\n\n"
                                f"Issue UUID: {issue_id}\n"
                                f"Issue 单号: {_run.linear_identifier}\n"
                                f"当前 stage: {_run.stage}\n\n"
                                f"用户消息: {prompt_context}"
                            )
                except Exception:
                    pass

            request = QueryRequest(
                prompt=actual_prompt,
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
                elif event_type == "result":
                    result_text = data.get("result", "") or data.get("content", "")
                elif event_type == "error":
                    error_text = data.get("error", "") or str(data)

            if new_claude_session_id and session_id and issue_id:
                self.token_store.save_session(session_id, issue_id, new_claude_session_id)
                # 同步更新 repair_runs 最新 linear_session_id
                try:
                    from plugins.bundled.repair.coordinator import get_coordinator
                    _coordinator = get_coordinator()
                    if _coordinator is not None and _coordinator.store.get(issue_id):
                        _coordinator.store.update(issue_id, linear_session_id=session_id)
                except Exception:
                    pass

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

    async def handle_issue_event(self, payload: Dict[str, Any]) -> None:
        """处理 Issue 状态变更/分配事件，审核通过则委派 RepairCoordinator。

        当 Issue 新状态为「审核通过」（如 In Progress）时，触发自动开发。
        软依赖 repair 插件：未启用时 get_coordinator() 返回 None，直接跳过。

        Args:
            payload: Linear Webhook 原始 payload（type=Issue）
        """
        data = payload.get("data", {})
        issue_id = data.get("id", "")
        state = data.get("state", {}) or {}
        state_name = state.get("name", "")

        if not issue_id:
            return

        try:
            from plugins.bundled.repair.coordinator import get_coordinator
            from plugins.bundled.repair import prompts
        except Exception:
            # repair 插件未启用（或其模块导入报错），忽略 Issue 事件
            logger.debug("[Linear] repair plugin unavailable, skip Issue event", exc_info=True)
            return

        coordinator = get_coordinator()
        if coordinator is None:
            return

        if not prompts.is_approval_state(state_name):
            logger.info(
                "[Linear] Issue %s state=%s not approval, ignore", issue_id, state_name
            )
            return

        logger.info(
            "[Linear] Issue %s approved (state=%s), triggering development",
            issue_id,
            state_name,
        )
        try:
            await coordinator.start_development(issue_id)
        except Exception:
            logger.error(
                "[Linear] start_development failed for %s", issue_id, exc_info=True
            )

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

            # 先查持久化，有则续接已有 Claude session（多轮对话）
            existing_claude_session_id = self.token_store.get_session(session_id) if session_id else None
            request = QueryRequest(
                prompt=final_prompt,
                language="中文",
                session_id=existing_claude_session_id,
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
                    # 持久化 linear_session_id -> claude_session_id 映射，供 prompted 续接
                    claude_session_id = data.get("session_id")
                    if claude_session_id and session_id and issue_id:
                        self.token_store.save_session(session_id, issue_id, claude_session_id)
                        logger.info(
                            f"[{trace_id}][Linear] session mapped: {session_id} -> {claude_session_id}"
                        )
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

        logger.info(f"[{trace_id}][Linear] Completed: session={session_id}")

    async def _set_issue_in_progress(
        self,
        client: LinearClient,
        issue_id: str,
        workspace_id: str,
        trace_id: str,
    ) -> None:
        """将 Issue 置为第一个 started 状态，并置 delegate 为 bot 用户。

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
            started_state_id = await client.get_team_first_started_state_id(team_id)

            update_kwargs: Dict[str, Any] = {}
            if started_state_id:
                update_kwargs["state_id"] = started_state_id
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
