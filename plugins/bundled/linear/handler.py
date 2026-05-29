"""Linear Agent session handler — core business logic."""

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from api.constants import AGENT_CWD
from api.services.agent_service import AgentService

from plugins.bundled.linear.linear_client import LinearClient, LinearAPIError
from plugins.bundled.linear.token_store import TokenStore
from plugins.bundled.linear.workflow_orchestrator import WorkflowOrchestrator

logger = logging.getLogger(__name__)


def _new_trace_id() -> str:
    return uuid.uuid4().hex[:8]


_STATE_STARTED = "需求编写完成"  # 阶段 A/B 完成后子 Issue 目标状态
_STATE_REVIEW = "需求编写完成"  # PRD 回填后状态（与阶段 A 相同，已确认）

# Linear plan 固定 4 步（显示用）
_PLAN_INIT = [
    {"content": "① 需求分析", "status": "inProgress"},
    {"content": "② 本体映射", "status": "pending"},
    {"content": "③/④ 检查与设计", "status": "pending"},
    {"content": "⑤ 生成 PRD", "status": "pending"},
]

# 步骤标签 → plan index 映射
_STEP_PLAN_INDEX = {
    "① 需求分析": 0,
    "② 本体映射": 1,
    "② 本体映射（lite）": 1,
    "③ 本体检查": 2,
    "④ 页面设计": 2,
    "⑤ 生成 PRD": 3,
}


