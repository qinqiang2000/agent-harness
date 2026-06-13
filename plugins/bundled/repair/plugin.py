"""Bug 修复流水线插件入口。

构造 store/jenkins/coordinator 并注册 module-level singleton；
on_start 自建 AsyncIOScheduler 轮询构建报告；注册 GitLab webhook 路由骨架。
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.constants import AGENTS_ROOT
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

if TYPE_CHECKING:
    # PluginAPI 顶层会 transitive import claude_agent_sdk（CLI/测试上下文不可用），
    # 仅作类型标注用，按 CLAUDE.md 约定用 TYPE_CHECKING guard。
    from api.plugins.api import PluginAPI

from plugins.bundled.repair import coordinator as coord_mod
from plugins.bundled.repair.coordinator import RepairCoordinator
from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
from plugins.bundled.repair.jenkins_client import JenkinsClient
from plugins.bundled.repair.mr_builder import MRBuilder
from plugins.bundled.repair.store import RepairStore

logger = logging.getLogger(__name__)


def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else str(AGENTS_ROOT / path)


class RepairChannelPlugin(ChannelPlugin):
    """修复流水线 channel plugin（自建 scheduler + GitLab webhook 骨架）。"""

    def __init__(self, api: "PluginAPI"):
        self.api = api
        self.config = api.config

        store = RepairStore(_resolve(self.config.get("repair_db_path", "data/repair/repair_runs.db")))

        jenkins_builds_db = _resolve(
            self.config.get("jenkins_builds_db_path", "data/repair/jenkins_builds.db")
        )
        build_store = JenkinsBuildStore(jenkins_builds_db)

        jenkins = JenkinsClient(
            base_url=os.getenv("JENKINS_BASE_URL", ""),
            user=os.getenv("JENKINS_USER", ""),
            api_token=os.getenv("JENKINS_API_TOKEN", ""),
            cicd_job=os.getenv("JENKINS_CICD_JOB", "cicd-pipeline"),
            cicd_token=os.getenv("JENKINS_CICD_TOKEN", ""),
            autotest_job=os.getenv("JENKINS_AUTOTEST_JOB", "at-automated-test"),
            autotest_token=os.getenv("JENKINS_AUTOTEST_TOKEN", ""),
            build_store=build_store,
            deploy=self.config.get("jenkins_deploy", True),
            autotest_run_mode=self.config.get("autotest_run_mode", "smoke"),
            autotest_threads=int(self.config.get("autotest_threads", 4)),
            build_timeout_seconds=int(self.config.get("build_timeout_seconds", 86400)),
            cicd_poll_seconds=int(self.config.get("cicd_poll_seconds", 15)),
            autotest_poll_seconds=int(self.config.get("autotest_poll_seconds", 30)),
            queue_poll_seconds=int(self.config.get("queue_poll_seconds", 5)),
        )
        self.jenkins = jenkins

        coord = RepairCoordinator(
            agent_service=api.agent_service,
            store=store,
            jenkins=jenkins,
            linear_client_factory=self._linear_client_factory,
            fix_retry_limit=int(self.config.get("fix_retry_limit", 3)),
            rediagnose_limit=int(self.config.get("rediagnose_limit", 2)),
            mr_builder=MRBuilder(),
        )
        self.store = store
        self.coordinator = coord
        coord_mod.set_coordinator(coord)

        self._scheduler = None  # 在 on_start 自建

    # ── LinearClient factory ─────────────────────────────────────────────
    def _linear_client_factory(self, workspace_id: str):
        from plugins.bundled.linear.linear_client import LinearClient
        from plugins.bundled.linear.token_store import TokenStore

        db_path = _resolve(os.getenv("LINEAR_TOKEN_DB", "data/linear/linear_tokens.db"))
        ts = TokenStore(db_path)
        ws = workspace_id or ts.get_first_workspace_id()
        token = ts.get_token(ws) if ws else None
        if not token:
            raise RuntimeError(f"no Linear token for workspace={ws}")
        return LinearClient(token)

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="repair",
            name="Bug 修复流水线",
            webhook_path="/repair/gitlab/webhook",
            description="Linear 中枢自动 bug 修复流水线",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=False,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=False,
            transfer_human=False,
        )

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["repair"])

        @router.post("/repair/gitlab/webhook")
        async def gitlab_webhook(request: Request):
            """GitLab webhook 骨架（本期占位，验签 TODO，不作主驱动）。

            TODO(联调): 校验 X-Gitlab-Token；解析 MR/pipeline 事件，
            按 source branch 反查 repair_runs，推进 coordinator。
            本期 APScheduler 轮询为主驱动。
            """
            logger.info("[Repair] gitlab webhook received (placeholder)")
            return JSONResponse(status_code=200, content={"ok": True})

        return router

    async def send_text(self, recipient_id, text, context=None) -> bool:
        return False

    async def on_start(self) -> None:
        poll_enabled = os.getenv("REPAIR_POLL_ENABLED", "true").lower() in ("1", "true", "yes")
        if not poll_enabled:
            logger.info("[Repair] poll disabled (set REPAIR_POLL_ENABLED=true to enable)")
            return
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        interval = int(self.config.get("poll_interval_seconds", 60))
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self.coordinator.poll_building_runs,
            "interval",
            seconds=interval,
            id="repair_poll",
        )
        self._scheduler.start()
        logger.info("[Repair] poll scheduler started, interval=%ds", interval)
        await self.jenkins.resume_pending_drivers()
        logger.info("[Repair] resumed pending Jenkins drivers on start")

    async def on_stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("[Repair] poll scheduler stopped")
        await self.jenkins.aclose()


def register(api: "PluginAPI") -> RepairChannelPlugin:
    """插件注册入口，由 PluginManager 调用。"""
    plugin = RepairChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[Repair] plugin registered")
    return plugin
