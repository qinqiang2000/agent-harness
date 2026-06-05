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


async def _run_agent(agent_service, prompt: str, skill: str, session_id: Optional[str]) -> tuple[str, Optional[str]]:
    """调 AgentService.process_query，返回 (result_text, claude_session_id)。

    新会话靠 DEFAULT_SKILLS 加载 skill；resume 时传 session_id。
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
        try:
            result_text, session_id = await _run_agent(
                self.agent_service, prompt, skill="bug-fix-developer", session_id=None
            )
        except Exception:
            logger.error("[Repair] developer agent failed: %s", linear_issue_id, exc_info=True)
            self.store.update(linear_issue_id, stage=Stage.PENDING_REVIEW)
            try:
                await self._linear(run.workspace_id).create_comment(
                    linear_issue_id, "⚠️ 自动开发启动失败，已退回待审核，请重新触发或人工介入。"
                )
            except Exception:
                logger.warning("[Repair] failed to comment after dev failure", exc_info=True)
            return

        parsed = prompts.parse_developer_output(result_text)
        new_branch = parsed["branch"] or branch
        mr_url = parsed["mr_url"]

        build_id = self.jenkins.trigger_build(repo=run.repo, branch=new_branch)

        self.store.update(
            linear_issue_id,
            stage=Stage.BUILDING,
            branch=new_branch,
            mr_url=mr_url,
            develop_session_id=session_id or "",
            jenkins_build_id=build_id,
        )

        client = self._linear(run.workspace_id)
        try:
            await client.create_comment(
                linear_issue_id,
                f"已自动开发并建 MR：{mr_url or '(未解析到 MR 链接)'}\n"
                f"分支：{new_branch}\n构建已触发，等待测试报告。",
            )
        except Exception:
            logger.warning("[Repair] failed to comment after development", exc_info=True)

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