class LinearSessionHandler:
    """处理 Linear AgentSession 事件，驱动 product-workflow 并回写 Activity。"""

    def __init__(
        self,
        agent_service: AgentService,
        token_store: TokenStore,
        config: Dict[str, Any],
    ):
        self.agent_service = agent_service
        self.token_store = token_store
        self.config = config
        # 基于 AGENT_CWD 解析为绝对路径，避免相对路径依赖进程 cwd
        _prd_root = Path(config.get("prd_output_root", "data/linear/prd"))
        self.prd_output_root = (
            _prd_root if _prd_root.is_absolute() else AGENT_CWD / _prd_root
        )
        # 取消标志：session_id → asyncio.Event
        self._cancel_flags: Dict[str, asyncio.Event] = {}
        # 等待人工介入：linear_session_id → asyncio.Future（用户 prompted 回复）
        self._pending_human: Dict[str, asyncio.Future] = {}

    # ── 公共入口 ─────────────────────────────────────────────────────────────

    async def handle_created(self, payload: Dict[str, Any]) -> None:
        """处理 AgentSession created 事件（新会话）。"""
        agent_session = payload.get("agentSession", {})
        session_id = agent_session.get("id")
        issue_id = agent_session.get("issueId")
        prompt_context = payload.get("promptContext", "")
        if not prompt_context:
            prompt_context = agent_session.get("issue", {}).get("description", "")
        workspace_id = payload.get("organizationId", "")

        if not session_id:
            logger.error("[Linear] handle_created: missing session_id")
            return

        trace_id = _new_trace_id()
        cancel_event = asyncio.Event()
        self._cancel_flags[session_id] = cancel_event

        token = self._get_token(workspace_id)
        if not token:
            logger.error(f"[{trace_id}][Linear] No token for workspace: {workspace_id}")
            return

        client = LinearClient(token)

        # 判断是否子 Issue（父 Issue 有特性清单产物）
        parent_context = await self._find_parent_context(client, issue_id, trace_id)

        try:
            if parent_context:
                logger.info(
                    f"[{trace_id}][Linear] Sub-issue detected: issue={issue_id}, "
                    f"parent_dir={parent_context['output_dir'].name}"
                )
                await self._process_sub_issue_session(
                    session_id=session_id,
                    issue_id=issue_id,
                    workspace_id=workspace_id,
                    cancel_event=cancel_event,
                    client=client,
                    parent_context=parent_context,
                    trace_id=trace_id,
                )
            else:
                logger.info(f"[{trace_id}][Linear] Parent issue flow: issue={issue_id}")
                await self._process_session(
                    session_id=session_id,
                    issue_id=issue_id,
                    prompt=prompt_context,
                    workspace_id=workspace_id,
                    cancel_event=cancel_event,
                    client=client,
                    trace_id=trace_id,
                )
        finally:
            self._cancel_flags.pop(session_id, None)

    async def handle_prompted(self, payload: Dict[str, Any]) -> None:
        """处理 AgentSession prompted 事件（用户追加消息）。"""
        session_id = payload.get("agentSession", {}).get("id")
        user_prompt = (
            payload.get("agentActivity", {}).get("content", {}).get("body", "")
        )
        workspace_id = payload.get("organizationId", "")

        if not session_id or not user_prompt:
            return

        # 优先：如果有等待人工介入的 Future，resolve 它
        fut = self._pending_human.get(session_id)
        if fut and not fut.done():
            fut.set_result(user_prompt)
            logger.info(f"[Linear] Human reply resolved: session={session_id}")
            return

        # 否则：普通追加消息，暂不支持续接编排流程
        token = self._get_token(workspace_id)
        if not token:
            logger.error(f"[Linear] No token for workspace: {workspace_id}")
            return

        client = LinearClient(token)
        try:
            await client.send_response(
                session_id,
                "当前工作流已完成或未在运行中，如需重新分析请重新分配 Issue 给 Agent。",
            )
        except Exception:
            logger.warning("[Linear] Failed to send prompted reply", exc_info=True)

    async def handle_stopped(self, payload: Dict[str, Any]) -> None:
        """处理 stop 信号，取消正在运行的 session。"""
        session_id = payload.get("agentSession", {}).get("id")
        workspace_id = payload.get("organizationId", "")

        if not session_id:
            return

        cancel_event = self._cancel_flags.get(session_id)
        if cancel_event:
            cancel_event.set()
            logger.info(f"[Linear] Stop signal received: session={session_id}")

        token = self._get_token(workspace_id)
        if token:
            client = LinearClient(token)
            try:
                await client.send_response(session_id, "已收到停止指令，操作已中止。")
            except Exception:
                logger.warning(
                    "[Linear] Failed to send stop confirmation", exc_info=True
                )

    # ── 核心处理流程 ──────────────────────────────────────────────────────────

    async def _process_session(
        self,
        session_id: str,
        issue_id: Optional[str],
        prompt: str,
        workspace_id: str,
        cancel_event: asyncio.Event,
        client: LinearClient,
        trace_id: str,
    ) -> None:
        app_user_id = self.token_store.get_app_user_id(workspace_id)

        try:
            await client.send_thought(
                session_id, "已收到需求，正在启动产品工作流分析..."
            )
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send initial thought", exc_info=True
            )

        if issue_id:
            await self._setup_issue(client, issue_id, app_user_id, trace_id)

        issue_identifier = await self._get_issue_identifier(client, issue_id, trace_id)
        output_dir = self.prd_output_root / (issue_identifier or session_id[:8])
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[{trace_id}][Linear] Output dir: {output_dir}")

        plan = list(_PLAN_INIT)
        try:
            await client.update_agent_session(session_id, plan=plan)
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to init session plan", exc_info=True
            )

        async def update_plan_step(label: str, status: str) -> None:
            idx = _STEP_PLAN_INDEX.get(label)
            if idx is None:
                return
            plan[idx] = {"content": plan[idx]["content"], "status": status}
            if status == "completed" and idx + 1 < len(plan):
                if plan[idx + 1]["status"] == "pending":
                    plan[idx + 1] = {
                        "content": plan[idx + 1]["content"],
                        "status": "inProgress",
                    }
            try:
                await client.update_agent_session(session_id, plan=list(plan))
            except Exception:
                logger.warning(
                    f"[{trace_id}][Linear] Failed to update plan step={label}",
                    exc_info=True,
                )

        async def wait_for_human(message: str) -> Optional[str]:
            try:
                await client.send_response(session_id, message)
            except Exception:
                logger.warning(
                    f"[{trace_id}][Linear] Failed to send human-wait message",
                    exc_info=True,
                )
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending_human[session_id] = fut
            try:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=1800)
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{trace_id}][Linear] Human wait timeout: session={session_id}"
                )
                return None
            finally:
                self._pending_human.pop(session_id, None)

        orchestrator = WorkflowOrchestrator(
            agent_service=self.agent_service,
            output_dir=output_dir,
            cancel_event=cancel_event,
            on_step_start=lambda label: update_plan_step(label, "inProgress"),
            on_step_done=lambda label, result: update_plan_step(
                label, "completed" if result.success else "canceled"
            ),
            on_tool_use=lambda tool, inp: client.send_action(
                session_id, action=f"调用工具 {tool}", parameter=inp, ephemeral=False
            ),
            on_thought=lambda text: client.send_thought(
                session_id, text, ephemeral=True
            ),
            wait_for_human=wait_for_human,
        )

        orch_result = await orchestrator.run(prompt=prompt, issue_id=issue_identifier)

        if not orch_result.success:
            logger.error(
                f"[{trace_id}][Linear] Orchestrator failed: {orch_result.error}"
            )
            try:
                await client.send_error(
                    session_id, f"产品工作流执行失败：{orch_result.error}"
                )
            except Exception:
                pass
            for i, step in enumerate(plan):
                if step["status"] in ("pending", "inProgress"):
                    plan[i] = {"content": step["content"], "status": "canceled"}
            try:
                await client.update_agent_session(session_id, plan=list(plan))
            except Exception:
                pass
            return

        # 大需求：② 完成后拆子 Issue
        if orch_result.split_required:
            logger.info(f"[{trace_id}][Linear] Split required, creating sub-issues")
            await self._handle_split(
                client=client,
                session_id=session_id,
                issue_id=issue_id,
                output_dir=output_dir,
                app_user_id=app_user_id,
                plan=plan,
                trace_id=trace_id,
            )
            return

        # 小需求：工作流全部完成
        for i in range(len(plan)):
            plan[i] = {"content": plan[i]["content"], "status": "completed"}
        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        await self._trigger_phase2(client, session_id, issue_id, output_dir, trace_id)

        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        try:
            await client.update_agent_session(
                session_id,
                external_urls=[
                    {"label": "查看 PRD 产物", "url": f"file://{output_dir}"}
                ],
            )
        except Exception:
            pass

        prd_count = len(orch_result.prd_files)
        summary = (
            f"产品工作流已完成。\n"
            f"· 执行步骤：{'→'.join(orch_result.steps_executed)}\n"
            f"· 通道：{orch_result.lane}\n"
            f"· PRD 产物：{prd_count} 份\n"
            f"· 输出目录：{output_dir.name}"
        )
        logger.info(f"[{trace_id}][Linear] Workflow completed: {summary}")
        try:
            await client.send_response(session_id, summary)
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send completion summary", exc_info=True
            )

    async def _handle_split(
        self,
        client: LinearClient,
        session_id: str,
        issue_id: Optional[str],
        output_dir: Path,
        app_user_id: Optional[str],
        plan: list,
        trace_id: str,
    ) -> None:
        """大需求：将②产物（特性清单）追加到父 Issue，创建子 Issue（assignee 复用父 Issue，delegate=Agent）。"""
        from plugins.bundled.linear.feature_list_parser import parse_feature_list
        from plugins.bundled.linear.issue_creator import IssueCreator

        # 防递归：如果当前 Issue 本身是子 Issue（有 parent），则不触发 split
        team_id = None
        assignee_id = None
        issue_identifier = None
        parent_priority = 0
        if issue_id:
            try:
                issue_data = await client.get_issue(issue_id)
                team_id = issue_data.get("team", {}).get("id")
                assignee_id = issue_data.get("assigneeId")
                issue_identifier = issue_data.get("identifier")
                parent_priority = issue_data.get("priority", 0)
                # 防递归：当前 Issue 已有 parent，说明是子 Issue，不应再 split
                if issue_data.get("parent"):
                    parent_identifier = issue_data["parent"].get("identifier", "")
                    logger.info(
                        f"[{trace_id}][Linear] Issue {issue_identifier} has parent {parent_identifier}, "
                        f"skipping split to prevent recursion"
                    )
                    # 将 plan 全部置为 completed，继续跑 ③④⑤
                    for i in range(len(plan)):
                        plan[i] = {"content": plan[i]["content"], "status": "completed"}
                    try:
                        await client.update_agent_session(session_id, plan=list(plan))
                    except Exception:
                        pass
                    return
            except Exception:
                logger.warning(
                    f"[{trace_id}][Linear] Failed to get parent issue info",
                    exc_info=True,
                )

        if not team_id:
            logger.error(f"[{trace_id}][Linear] No team_id, cannot create sub-issues")
            try:
                await client.send_error(
                    session_id, "无法获取团队信息，子 Issue 创建失败"
                )
            except Exception:
                pass
            return

        # 将②产物（特性清单）追加到父 Issue 描述
        feature_list_files = list(output_dir.glob("*_特性清单.md"))
        if feature_list_files and issue_id:
            try:
                fl_content = feature_list_files[0].read_text(encoding="utf-8")
                issue_data = await client.get_issue(issue_id)
                current_desc = issue_data.get("description") or ""
                block = "\n\n---特性清单---\n" + fl_content + "\n---特性清单---"
                if "---特性清单---" in current_desc:
                    import re

                    new_desc = re.sub(
                        r"\n\n---特性清单---\n.*?\n---特性清单---",
                        block,
                        current_desc,
                        flags=re.DOTALL,
                    )
                else:
                    new_desc = current_desc + block
                await client.update_issue(issue_id, description=new_desc)
                logger.info(
                    f"[{trace_id}][Linear] Feature list appended to parent issue: {issue_id}"
                )
            except Exception:
                logger.warning(
                    f"[{trace_id}][Linear] Failed to append feature list to parent issue",
                    exc_info=True,
                )

        # 创建子 Issue 骨架（assignee=父 Issue 负责人，delegate=Agent）
        # 超过 3 个子 Issue 时不自动指派给 Agent，由用户手动逐个指派
        _AUTO_DELEGATE_THRESHOLD = 3
        sub_count = 0
        for fl_file in feature_list_files:
            try:
                feature_list = parse_feature_list(str(fl_file))
                # 计算有效特性数量（有本体映射报告的）
                ontology_dir = output_dir / feature_list.ontology_reports_dir
                valid_count = sum(
                    1
                    for feat in feature_list.features
                    if (ontology_dir / f"{feat.id}_本体映射报告.md").exists()
                )
                # 超过阈值则不自动指派 Agent
                effective_app_user_id = (
                    app_user_id if valid_count <= _AUTO_DELEGATE_THRESHOLD else None
                )
                if (
                    effective_app_user_id is None
                    and valid_count > _AUTO_DELEGATE_THRESHOLD
                ):
                    logger.info(
                        f"[{trace_id}][Linear] {valid_count} sub-issues exceed threshold "
                        f"({_AUTO_DELEGATE_THRESHOLD}), skipping auto-delegate"
                    )
                pending_state_id = await client.get_team_state_by_name(
                    team_id, _STATE_STARTED
                )
                creator = IssueCreator(client, str(self.prd_output_root))
                result = await creator.create_skeleton(
                    feature_list=feature_list,
                    req_dir=str(output_dir),
                    team_id=team_id,
                    pending_state_id=pending_state_id or "",
                    assignee_id=assignee_id,
                    app_user_id=effective_app_user_id,
                    source_issue_identifier=issue_identifier,
                    parent_issue_id=issue_id,
                    parent_issue_identifier=issue_identifier,
                    parent_priority=parent_priority,
                )
                sub_count = len(result.get("issues", []))
                logger.info(
                    f"[{trace_id}][Linear] Sub-issues created: "
                    f"parent={result['parent_issue']['identifier']}, count={sub_count}"
                )
            except Exception:
                logger.error(
                    f"[{trace_id}][Linear] Failed to create sub-issues for {fl_file}",
                    exc_info=True,
                )
                try:
                    await client.send_error(session_id, "子 Issue 创建失败，请查看日志")
                except Exception:
                    pass

        # 将 plan 前两步置为 completed，后两步置为 pending（子 Issue 自己跑）
        for i in range(2):
            plan[i] = {"content": plan[i]["content"], "status": "completed"}
        for i in range(2, len(plan)):
            plan[i] = {"content": plan[i]["content"], "status": "pending"}
        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        summary = (
            f"需求分析完成，已拆分为 {sub_count} 个子 Issue。\n"
            f"· 特性清单已追加到当前 Issue\n"
            f"· 每个子 Issue 将独立完成 ③④⑤ 步骤并生成 PRD"
        )
        logger.info(f"[{trace_id}][Linear] Split completed: {summary}")
        try:
            await client.send_response(session_id, summary)
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to send split summary", exc_info=True
            )

    async def _process_sub_issue_session(
        self,
        session_id: str,
        issue_id: Optional[str],
        workspace_id: str,
        cancel_event: asyncio.Event,
        client: LinearClient,
        parent_context: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """子 Issue 流程：从父 Issue 产物目录恢复上下文，跑 ③④⑤。"""
        app_user_id = self.token_store.get_app_user_id(workspace_id)
        parent_output_dir: Path = parent_context["output_dir"]
        feature_id: str = parent_context.get("feature_id", "")

        # 子 Issue trace_id 格式：父trace-featureId
        sub_trace = f"{trace_id}-{feature_id}" if feature_id else trace_id

        try:
            await client.send_thought(
                session_id, f"子需求 {feature_id} 开始处理，跑 ③④⑤ 步骤..."
            )
        except Exception:
            pass

        if issue_id:
            await self._setup_issue(client, issue_id, app_user_id, sub_trace)

        issue_identifier = await self._get_issue_identifier(client, issue_id, sub_trace)
        output_dir = self.prd_output_root / (issue_identifier or session_id[:8])
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[{sub_trace}][Linear] Sub-issue output dir: {output_dir}")

        # 子 Issue plan 只显示 ③④⑤
        plan = [
            {"content": "① 需求分析", "status": "completed"},
            {"content": "② 本体映射", "status": "completed"},
            {"content": "③/④ 检查与设计", "status": "inProgress"},
            {"content": "⑤ 生成 PRD", "status": "pending"},
        ]
        try:
            await client.update_agent_session(session_id, plan=plan)
        except Exception:
            pass

        async def update_plan_step(label: str, status: str) -> None:
            idx = _STEP_PLAN_INDEX.get(label)
            if idx is None:
                return
            plan[idx] = {"content": plan[idx]["content"], "status": status}
            if status == "completed" and idx + 1 < len(plan):
                if plan[idx + 1]["status"] == "pending":
                    plan[idx + 1] = {
                        "content": plan[idx + 1]["content"],
                        "status": "inProgress",
                    }
            try:
                await client.update_agent_session(session_id, plan=list(plan))
            except Exception:
                logger.warning(
                    f"[{sub_trace}][Linear] Failed to update plan step={label}",
                    exc_info=True,
                )

        orchestrator = WorkflowOrchestrator(
            agent_service=self.agent_service,
            output_dir=output_dir,
            cancel_event=cancel_event,
            on_step_start=lambda label: update_plan_step(label, "inProgress"),
            on_step_done=lambda label, result: update_plan_step(
                label, "completed" if result.success else "canceled"
            ),
            on_tool_use=lambda tool, inp: client.send_action(
                session_id, action=f"调用工具 {tool}", parameter=inp, ephemeral=False
            ),
            on_thought=lambda text: client.send_thought(
                session_id, text, ephemeral=True
            ),
        )

        orch_result = await orchestrator.run(
            prompt=(
                f"子需求 {feature_id}，请基于父需求产物完成本体检查和 PRD 生成。\n\n"
                f"**重要约束：**\n"
                f"- 本次只处理特性 `{feature_id}` 的内容\n"
                f"- 目录中的需求分析报告和特性清单仅作为背景上下文，不是本次任务范围\n"
                f"- ③ 只生成 `{feature_id}` 的本体检查报告\n"
                f"- ④ 只生成 `{feature_id}` 的页面设计说明（skill 判断不需要则跳过）\n"
                f"- ⑤ 只生成 `{feature_id}` 的用户故事设计规格说明书"
            ),
            issue_id=issue_identifier,
            start_from_step=3,
            parent_context_dir=parent_output_dir,
            feature_id=feature_id,
        )

        if not orch_result.success:
            logger.error(
                f"[{sub_trace}][Linear] Sub-issue orchestrator failed: {orch_result.error}"
            )
            try:
                await client.send_error(
                    session_id, f"子需求工作流执行失败：{orch_result.error}"
                )
            except Exception:
                pass
            for i, step in enumerate(plan):
                if step["status"] in ("pending", "inProgress"):
                    plan[i] = {"content": step["content"], "status": "canceled"}
            try:
                await client.update_agent_session(session_id, plan=list(plan))
            except Exception:
                pass
            return

        # 全部完成
        for i in range(len(plan)):
            plan[i] = {"content": plan[i]["content"], "status": "completed"}
        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        # PRD 回填到子 Issue
        await self._trigger_phase2(client, session_id, issue_id, output_dir, sub_trace)

        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        prd_count = len(orch_result.prd_files)
        summary = (
            f"子需求 {feature_id} 完成。\n"
            f"· 执行步骤：{'→'.join(orch_result.steps_executed)}\n"
            f"· PRD 产物：{prd_count} 份"
        )
        logger.info(f"[{sub_trace}][Linear] Sub-issue completed: {summary}")
        try:
            await client.send_response(session_id, summary)
        except Exception:
            pass

    # ── 阶段二：PRD 回填 ──────────────────────────────────────────────────────

    async def _trigger_phase2(
        self,
        client: LinearClient,
        session_id: str,
        issue_id: Optional[str],
        output_dir: Path,
        trace_id: str,
    ) -> None:
        """扫描产物目录，触发 PRD 回填（小需求追加到 Issue 描述，大需求子 Issue 走 backfiller）。"""
        from plugins.bundled.linear.prd_backfiller import PRDBackfiller

        team_id = None
        if issue_id:
            try:
                issue_data = await client.get_issue(issue_id)
                team_id = issue_data.get("team", {}).get("id")
            except Exception:
                logger.warning(
                    f"[{trace_id}][Linear] Failed to get team_id from issue",
                    exc_info=True,
                )

        if not team_id:
            logger.warning(f"[{trace_id}][Linear] No team_id, skipping phase 2")
            return

        feature_list_files = list(output_dir.glob("*_特性清单.md"))

        # 子目录模式 PRD 回填（大需求子 Issue）
        prd_dir = output_dir / "prd"
        if prd_dir.exists():
            prd_files = list(prd_dir.glob("*_用户故事设计规格说明书_v*.md"))
            if prd_files:
                review_state_id = await client.get_team_state_by_name(
                    team_id, _STATE_REVIEW
                )
                backfiller = PRDBackfiller(client, str(self.prd_output_root))
                for prd_file in prd_files:
                    try:
                        await backfiller.backfill(
                            prd_file_path=str(prd_file),
                            req_dir=str(output_dir),
                            review_state_id=review_state_id or "",
                        )
                        logger.info(
                            f"[{trace_id}][Linear] PRD backfilled: {prd_file.name}"
                        )
                    except Exception:
                        logger.error(
                            f"[{trace_id}][Linear] Phase B failed for {prd_file}",
                            exc_info=True,
                        )

        # 小需求 PRD 回填：根目录有 PRD 文件且无特性清单，直接追加到原 Issue 描述
        if issue_id and not feature_list_files:
            root_prd_files = list(output_dir.glob("*_用户故事设计规格说明书_v*.md"))
            if root_prd_files:
                prd_file = root_prd_files[0]
                try:
                    import re

                    prd_content = prd_file.read_text(encoding="utf-8")
                    issue_data = await client.get_issue(issue_id)
                    current_desc = issue_data.get("description") or ""
                    prd_block = f"\n\n---PRD文档---\n{prd_content}\n---PRD文档---"
                    if "---PRD文档---" in current_desc:
                        new_desc = re.sub(
                            r"\n\n---PRD文档---\n.*?\n---PRD文档---",
                            prd_block,
                            current_desc,
                            flags=re.DOTALL,
                        )
                    else:
                        new_desc = current_desc + prd_block
                    await client.update_issue(issue_id, description=new_desc)
                    logger.info(
                        f"[{trace_id}][Linear] PRD appended to issue: {issue_id}"
                    )
                except Exception:
                    logger.error(
                        f"[{trace_id}][Linear] Failed to append PRD to issue {issue_id}",
                        exc_info=True,
                    )

        await self._sync_to_git(output_dir, trace_id)

    async def _sync_to_git(self, output_dir: Path, trace_id: str = "") -> None:
        """将产物目录同步到 Git 仓库。"""
        repo_url = os.environ.get("LINEAR_GIT_REPO_URL", "")
        branch = os.environ.get("LINEAR_GIT_BRANCH", "master")
        _local_path = Path(
            os.environ.get("LINEAR_GIT_LOCAL_PATH", "data/linear/git-repo")
        )
        local_path = (
            _local_path if _local_path.is_absolute() else AGENT_CWD / _local_path
        )

        if not repo_url:
            logger.info(
                f"[{trace_id}][Linear] LINEAR_GIT_REPO_URL not set, skipping git sync"
            )
            return

        local_repo = local_path
        try:
            if not (local_repo / ".git").exists():
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "clone",
                    "--branch",
                    branch,
                    repo_url,
                    str(local_repo),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.error(
                        f"[{trace_id}][Linear] Git clone failed: {stderr.decode()}"
                    )
                    return
                for cfg_cmd in [
                    [
                        "git",
                        "-C",
                        str(local_repo),
                        "config",
                        "user.email",
                        "prd-agent@yjcj.online",
                    ],
                    ["git", "-C", str(local_repo), "config", "user.name", "PRD Agent"],
                ]:
                    cfg_proc = await asyncio.create_subprocess_exec(
                        *cfg_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await cfg_proc.communicate()

            import shutil

            dest = local_repo / output_dir.name / "PRD"
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(output_dir), str(dest))

            _RETRY_CMDS = {"pull", "push"}
            _MAX_RETRIES = 3
            _RETRY_DELAY = 5

            git_cmds = [
                ["git", "-C", str(local_repo), "pull", "--rebase", "origin", branch],
                ["git", "-C", str(local_repo), "add", str(dest)],
                [
                    "git",
                    "-C",
                    str(local_repo),
                    "commit",
                    "-m",
                    f"chore: sync prd artifacts {output_dir.name}",
                ],
                ["git", "-C", str(local_repo), "push", "origin", branch],
            ]

            # 为 git 子进程注入代理环境变量（走 mihomo 代理访问 github.com）
            git_env = os.environ.copy()
            _git_proxy = os.environ.get("LINEAR_GIT_PROXY", "http://127.0.0.1:7890")
            if _git_proxy:
                git_env["https_proxy"] = _git_proxy
                git_env["http_proxy"] = _git_proxy

            failed = False
            for cmd in git_cmds:
                op = cmd[3] if len(cmd) > 3 else ""
                is_network_cmd = op in _RETRY_CMDS
                max_attempts = _MAX_RETRIES if is_network_cmd else 1
                for attempt in range(1, max_attempts + 1):
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=git_env,
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        break
                    err_msg = stderr.decode().strip()
                    if attempt < max_attempts:
                        logger.warning(
                            f"[{trace_id}][Linear] Git cmd failed (attempt {attempt}/{max_attempts}), "
                            f"retrying in {_RETRY_DELAY}s: {' '.join(cmd)}: {err_msg}"
                        )
                        await asyncio.sleep(_RETRY_DELAY)
                    else:
                        logger.warning(
                            f"[{trace_id}][Linear] Git cmd failed after {max_attempts} attempts: "
                            f"{' '.join(cmd)}: {err_msg}"
                        )
                        # pull 失败时跳过（网络问题），继续执行 add/commit/push
                        if op == "pull":
                            logger.warning(
                                f"[{trace_id}][Linear] pull failed, skipping and continuing with add/commit/push"
                            )
                        else:
                            failed = True
                        break
                if failed:
                    break

            logger.info(f"[{trace_id}][Linear] Git sync completed: {output_dir.name}")
        except Exception:
            logger.error(f"[{trace_id}][Linear] Git sync failed", exc_info=True)

    # ── 辅助方法 ──────────────────────────────────────────────────────────────

    def _get_token(self, workspace_id: str) -> Optional[str]:
        if workspace_id:
            return self.token_store.get_token(workspace_id)
        ws_id = self.token_store.get_first_workspace_id()
        return self.token_store.get_token(ws_id) if ws_id else None

    async def _find_parent_context(
        self,
        client: LinearClient,
        issue_id: Optional[str],
        trace_id: str,
    ) -> Optional[Dict[str, Any]]:
        """判断是否子 Issue，返回原始需求产物目录和 feature_id，否则返回 None。

        查找逻辑：
        1. 查当前 Issue 是否有 parent
        2. 扫描所有 linear_result.yaml，找到 parent_issue.identifier 匹配的记录
        3. 从记录的 source_issue_identifier 找到原始需求产物目录
        """
        if not issue_id:
            return None
        try:
            issue = await client.get_issue(issue_id)
            parent = issue.get("parent")
            if not parent:
                return None
            parent_identifier = parent.get("identifier")
            if not parent_identifier:
                return None

            # 从 Issue 标题提取 feature_id（格式："{feature_id} {title}"）
            title = issue.get("title", "")
            feature_id = title.split(" ")[0] if title else ""

            # 方法1：通过 linear_result.yaml 找到原始需求产物目录
            import yaml as _yaml

            for result_file in self.prd_output_root.rglob("linear_result.yaml"):
                try:
                    data = _yaml.safe_load(result_file.read_text(encoding="utf-8"))
                    if not data:
                        continue
                    # 检查 parent_issue.identifier 是否匹配
                    if (
                        data.get("parent_issue", {}).get("identifier")
                        == parent_identifier
                    ):
                        source_identifier = data.get("source_issue_identifier")
                        if source_identifier:
                            source_dir = self.prd_output_root / source_identifier
                        else:
                            # 兜底：用 result_file 所在目录
                            source_dir = result_file.parent
                        if source_dir.exists():
                            logger.info(
                                f"[{trace_id}][Linear] Parent context found via linear_result.yaml: "
                                f"parent={parent_identifier}, source_dir={source_dir.name}, feature_id={feature_id}"
                            )
                            return {
                                "output_dir": source_dir,
                                "feature_id": feature_id,
                                "parent_identifier": parent_identifier,
                            }
                except Exception:
                    continue

            # 方法2：直接查 parent_identifier 对应的产物目录（旧逻辑兜底）
            parent_output_dir = self.prd_output_root / parent_identifier
            if parent_output_dir.exists():
                feature_list_files = list(parent_output_dir.glob("*_特性清单.md"))
                if feature_list_files:
                    logger.info(
                        f"[{trace_id}][Linear] Parent context found via dir: "
                        f"parent={parent_identifier}, feature_id={feature_id}"
                    )
                    return {
                        "output_dir": parent_output_dir,
                        "feature_id": feature_id,
                        "parent_identifier": parent_identifier,
                    }

            logger.info(
                f"[{trace_id}][Linear] No parent context found for parent={parent_identifier}, "
                f"treating as new parent issue"
            )
            return None
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to find parent context", exc_info=True
            )
            return None

    async def _setup_issue(
        self,
        client: LinearClient,
        issue_id: str,
        app_user_id: Optional[str],
        trace_id: str = "",
    ) -> None:
        try:
            issue = await client.get_issue(issue_id)
            team_id = issue.get("team", {}).get("id")
            if team_id:
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
                f"[{trace_id}][Linear] Failed to setup issue {issue_id}", exc_info=True
            )

    async def _get_issue_identifier(
        self,
        client: LinearClient,
        issue_id: Optional[str],
        trace_id: str = "",
    ) -> Optional[str]:
        if not issue_id:
            return None
        try:
            issue = await client.get_issue(issue_id)
            return issue.get("identifier")
        except Exception:
            logger.warning(
                f"[{trace_id}][Linear] Failed to get issue identifier", exc_info=True
            )
            return None

    @staticmethod
    def _build_history_prompt(activities: list) -> str:
        lines = []
        for act in activities:
            content = act.get("content", {})
            body = content.get("body", "")
            act_type = content.get("__typename", "")
            if body and act_type in ("AgentActivityPromptContent",):
                lines.append(f"用户：{body}")
            elif body and act_type in ("AgentActivityResponseContent",):
                lines.append(f"Agent：{body}")
        return "\n".join(lines)
