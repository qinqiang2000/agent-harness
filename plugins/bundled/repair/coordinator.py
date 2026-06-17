"""RepairCoordinator —— 纯编排状态机。

每方法 = 读 store → 调 agent 或 Linear → 写新状态。
N/M 重试由代码硬兜底。通过 module-level singleton 供 linear handler 委派。
"""

import json
import logging
from typing import Callable, Optional

from plugins.bundled.repair import prompts
from plugins.bundled.repair.jenkins_client import JenkinsClient
from plugins.bundled.repair.store import RepairRun, RepairStore, Stage
from plugins.bundled.linear.linear_client import LinearAPIError

logger = logging.getLogger(__name__)


async def _run_agent(
    agent_service,
    prompt: str,
    skill: str,
    session_id: Optional[str],
    on_message: Optional[Callable[[str], "object"]] = None,
    on_session_created: Optional[Callable[[str], "object"]] = None,
) -> tuple[str, Optional[str]]:
    """调 AgentService.process_query，返回 (result_text, claude_session_id)。

    新会话靠 DEFAULT_SKILLS 加载 skill；resume 时传 session_id。
    on_message：每收到一条 assistant_message 中间过程文本就 await 调用一次
    （用于逐步转发到 Linear 会话）；回调异常被吞掉，不影响主流程。
    on_session_created：收到 session_created 事件时立即回调，参数为 claude_session_id，
    用于在会话开始时就持久化映射，无需等流水线结束。
    """
    from api.models.requests import QueryRequest

    request = QueryRequest(
        prompt=prompt,
        language="中文",
        skill=skill if not session_id else None,
        session_id=session_id,
        metadata={"max_turns": 1000},
    )
    result_text = ""
    new_session_id = session_id
    async for event in agent_service.process_query(request):
        etype = event.get("type") or event.get("event", "")
        data = event.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if etype == "session_created":
            new_session_id = data.get("session_id", new_session_id)
            if on_session_created and new_session_id:
                try:
                    await on_session_created(new_session_id)
                except Exception:
                    logger.warning("[Repair] on_session_created callback failed", exc_info=True)
        elif etype == "assistant_message":
            if on_message:
                text = data.get("content", "") or data.get("text", "")
                if text:
                    try:
                        await on_message(text)
                    except Exception:
                        logger.warning("[Repair] on_message callback failed", exc_info=True)
        elif etype == "result":
            result_text = data.get("result", "") or data.get("content", "")
    return result_text, new_session_id


