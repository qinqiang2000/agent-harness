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

logger = logging.getLogger(__name__)


async def _run_agent(
    agent_service,
    prompt: str,
    skill: str,
    session_id: Optional[str],
    on_message: Optional[Callable[[str], "object"]] = None,
) -> tuple[str, Optional[str]]:
    """调 AgentService.process_query，返回 (result_text, claude_session_id)。

    新会话靠 DEFAULT_SKILLS 加载 skill；resume 时传 session_id。
    on_message：每收到一条 assistant_message 中间过程文本就 await 调用一次
    （用于逐步转发到 Linear 会话）；回调异常被吞掉，不影响主流程。
    """
    from api.models.requests import QueryRequest

    request = QueryRequest(
        prompt=prompt,
        language="中文",
        skill=skill if not session_id else None,
        session_id=session_id,
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
    ):
        self.agent_service = agent_service
        self.store = store
        self.jenkins = jenkins
        self._linear_factory = linear_client_factory
        self.N = fix_retry_limit
        self.M = rediagnose_limit

    def _linear(self, workspace_id: str):
        return self._linear_factory(workspace_id)

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
        branch = run.branch or f"fix/{run.linear_identifier}"

        prompt = prompts.build_developer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence=run.evidence or run.last_report or "（见 Linear 单描述）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=branch,
            is_retry=False,
            last_report="",
        )

        # 有会话时，把 developer 每步中间输出转成会话 thought（逐步可见）。
        on_message = (lambda text: notify(text)) if session_id else None

        try:
            result_text, claude_session_id = await _run_agent(
                self.agent_service,
                prompt,
                skill="bug-fix-developer",
                session_id=None,
                on_message=on_message,
            )
        except Exception:
            logger.error("[Repair] developer agent failed: %s", linear_issue_id, exc_info=True)
            self.store.update(linear_issue_id, stage=on_agent_failure)
            fail_msg = (
                "⚠️ 自动开发启动失败，已退回待审核，请重新触发或人工介入。"
                if on_agent_failure == Stage.PENDING_REVIEW
                else "🚫 自动修复启动失败（开发阶段异常），已转人工，请人工介入。"
            )
            await notify(fail_msg, final=True)
            return

        parsed = prompts.parse_developer_output(result_text)
        new_branch = parsed["branch"] or branch
        mr_url = parsed["mr_url"]
        summary = parsed["summary"]
        # 人工单 repo 可能留空，由 agent 查表解析后在输出里回填【仓库】
        resolved_repo = parsed["repo"] or run.repo
        session_id_for_store = claude_session_id

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
            await notify(
                "🚫 自动修复未完成（开发阶段未产出有效修复/未推分支），已转人工。\n\n"
                f"Agent 最后输出：\n{result_text}",
                final=True,
            )
            return

        build_id = self.jenkins.trigger_build(repo=resolved_repo, branch=new_branch)

        self.store.update(
            linear_issue_id,
            stage=Stage.BUILDING,
            repo=resolved_repo,
            branch=new_branch,
            mr_url=mr_url,
            develop_session_id=session_id_for_store or "",
            jenkins_build_id=build_id,
        )

        result_msg = (
            f"已自动开发并建 MR：{mr_url or '(未解析到 MR 链接)'}\n"
            f"分支：{new_branch}\n构建已触发，等待测试报告。"
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

        report = self.jenkins.get_report(run.jenkins_build_id)
        if report is None:
            logger.info("[Repair] report not ready: %s", linear_issue_id)
            return

        self.store.update(linear_issue_id, stage=Stage.ANALYZING)
        report_summary = report.get("summary", "") + "\n" + str(report.get("failures", ""))
        self.store.update(linear_issue_id, last_report=report_summary)

        prompt = prompts.build_analyzer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            repair_plan=run.repair_plan,
            report=report_summary,
        )
        try:
            result_text, _ = await _run_agent(
                self.agent_service, prompt, skill="repair-report-analyzer", session_id=None
            )
        except Exception:
            logger.error("[Repair] analyzer agent failed: %s, rolling back to BUILDING", linear_issue_id, exc_info=True)
            self.store.update(linear_issue_id, stage=Stage.BUILDING)
            return
        parsed = prompts.parse_analyzer_output(result_text)
        verdict = parsed["verdict"]
        run = self.store.get(linear_issue_id)  # 重新读最新

        if verdict == "resolved":
            await self._handle_resolved(run, parsed["raw"])
        elif verdict == "code_error":
            await self._handle_code_error(run, parsed["raw"])
        elif verdict == "root_cause_error":
            await self._handle_root_cause_error(run, parsed["raw"])
        elif verdict == "missing_dependency":
            await self._handle_missing_dependency(run, parsed["raw"])

    async def _handle_resolved(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        done_id = await self._state_id_by_type(client, team_id, "completed") if team_id else None
        if done_id:
            await client.update_issue(run.linear_issue_id, state_id=done_id)
        await client.create_comment(
            run.linear_issue_id,
            f"✅ Bug 已修复并通过测试。\n分支：{run.branch}\nMR：{run.mr_url}\n\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.RESOLVED)

    async def _handle_code_error(self, run: RepairRun, raw: str) -> None:
        count = self.store.increment_fix_retry(run.linear_issue_id)
        if count >= self.N:
            await self._reject(run, f"代码错重修达上限 N={self.N}，转人工。\n{raw}")
            return
        prompt = prompts.build_developer_prompt(
            identifier=run.linear_identifier,
            root_cause=run.root_cause,
            evidence="（见上一轮失败报告）",
            repair_plan=run.repair_plan,
            repo=run.repo,
            branch=run.branch,
            is_retry=True,
            last_report=run.last_report,
        )
        result_text, session_id = await _run_agent(
            self.agent_service,
            prompt,
            skill="bug-fix-developer",
            session_id=run.develop_session_id or None,
        )
        parsed = prompts.parse_developer_output(result_text)
        # 重修同样要求真正完成才触发构建；否则落 REJECTED 转人工。
        if parsed["status"] != "completed":
            logger.info(
                "[Repair] retry developer not completed (status=%s): %s, skip build, reject",
                parsed["status"],
                run.linear_issue_id,
            )
            await self._reject(
                run,
                "重修未完成（开发阶段未产出有效修复），转人工。\n\n"
                f"Agent 最后输出：\n{result_text}",
            )
            return
        mr_url = parsed["mr_url"] or run.mr_url
        build_id = self.jenkins.trigger_build(repo=run.repo, branch=run.branch)
        self.store.update(
            run.linear_issue_id,
            stage=Stage.BUILDING,
            mr_url=mr_url,
            develop_session_id=session_id or run.develop_session_id,
            jenkins_build_id=build_id,
        )

    async def _handle_root_cause_error(self, run: RepairRun, raw: str) -> None:
        count = self.store.increment_rediagnose(run.linear_issue_id)
        client = self._linear(run.workspace_id)
        if count >= self.M:
            await self._reject(run, f"根因错重诊断达上限 M={self.M}，转人工。\n{raw}")
            return
        await client.create_comment(
            run.linear_issue_id,
            f"⚠️ 原根因判错（第 {count} 次），需重新诊断。\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.PENDING_REVIEW)

    async def _handle_missing_dependency(self, run: RepairRun, raw: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        child = await client.create_issue(
            team_id=team_id,
            title=f"[依赖] {run.linear_identifier} 修复牵出的外部依赖",
            description=raw,
        )
        await client.create_comment(
            run.linear_issue_id,
            f"🔗 修复牵出外部依赖，已建子单 {child.get('identifier')}，"
            f"父单 blockedBy 子单（本期记录，合并接力待人工）。\n{raw}",
        )
        self.store.update(run.linear_issue_id, stage=Stage.BLOCKED)

    async def _reject(self, run: RepairRun, reason: str) -> None:
        client = self._linear(run.workspace_id)
        issue = await client.get_issue(run.linear_issue_id)
        team_id = issue.get("team", {}).get("id", "")
        cancel_id = await self._state_id_by_type(client, team_id, "canceled") if team_id else None
        if cancel_id:
            await client.update_issue(run.linear_issue_id, state_id=cancel_id)
        await client.create_comment(run.linear_issue_id, f"🚫 产研退回：{reason}")
        self.store.update(run.linear_issue_id, stage=Stage.REJECTED)

    # ── 轮询入口（scheduler 调用）────────────────────────────────────────
    async def poll_building_runs(self) -> None:
        """扫描所有 building 的 run，逐个尝试分析报告。"""
        for run in self.store.list_by_stage(Stage.BUILDING):
            try:
                await self.analyze_report(run.linear_issue_id)
            except Exception:
                logger.error(
                    "[Repair] poll analyze failed: %s",
                    run.linear_issue_id,
                    exc_info=True,
                )


# ── module-level singleton ─────────────────────────────────────────────
_coordinator: Optional[RepairCoordinator] = None


def set_coordinator(coord: RepairCoordinator) -> None:
    global _coordinator
    _coordinator = coord


def get_coordinator() -> Optional[RepairCoordinator]:
    """linear handler 软依赖此函数；repair 未启用时返回 None。"""
    return _coordinator
