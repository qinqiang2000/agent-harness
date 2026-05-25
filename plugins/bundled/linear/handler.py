"""Linear Agent session handler — core business logic."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from api.constants import AGENT_CWD
from api.services.agent_service import AgentService

from plugins.bundled.linear.linear_client import LinearClient, LinearAPIError
from plugins.bundled.linear.token_store import TokenStore
from plugins.bundled.linear.workflow_orchestrator import WorkflowOrchestrator

logger = logging.getLogger(__name__)

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
        # created 事件的需求内容在顶层 promptContext 字段（XML 格式）
        prompt_context = payload.get("promptContext", "")
        if not prompt_context:
            # 兜底：从 issue.description 取
            prompt_context = agent_session.get("issue", {}).get("description", "")
        workspace_id = payload.get("organizationId", "")

        if not session_id:
            logger.error("[Linear] handle_created: missing session_id")
            return

        cancel_event = asyncio.Event()
        self._cancel_flags[session_id] = cancel_event

        try:
            await self._process_session(
                session_id=session_id,
                issue_id=issue_id,
                prompt=prompt_context,
                workspace_id=workspace_id,
                cancel_event=cancel_event,
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
    ) -> None:
        token = self._get_token(workspace_id)
        if not token:
            logger.error(f"[Linear] No token for workspace: {workspace_id}")
            return

        client = LinearClient(token)
        app_user_id = self.token_store.get_app_user_id(workspace_id)

        # 10 秒内发送 thought，确认收到
        try:
            await client.send_thought(
                session_id, "已收到需求，正在启动产品工作流分析..."
            )
        except Exception:
            logger.warning("[Linear] Failed to send initial thought", exc_info=True)

        # 设置 issue 状态为 started，并将自己设为 delegate
        if issue_id:
            await self._setup_issue(client, issue_id, app_user_id)

        # 确定输出目录
        issue_identifier = await self._get_issue_identifier(client, issue_id)
        output_dir = self.prd_output_root / (issue_identifier or session_id[:8])
        output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化 plan（4 步固定显示）
        plan = list(_PLAN_INIT)
        try:
            await client.update_agent_session(session_id, plan=plan)
        except Exception:
            logger.warning("[Linear] Failed to init session plan", exc_info=True)

        # 构建 plan 更新辅助函数
        async def update_plan_step(label: str, status: str) -> None:
            idx = _STEP_PLAN_INDEX.get(label)
            if idx is None:
                return
            plan[idx] = {"content": plan[idx]["content"], "status": status}
            # 将下一步设为 inProgress（如果还是 pending）
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
                    f"[Linear] Failed to update plan step={label}", exc_info=True
                )

        # 构建等待人工介入的协程
        async def wait_for_human(message: str) -> Optional[str]:
            try:
                await client.send_response(session_id, message)
            except Exception:
                logger.warning(
                    "[Linear] Failed to send human-wait message", exc_info=True
                )
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending_human[session_id] = fut
            try:
                # 最多等待 30 分钟
                return await asyncio.wait_for(asyncio.shield(fut), timeout=1800)
            except asyncio.TimeoutError:
                logger.warning(f"[Linear] Human wait timeout: session={session_id}")
                return None
            finally:
                self._pending_human.pop(session_id, None)

        # 实例化编排器
        orchestrator = WorkflowOrchestrator(
            agent_service=self.agent_service,
            output_dir=output_dir,
            cancel_event=cancel_event,
            on_step_start=lambda label: update_plan_step(label, "inProgress"),
            on_step_done=lambda label, result: update_plan_step(
                label, "completed" if result.success else "canceled"
            ),
            on_tool_use=lambda tool, inp: client.send_action(
                session_id,
                action=f"调用工具 {tool}",
                parameter=inp,
                ephemeral=False,
            ),
            on_thought=lambda text: client.send_thought(
                session_id, text, ephemeral=True
            ),
            wait_for_human=wait_for_human,
        )

        # 运行编排器
        orch_result = await orchestrator.run(prompt=prompt, issue_id=issue_identifier)

        if not orch_result.success:
            logger.error(f"[Linear] Orchestrator failed: {orch_result.error}")
            try:
                await client.send_error(
                    session_id, f"产品工作流执行失败：{orch_result.error}"
                )
            except Exception:
                pass
            # 将未完成步骤标记为 canceled
            for i, step in enumerate(plan):
                if step["status"] in ("pending", "inProgress"):
                    plan[i] = {"content": step["content"], "status": "canceled"}
            try:
                await client.update_agent_session(session_id, plan=list(plan))
            except Exception:
                pass
            return

        # 工作流成功，将所有步骤置为 completed
        for i in range(len(plan)):
            plan[i] = {"content": plan[i]["content"], "status": "completed"}
        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        # 阶段二：扫描产物，触发 Issue 创建和 PRD 回填
        await self._trigger_phase2(client, session_id, issue_id, output_dir)

        # 阶段二完成，更新 plan 全部完成（_trigger_phase2 可能修改 plan）
        try:
            await client.update_agent_session(session_id, plan=list(plan))
        except Exception:
            pass

        # 更新 externalUrls
        try:
            await client.update_agent_session(
                session_id,
                external_urls=[
                    {"label": "查看 PRD 产物", "url": f"file://{output_dir}"}
                ],
            )
        except Exception:
            pass

        # 发送完成摘要
        prd_count = len(orch_result.prd_files)
        summary = (
            f"产品工作流已完成。\n"
            f"· 执行步骤：{'→'.join(orch_result.steps_executed)}\n"
            f"· 通道：{orch_result.lane}\n"
            f"· PRD 产物：{prd_count} 份\n"
            f"· 输出目录：{output_dir.name}"
        )
        try:
            await client.send_response(session_id, summary)
        except Exception:
            logger.warning("[Linear] Failed to send completion summary", exc_info=True)

    # ── 阶段二：Issue 创建 + PRD 回填 ────────────────────────────────────────

    async def _trigger_phase2(
        self,
        client: LinearClient,
        session_id: str,
        issue_id: Optional[str],
        output_dir: Path,
    ) -> None:
        """扫描产物目录，触发阶段 A（骨架创建）和阶段 B（PRD 回填）。"""
        # 延迟导入，避免循环依赖
        from plugins.bundled.linear.feature_list_parser import parse_feature_list
        from plugins.bundled.linear.issue_creator import IssueCreator
        from plugins.bundled.linear.prd_backfiller import PRDBackfiller

        # 获取 team_id
        team_id = None
        if issue_id:
            try:
                issue_data = await client.get_issue(issue_id)
                team_id = issue_data.get("team", {}).get("id")
            except Exception:
                logger.warning(
                    "[Linear] Failed to get team_id from issue", exc_info=True
                )

        if not team_id:
            logger.warning("[Linear] No team_id, skipping phase 2")
            return

        # 查找特性清单文件（stage: confirmed）
        feature_list_files = list(output_dir.glob("*_特性清单.md"))
        for fl_file in feature_list_files:
            try:
                feature_list = parse_feature_list(str(fl_file))
                if feature_list.stage != "confirmed":
                    continue

                await client.send_thought(
                    session_id, f"正在创建 Linear Issue 骨架：{feature_list.title}"
                )

                creator = IssueCreator(client, str(self.prd_output_root))
                pending_state_id = await client.get_team_state_by_name(
                    team_id, _STATE_STARTED
                )
                result = await creator.create_skeleton(
                    feature_list=feature_list,
                    req_dir=str(output_dir),
                    team_id=team_id,
                    pending_state_id=pending_state_id or "",
                )
                await client.send_thought(
                    session_id,
                    f"Issue 骨架创建完成：父 Issue {result['parent_issue']['identifier']}，子 Issue {len(result['issues'])} 个",
                )
            except Exception:
                logger.error(f"[Linear] Phase A failed for {fl_file}", exc_info=True)
                await client.send_error(session_id, f"Issue 骨架创建失败，请查看日志")

        # 查找 PRD 文件，触发阶段 B（子目录模式，大需求）
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
                    except Exception:
                        logger.error(
                            f"[Linear] Phase B failed for {prd_file}", exc_info=True
                        )

        # 小需求 PRD 回填：根目录有 PRD 文件且无特性清单，直接追加到原 Issue 描述
        if issue_id and not feature_list_files:
            root_prd_files = list(output_dir.glob("*_用户故事设计规格说明书_v*.md"))
            if root_prd_files:
                prd_file = root_prd_files[0]
                try:
                    prd_content = prd_file.read_text(encoding="utf-8")
                    issue_data = await client.get_issue(issue_id)
                    current_desc = issue_data.get("description") or ""
                    prd_block_start = "\n\n---PRD文档---\n"
                    prd_block_end = "\n---PRD文档---"
                    prd_block = f"{prd_block_start}{prd_content}{prd_block_end}"
                    # 已有则替换，无则追加
                    if "---PRD文档---" in current_desc:
                        import re

                        new_desc = re.sub(
                            r"\n\n---PRD文档---\n.*?\n---PRD文档---",
                            prd_block,
                            current_desc,
                            flags=re.DOTALL,
                        )
                    else:
                        new_desc = current_desc + prd_block
                    await client.update_issue(issue_id, description=new_desc)
                    logger.info(f"[Linear] PRD appended to issue: {issue_id}")
                except Exception:
                    logger.error(
                        f"[Linear] Failed to append PRD to issue {issue_id}",
                        exc_info=True,
                    )

        # Git 同步
        await self._sync_to_git(output_dir)

    async def _sync_to_git(self, output_dir: Path) -> None:
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
            logger.info("[Linear] LINEAR_GIT_REPO_URL not set, skipping git sync")
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
                    logger.error(f"[Linear] Git clone failed: {stderr.decode()}")
                    return
                # 配置 git user（避免 Author identity unknown）
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

            # 复制产物到仓库：{issue_id}/PRD/
            import shutil

            dest = local_repo / output_dir.name / "PRD"
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(output_dir), str(dest))

            # git add + commit + push（网络操作带重试）
            _RETRY_CMDS = {"pull", "push"}
            _MAX_RETRIES = 3
            _RETRY_DELAY = 5  # 秒

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

            failed = False
            for cmd in git_cmds:
                # 判断是否为需要重试的网络操作
                is_network_cmd = len(cmd) > 2 and cmd[2] in _RETRY_CMDS
                max_attempts = _MAX_RETRIES if is_network_cmd else 1

                for attempt in range(1, max_attempts + 1):
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        break
                    err_msg = stderr.decode().strip()
                    if attempt < max_attempts:
                        logger.warning(
                            f"[Linear] Git cmd failed (attempt {attempt}/{max_attempts}), "
                            f"retrying in {_RETRY_DELAY}s: {' '.join(cmd)}: {err_msg}"
                        )
                        await asyncio.sleep(_RETRY_DELAY)
                    else:
                        logger.warning(
                            f"[Linear] Git cmd failed after {max_attempts} attempts: "
                            f"{' '.join(cmd)}: {err_msg}"
                        )
                        failed = True
                        break

                if failed:
                    break

            logger.info(f"[Linear] Git sync completed: {output_dir.name}")
        except Exception:
            logger.error("[Linear] Git sync failed", exc_info=True)

    # ── 辅助方法 ──────────────────────────────────────────────────────────────

    def _get_token(self, workspace_id: str) -> Optional[str]:
        if workspace_id:
            return self.token_store.get_token(workspace_id)
        # 单 workspace 场景：取唯一安装
        ws_id = self.token_store.get_first_workspace_id()
        return self.token_store.get_token(ws_id) if ws_id else None

    async def _setup_issue(
        self,
        client: LinearClient,
        issue_id: str,
        app_user_id: Optional[str],
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
            logger.warning(f"[Linear] Failed to setup issue {issue_id}", exc_info=True)

    async def _get_issue_identifier(
        self,
        client: LinearClient,
        issue_id: Optional[str],
    ) -> Optional[str]:
        if not issue_id:
            return None
        try:
            issue = await client.get_issue(issue_id)
            return issue.get("identifier")
        except Exception:
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