class RepairCoordinator:
    """状态机编排。依赖全部注入，便于测试。"""

    def __init__(
        self,
        agent_service,
        store: RepairStore,
        jenkins: JenkinsClient,
        linear_client_factory: Callable,
        fix_retry_limit: int = 3,
        rediagnose_limit: int = 2,
        mr_builder=None,
        session_saver: Optional[Callable[[str, str], "object"]] = None,
    ):
        self.agent_service = agent_service
        self.store = store
        self.jenkins = jenkins
        self._linear_factory = linear_client_factory
        self.N = fix_retry_limit
        self.M = rediagnose_limit
        if mr_builder is None:
            from plugins.bundled.repair.mr_builder import MRBuilder
            mr_builder = MRBuilder()
        self.mr_builder = mr_builder
        self._session_saver = session_saver

    def _linear(self, workspace_id: str):
        return self._linear_factory(workspace_id)

    async def _notify_run(self, run: RepairRun, client, msg: str) -> None:
        """有 linear_session_id 走会话 send_response，否则 fallback 到 issue 评论。"""
        try:
            if run.linear_session_id:
                await client.send_response(run.linear_session_id, msg)
            else:
                await client.create_comment(run.linear_issue_id, msg)
        except Exception:
            logger.warning("[Repair] _notify_run failed (session=%s)", run.linear_session_id, exc_info=True)

    async def _set_issue_linear_state(self, client, linear_issue_id: str, state_type: str) -> None:
        """把 Linear issue 推到指定 workflow state type 的第一个状态，失败只打警告。"""
        try:
            issue = await client.get_issue(linear_issue_id)
            team_id = (issue.get("team") or {}).get("id")
            if team_id:
                state_id = await self._state_id_by_type(client, team_id, state_type)
                if state_id:
                    await client.update_issue(linear_issue_id, state_id=state_id)
                    logger.info("[Repair] issue %s -> %s state", linear_issue_id, state_type)
        except Exception:
            logger.warning("[Repair] failed to set issue %s state: %s", state_type, linear_issue_id, exc_info=True)

    async def _state_id_by_type(self, client, team_id: str, type_name: str) -> Optional[str]:
        """按 workflow state type（started/completed/canceled）取第一个 stateId。"""
        states = await client.get_workflow_states(team_id)
        matched = [s for s in states if s["type"] == type_name]
        if not matched:
            return None
        return min(matched, key=lambda s: s["position"])["id"]

    # ── 阶段 1：开始开发 ─────────────────────────────────────────────────
    async def start_development(self, linear_issue_id: str) -> None:
        """pending_review + 审核通过 → developing → 调 developer → building → 触发 Jenkins。"""
        run = self.store.get(linear_issue_id)
        if not run:
            logger.warning("[Repair] start_development: run not found %s", linear_issue_id)
            return
        if run.stage != Stage.PENDING_REVIEW:
            logger.info(
                "[Repair] start_development skip: %s stage=%s (not pending_review)",
                linear_issue_id,
                run.stage,
            )
            return
        await self._develop_and_build(run, on_agent_failure=Stage.PENDING_REVIEW)

    async def start_manual_repair(
        self, linear_issue_id: str, session_id: Optional[str] = None
    ) -> None:
        """人工修复单：created 即开修，不经审核门。

        handler 已先 upsert 一条带 repo+repair_plan 的 run（stage=PENDING_REVIEW）。
        与 start_development 的差异：
        - 入口门只挡「已在流水线中」的 run（building/developing/...）以幂等，
          不要求审核通过；
        - agent 失败时落可见终态 REJECTED（人工单无审核态可退），不静默卡死。

        session_id：created 事件的 Linear AgentSession ID。传入时把开发过程/结果
        写回该会话（中间步骤 send_thought、最终 send_response），而非 issue 评论。
        """
        run = self.store.get(linear_issue_id)
        if not run:
            logger.warning("[Repair] start_manual_repair: run not found %s", linear_issue_id)
            return
        if run.stage != Stage.PENDING_REVIEW:
            logger.info(
                "[Repair] start_manual_repair skip: %s stage=%s (already in pipeline)",
                linear_issue_id,
                run.stage,
            )
            return
        await self._develop_and_build(
            run, on_agent_failure=Stage.REJECTED, session_id=session_id
        )

    async def _develop_and_build(
        self,
        run: RepairRun,
        on_agent_failure: str,
        session_id: Optional[str] = None,
    ) -> None:
        """共用：developing → 调 developer → building → 触发 Jenkins → 回写。

        Args:
            run: 当前 RepairRun（stage 已确认为 PENDING_REVIEW）
            on_agent_failure: developer agent 抛错时落到的 stage
                （start_development 回退 PENDING_REVIEW；人工单落 REJECTED）
            session_id: Linear AgentSession ID。传入时开发过程/结果写回会话
                （中间 send_thought、最终 send_response），否则走 issue 评论。
        """
        linear_issue_id = run.linear_issue_id
        client = self._linear(run.workspace_id)

        async def notify(body: str, *, final: bool = False) -> None:
            """把消息写回 Linear：有 session 走会话（thought/response），否则走 issue 评论。"""
            try:
                if session_id:
                    if final:
                        await client.send_response(session_id, body)
                    else:
                        await client.send_thought(session_id, body)
                else:
                    await client.create_comment(linear_issue_id, body)
            except Exception:
                logger.warning("[Repair] notify failed (session=%s)", session_id, exc_info=True)

        self.store.update(linear_issue_id, stage=Stage.DEVELOPING)

        # 把 Linear issue 状态推到第一个 started 状态，防止重复触发
        await self._set_issue_linear_state(client, linear_issue_id, "started")

        branch = run.branch or f"fix_{run.linear_identifier}"

        prompt = prompts.build_developer_prompt(
            issue_id=run.linear_issue_id,
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence=run.evidence or run.last_report or "（见 Linear 单描述）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=branch,
            is_retry=False,
            last_report="",
            repos=json.loads(run.repos) if run.repos else None,
        )

        # 有会话时，把 developer 每步中间输出转成会话 thought（逐步可见）。
        on_message = (lambda text: notify(text)) if session_id else None

        # session_created 时立即持久化 issue -> claude_session_id 映射，
        # 供后续 prompted 事件续接多轮对话，无需等流水线结束。
        async def _on_session_created(claude_sid: str) -> None:
            if self._session_saver:
                try:
                    await self._session_saver(linear_issue_id, claude_sid)
                except Exception:
                    logger.warning("[Repair] session_saver failed", exc_info=True)

        try:
            result_text, claude_session_id = await _run_agent(
                self.agent_service,
                prompt,
                skill="bug-fix-developer",
                session_id=None,
                on_message=on_message,
                on_session_created=_on_session_created,
            )
        except Exception:
            logger.error("[Repair] developer agent failed: %s", linear_issue_id, exc_info=True)
            self.store.update(linear_issue_id, stage=on_agent_failure)
            self.store.release_repos(linear_issue_id)  # 开发异常：还锁（若已占）
            # agent 抛异常：人工单落 canceled，审核单退回 backlog
            if on_agent_failure == Stage.REJECTED:
                await self._set_issue_linear_state(client, linear_issue_id, "canceled")
            else:
                await self._set_issue_linear_state(client, linear_issue_id, "backlog")
            fail_msg = (
                "⚠️ 自动开发启动失败，已退回待审核，请重新触发或人工介入。"
                if on_agent_failure == Stage.PENDING_REVIEW
                else "🚫 自动修复启动失败（开发阶段异常），已转人工，请人工介入。"
            )
            await notify(fail_msg, final=True)
            return

        parsed = prompts.parse_developer_output(result_text)
        new_branch = parsed["branch"] or branch
        summary = parsed["summary"]
        # 人工单 repo 可能留空，由 agent 查表解析后在输出里回填【仓库】
        resolved_repo = parsed["repo"] or run.repo
        session_id_for_store = claude_session_id

        # 锁冲突：developer 申请 repo 锁被挡 → 不构建，退回初始态，人工重推。
        if parsed["status"] == "blocked":
            logger.info("[Repair] developer blocked by repo lock: %s", linear_issue_id)
            self.store.release_repos(linear_issue_id)  # 防御：被挡时本单未占到锁，幂等
            self.store.update(linear_issue_id, stage=Stage.PENDING_REVIEW)
            await self._set_issue_linear_state(client, linear_issue_id, "backlog")
            await notify(
                "🔒 涉及的服务正被其他修复单占用，已退回。请待其完成后重新触发。\n\n"
                f"{result_text}",
                final=True,
            )
            return

        # developer 未真正完成（卡批准/没按格式收尾/中途放弃）→ 不触发构建，
        # 回写 agent 实际输出 + 落可见终态 REJECTED，等人工介入。
        if parsed["status"] != "completed" or not parsed["branch"]:
            logger.info(
                "[Repair] developer not completed (status=%s branch=%s): %s, skip build, reject",
                parsed["status"],
                parsed["branch"] or "(无)",
                linear_issue_id,
            )
            self.store.update(linear_issue_id, stage=Stage.REJECTED)
            self.store.release_repos(linear_issue_id)  # 开发失败：还锁
            await self._set_issue_linear_state(client, linear_issue_id, "canceled")
            await notify(
                "🚫 自动修复未完成（开发阶段未产出有效修复/未推分支），已转人工。\n\n"
                f"Agent 最后输出：\n{result_text}",
                final=True,
            )
            return

        resolved_repos = parsed["repos"] or ([resolved_repo] if resolved_repo else [])
        build_id = await self.jenkins.trigger_build(
            repos=resolved_repos, branch=new_branch, linear_identifier=run.linear_identifier
        )

        self.store.update(
            linear_issue_id,
            stage=Stage.BUILDING,
            repo=resolved_repo,
            repos=json.dumps(resolved_repos, ensure_ascii=False),
            branch=new_branch,
            develop_session_id=session_id_for_store or "",
            jenkins_build_id=build_id,
        )

        result_msg = (
            f"已完成代码修复并推送分支：{new_branch}\n"
            f"构建+测试已触发，等待测试报告。MR 将在测试通过后自动创建。"
        )
        if summary:
            result_msg += f"\n\n修复摘要：{summary}"
        await notify(result_msg, final=True)

    # ── 阶段 2：分析报告 + 三类归因 ──────────────────────────────────────
    async def analyze_report(self, linear_issue_id: str) -> None:
        """building + 报告就绪 → analyzer → 解析判定 → 回转。"""
        run = self.store.get(linear_issue_id)
        if not run or run.stage != Stage.BUILDING:
            return

        report = await self.jenkins.get_report_async(run.jenkins_build_id)
        if report is None:
            logger.info("[Repair] report not ready: %s", linear_issue_id)
            return

        phase = report.get("phase", "")
        client = self._linear(run.workspace_id)

        if report.get("status") == "timeout":
            self.store.update(linear_issue_id, stage=Stage.REJECTED)
            self.store.release_repos(linear_issue_id)
            await self._set_issue_linear_state(client, linear_issue_id, "canceled")
            await self._notify_run(
                run, client,
                "⚠️ 构建+测试超时（超过配置时限未完成），已转人工。\n"
                "请检查 Jenkins/部署环境后，在本单评论「重跑」重新触发。",
            )
            logger.warning("[Repair] build timeout, rejected: %s", linear_issue_id)
            return

        if phase == "done_cicd_failure":
            self.store.update(linear_issue_id, stage=Stage.REJECTED)
            self.store.release_repos(linear_issue_id)
            await self._set_issue_linear_state(client, linear_issue_id, "canceled")
            await self._notify_run(
                run, client,
                f"⚠️ CI/CD 构建失败，已转人工。\n"
                f"请检查 Jenkins 构建配置、账号权限或代码错误后，在本单评论「重跑」重新触发。\n\n"
                f"{report.get('summary', '')}",
            )
            logger.warning("[Repair] cicd failure, rejected: %s", linear_issue_id)
            return

        if phase == "done_test_aborted":
            self.store.update(linear_issue_id, stage=Stage.REJECTED)
            self.store.release_repos(linear_issue_id)
            await self._set_issue_linear_state(client, linear_issue_id, "canceled")
            await self._notify_run(
                run, client,
                f"⚠️ 自动化测试任务未正常完成，已转人工。\n"
                f"请检查 Jenkins autotest 配置后，在本单评论「重跑」重新触发。\n\n"
                f"{report.get('summary', '')}",
            )
            logger.warning("[Repair] test aborted, rejected: %s", linear_issue_id)
            return

        self.store.update(linear_issue_id, stage=Stage.ANALYZING)

        # 优先读本地报告文件（详细内容），无则降级到摘要计数
        report_path = report.get("report_path", "")
        if report_path:
            try:
                from pathlib import Path
                report_content = Path(report_path).read_text(encoding="utf-8")
            except Exception:
                logger.warning("[Repair] failed to read report file %s, fallback to summary", report_path, exc_info=True)
                report_content = report.get("summary", "")
        else:
            report_content = report.get("summary", "") + "\n" + str(report.get("failures", ""))

        self.store.update(linear_issue_id, last_report=report.get("summary", ""))

        prompt = prompts.build_analyzer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            repair_plan=run.repair_plan,
            report=report.get("summary", "") if not report_path else "",
            report_path=report_path,
        )
        try:
            result_text, _ = await _run_agent(
                self.agent_service, prompt, skill="repair-report-analyzer", session_id=run.develop_session_id or None
            )
        except Exception:
            logger.error("[Repair] analyzer agent failed: %s, rolling back to BUILDING", linear_issue_id, exc_info=True)
            self.store.update(linear_issue_id, stage=Stage.BUILDING)
            return
        finally:
            if report_path:
                try:
                    from pathlib import Path
                    Path(report_path).unlink(missing_ok=True)
                except Exception:
                    logger.warning("[Repair] failed to delete report file %s", report_path, exc_info=True)
        parsed = prompts.parse_analyzer_output(result_text)
        verdict = parsed["verdict"]
        run = self.store.get(linear_issue_id)  # 重新读最新

        try:
            if verdict == "resolved":
                await self._handle_resolved(run, parsed["raw"])
            elif verdict == "code_error":
                await self._handle_code_error(run, parsed["raw"])
            elif verdict == "root_cause_error":
                await self._handle_root_cause_error(run, parsed["raw"])
            elif verdict == "missing_dependency":
                await self._handle_missing_dependency(run, parsed["raw"])
        except LinearAPIError as exc:
            if "not found" in str(exc).lower() or "entity not found" in str(exc).lower():
                logger.error(
                    "[Repair] Linear issue not found, aborting run: %s", linear_issue_id, exc_info=True,
                )
                self.store.update(linear_issue_id, stage=Stage.REJECTED)
                self.store.release_repos(linear_issue_id)
            else:
                logger.error(
                    "[Repair] verdict handler failed (%s), rolling back to BUILDING: %s",
                    verdict, linear_issue_id, exc_info=True,
                )
                self.store.update(linear_issue_id, stage=Stage.BUILDING)
            return
        except Exception:
            logger.error(
                "[Repair] verdict handler failed (%s), rolling back to BUILDING: %s",
                verdict, linear_issue_id, exc_info=True,
            )
            self.store.update(linear_issue_id, stage=Stage.BUILDING)
            return

    async def _handle_resolved(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        # 测试通过，现在才建 MR（git push -o merge_request.create）
        title = f"fix({run.linear_identifier}): 自动修复"
        mr_url = self.mr_builder.build_mr(
            identifier=run.linear_identifier, branch=run.branch, title=title
        )
        self.store.update(run.linear_issue_id, mr_url=mr_url)

        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        done_id = await self._state_id_by_type(client, team_id, "completed") if team_id else None
        if done_id:
            await client.update_issue(run.linear_issue_id, state_id=done_id)
        await self._notify_run(
            run, client,
            f"✅ Bug 已修复并通过测试。\n分支：{run.branch}\n"
            f"MR（待人工合并到 test）：{mr_url or '(建 MR 失败，请人工检查工作目录)'}\n\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.RESOLVED)
        self.store.release_repos(run.linear_issue_id)  # 建完 MR 即释放锁

    async def _handle_code_error(self, run: RepairRun, raw: str) -> None:
        count = self.store.increment_fix_retry(run.linear_issue_id)
        if count >= self.N:
            await self._reject(run, f"代码错重修达上限 N={self.N}，转人工。\n{raw}")
            return
        self.store.update(run.linear_issue_id, stage=Stage.PENDING_RERUN, last_report=run.last_report)
        client = self._linear(run.workspace_id)
        msg = (
            f"🔍 自动化测试报告分析完成，修复未通过（第 {count} 次）。\n\n"
            f"{raw}\n\n"
            f"请确认是否继续重修？在此对话回复「确认重修」后，将自动在原分支继续修复并重新触发构建。"
        )
        if run.linear_session_id:
            try:
                await client.send_response(run.linear_session_id, msg)
            except Exception:
                logger.warning("[Repair] send_response failed, fallback to comment: %s", run.linear_issue_id, exc_info=True)
                await client.create_comment(run.linear_issue_id, msg)
        else:
            await client.create_comment(run.linear_issue_id, msg)

    async def confirm_rerun(self, linear_issue_id: str, linear_session_id: str) -> None:
        """用户在 Linear 会话确认重修后调用，执行重修并触发构建。"""
        run = self.store.get(linear_issue_id)
        if not run or run.stage != Stage.PENDING_RERUN:
            return
        # 更新 linear_session_id（本次对话的新 session）
        self.store.update(linear_issue_id, linear_session_id=linear_session_id)
        run = self.store.get(linear_issue_id)
        client = self._linear(run.workspace_id)
        try:
            await client.send_thought(linear_session_id, "已收到确认，正在启动重修...")
        except Exception:
            pass
        prompt = prompts.build_developer_prompt(
            issue_id=run.linear_issue_id,
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence="（见上一轮失败报告）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=run.branch,
            is_retry=True,
            last_report=run.last_report,
            repos=json.loads(run.repos) if run.repos else None,
        )

        async def notify(body: str, final: bool = False) -> None:
            try:
                if final:
                    await client.send_response(linear_session_id, body)
                else:
                    await client.send_thought(linear_session_id, body)
            except Exception:
                logger.warning("[Repair] notify failed session=%s, fallback to comment", linear_session_id, exc_info=True)
                try:
                    await client.create_comment(linear_issue_id, body)
                except Exception:
                    logger.warning("[Repair] notify fallback comment also failed: %s", linear_issue_id, exc_info=True)

        self.store.update(linear_issue_id, stage=Stage.DEVELOPING)
        result_text, session_id = await _run_agent(
            self.agent_service,
            prompt,
            skill="bug-fix-developer",
            session_id=run.develop_session_id or None,
        )
        parsed = prompts.parse_developer_output(result_text)
        if parsed["status"] != "completed":
            await self._reject(
                run,
                "重修未完成（开发阶段未产出有效修复），转人工。\n\n"
                f"Agent 最后输出：\n{result_text}",
            )
            return
        repos = json.loads(run.repos) if run.repos else ([run.repo] if run.repo else [])
        build_id = await self.jenkins.trigger_build(
            repos=repos, branch=run.branch, linear_identifier=run.linear_identifier
        )
        self.store.update(
            linear_issue_id,
            stage=Stage.BUILDING,
            develop_session_id=session_id or run.develop_session_id,
            jenkins_build_id=build_id,
        )
        await notify(
            f"重修代码已推送，构建+测试已触发，等待测试报告。",
            final=True,
        )

    async def _handle_root_cause_error(self, run: RepairRun, raw: str) -> None:
        count = self.store.increment_rediagnose(run.linear_issue_id)
        client = self._linear(run.workspace_id)
        if count >= self.M:
            await self._reject(run, f"根因错重诊断达上限 M={self.M}，转人工。\n{raw}")
            return
        await self._notify_run(
            run, client,
            f"⚠️ 原根因判错（第 {count} 次），需重新诊断。\n{raw}",
        )
        # 回退到 backlog，让用户重新触发诊断
        await self._set_issue_linear_state(client, run.linear_issue_id, "backlog")
        self.store.update(run.linear_issue_id, stage=Stage.PENDING_REVIEW)
        self.store.release_repos(run.linear_issue_id)

    async def _handle_missing_dependency(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        child = await client.create_issue(
            team_id=team_id,
            title=f"[依赖] {run.linear_identifier} 修复牵出的外部依赖",
            description=raw,
        )
        await self._notify_run(
            run, client,
            f"🔗 修复牵出外部依赖，已建子单 {child.get('identifier')}，"
            f"父单 blockedBy 子单（本期记录，合并接力待人工）。\n{raw}",
        )
        # issue 推回 backlog，等依赖子单解决后人工重新触发
        await self._set_issue_linear_state(client, run.linear_issue_id, "backlog")
        self.store.update(run.linear_issue_id, stage=Stage.BLOCKED)
        self.store.release_repos(run.linear_issue_id)

    async def _reject(self, run: RepairRun, reason: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        cancel_id = await self._state_id_by_type(client, team_id, "canceled") if team_id else None
        if cancel_id:
            await client.update_issue(run.linear_issue_id, state_id=cancel_id)
        await self._notify_run(run, client, f"🚫 产研退回：{reason}")
        self.store.update(run.linear_issue_id, stage=Stage.REJECTED)
        self.store.release_repos(run.linear_issue_id)

    # ── 轮询入口（scheduler 调用）────────────────────────────────────────
    async def poll_building_runs(self) -> None:
        """扫所有 building 的 run 尝试分析报告；并 reconcile 陈旧 repo 锁。"""
        for run in self.store.list_by_stage(Stage.BUILDING):
            try:
                await self.analyze_report(run.linear_issue_id)
            except Exception:
                logger.error(
                    "[Repair] poll analyze failed: %s",
                    run.linear_issue_id,
                    exc_info=True,
                )
        self._reconcile_locks()

    _ACTIVE_STAGES = (Stage.DEVELOPING, Stage.BUILDING, Stage.ANALYZING)

    def _reconcile_locks(self) -> None:
        """回收 holder 已不存在或已不在活跃态的陈旧锁，防 run 崩溃焊死 repo。"""
        for lock in self.store.list_locks():
            holder = lock["holder_issue_id"]
            run = self.store.get(holder)
            if run is None or run.stage not in self._ACTIVE_STAGES:
                logger.info(
                    "[Repair] reconcile: releasing stale lock repo=%s holder=%s",
                    lock["repo"], holder,
                )
                self.store.release_repos(holder)


# ── module-level singleton ─────────────────────────────────────────────
_coordinator: Optional[RepairCoordinator] = None


def set_coordinator(coord: RepairCoordinator) -> None:
    global _coordinator
    _coordinator = coord


def get_coordinator() -> Optional[RepairCoordinator]:
    """linear handler 软依赖此函数；repair 未启用时返回 None。"""
    return _coordinator
