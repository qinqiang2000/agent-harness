"""Jenkins 客户端 —— 真实 httpx 实现 + 自驱动两任务状态机。

两个公共方法（coordinator 接口不变）：
  trigger_build(repos, branch) -> build_token   异步，立即返回，只落库
  get_report(build_token) -> dict|None          同步，只读库

后台驱动由 start_driver(build_token) 拉起（asyncio.create_task），
由 plugin.on_start / poller 扫表统一调用，不在 trigger_build 内直接启动。
"""

import asyncio
import logging
import os
import re
import time
from typing import Dict, List, Optional

import httpx

from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore

logger = logging.getLogger(__name__)


class JenkinsClient:
    def __init__(
        self,
        base_url: str,
        user: str,
        api_token: str,
        cicd_job: str,
        cicd_token: str,
        autotest_job: str,
        autotest_token: str,
        build_store: JenkinsBuildStore,
        deploy: bool = True,
        autotest_run_mode: str = "smoke",
        autotest_threads: int = 4,
        build_timeout_seconds: int = 86400,
        cicd_poll_seconds: int = 60,
        autotest_poll_seconds: int = 300,
        queue_poll_seconds: int = 60,
        github_artifacts_client=None,
    ):
        self._base = base_url.rstrip("/")
        self._auth = (user, api_token)
        self._cicd_job = cicd_job
        self._cicd_token = cicd_token
        self._autotest_job = autotest_job
        self._autotest_token = autotest_token
        self._store = build_store
        self._deploy = deploy
        self._run_mode = autotest_run_mode
        self._threads = autotest_threads
        self._timeout_s = build_timeout_seconds
        self._cicd_poll = cicd_poll_seconds
        self._autotest_poll = autotest_poll_seconds
        self._queue_poll = queue_poll_seconds
        self._http = httpx.AsyncClient(auth=self._auth, timeout=30)
        self._owner = f"pid-{os.getpid()}"
        self._github_artifacts = github_artifacts_client

    async def trigger_build(self, repos: List[str], branch: str, linear_identifier: str = "") -> str:
        """并行触发各 repo 的 cicd 构建，落库，返回 build_token。不启动驱动。"""
        token = self._store.create_build(repos=repos, branch=branch, linear_identifier=linear_identifier)
        tasks = [self._trigger_cicd_one(token, repo, branch) for repo in repos]
        await asyncio.gather(*tasks, return_exceptions=True)
        return token

    async def _trigger_cicd_one(self, build_token: str, repo: str, branch: str) -> None:
        service = repo.split("/")[-1]
        url = f"{self._base}/job/{self._cicd_job}/buildWithParameters"
        params = {
            "token": self._cicd_token,
            "SERVICE": service,
            "BRANCH": branch,
            "DEPLOY": str(self._deploy).lower(),
        }
        try:
            resp = await self._http.post(url, params=params)
            if resp.status_code != 201:
                raise RuntimeError(f"cicd trigger failed: {resp.status_code}")
            location = resp.headers.get("Location", "")
            m = re.search(r"/queue/item/(\d+)/", location)
            if not m:
                raise RuntimeError(f"cannot parse queue id from: {location}")
            queue_id = m.group(1)
            self._store.update_cicd_build(build_token, repo, queue_id=queue_id)
        except Exception as exc:
            logger.error("[Jenkins] trigger cicd failed repo=%s: %s", repo, exc)
            self._store.update_cicd_build(
                build_token, repo, result="FAILURE", console_snippet=str(exc)
            )
            rows = self._store.list_cicd_builds(build_token)
            if all(r["result"] in ("FAILURE", "ABORTED") or not r["queue_id"] for r in rows):
                self._store.update_build(
                    build_token,
                    phase="done_cicd_failure",
                    report_json=f"[构建失败] 触发 cicd 失败: {exc}",
                )

    def get_report(self, build_token: str) -> Optional[Dict]:
        """只读库，phase 以 done_ 开头则按 phase 组装报告字典，否则返回 None。"""
        build = self._store.get_build(build_token)
        if not build:
            return None
        phase = build["phase"]
        if not phase.startswith("done_"):
            return None
        report_json = build.get("report_json", "")
        report_path = build.get("report_path", "")
        if phase == "done_success":
            return {"phase": phase, "status": "success", "summary": report_json, "report_path": report_path, "failures": []}
        elif phase == "done_cicd_failure":
            summary = (
                report_json if report_json.startswith("[构建失败]")
                else f"[构建失败] {report_json}"
            )
            return {"phase": phase, "status": "failure", "summary": summary, "report_path": "", "failures": []}
        elif phase == "done_test_failure":
            return {"phase": phase, "status": "failure", "summary": report_json, "report_path": report_path, "failures": []}
        elif phase == "done_test_aborted":
            return {"phase": phase, "status": "failure", "summary": f"[测试任务未正常完成] {report_json}", "report_path": "", "failures": []}
        elif phase == "done_timeout":
            return {
                "phase": phase,
                "status": "timeout",
                "summary": report_json or "构建+测试超过配置时限未完成，判定超时",
                "report_path": "",
                "failures": [],
            }
        return {"phase": phase, "status": "failure", "summary": report_json, "report_path": report_path, "failures": []}

    async def _advance(self, build_token: str) -> None:
        """非阻塞单步推进。整轮包 try/except，单次失败不改 phase。"""
        build = self._store.get_build(build_token)
        if not build or build["phase"].startswith("done_"):
            return

        if int(time.time()) - build["started_at"] > self._timeout_s:
            self._store.update_build(
                build_token,
                phase="done_timeout",
                report_json="构建+测试超过配置时限未完成，判定超时",
            )
            logger.warning("[Jenkins] build timeout: %s", build_token)
            return

        phase = build["phase"]
        try:
            if phase == "cicd_queued":
                await self._advance_cicd_queued(build_token)
            elif phase == "cicd_building":
                await self._advance_cicd_building(build_token)
            elif phase == "autotest_queued":
                await self._advance_autotest_queued(build_token)
            elif phase == "autotest_building":
                await self._advance_autotest_building(build_token)
        except Exception as exc:
            logger.warning(
                "[Jenkins] _advance error phase=%s token=%s: %s", phase, build_token, exc
            )

    async def _advance_cicd_queued(self, build_token: str) -> None:
        rows = self._store.list_cicd_builds(build_token)
        pending_rows = [r for r in rows if r["build_no"] == 0 and r["queue_id"]]
        for row in pending_rows:
            url = f"{self._base}/queue/item/{row['queue_id']}/api/json"
            resp = await self._http.get(url)
            if resp.status_code == 404:
                logger.warning(
                    "[Jenkins] queue item %s not found (expired?), marking FAILURE",
                    row["queue_id"],
                )
                self._store.update_cicd_build(
                    build_token, row["repo"], result="FAILURE",
                    console_snippet="queue item 已过期或不存在",
                )
                continue
            if resp.status_code != 200:
                logger.warning(
                    "[Jenkins] queue item %s returned HTTP %s, skipping",
                    row["queue_id"], resp.status_code,
                )
                continue
            try:
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "[Jenkins] queue item %s non-JSON response (%s): %.200s",
                    row["queue_id"], exc, resp.text,
                )
                continue
            executable = data.get("executable")
            if executable and executable.get("number"):
                self._store.update_cicd_build(
                    build_token, row["repo"], build_no=executable["number"]
                )
        rows = self._store.list_cicd_builds(build_token)
        if all(r["build_no"] > 0 or r["result"] in ("FAILURE", "ABORTED") for r in rows):
            self._store.update_build(build_token, phase="cicd_building")

    async def _advance_cicd_building(self, build_token: str) -> None:
        rows = self._store.list_cicd_builds(build_token)
        for row in rows:
            if row["result"] != "PENDING":
                continue
            url = f"{self._base}/job/{self._cicd_job}/{row['build_no']}/api/json"
            resp = await self._http.get(url)
            data = resp.json()
            if data.get("building"):
                continue
            result = data.get("result", "ABORTED")
            self._store.update_cicd_build(build_token, row["repo"], result=result)
            if result in ("FAILURE", "ABORTED"):
                snippet = await self._get_console_snippet(self._cicd_job, row["build_no"])
                self._store.update_cicd_build(
                    build_token, row["repo"], console_snippet=snippet
                )

        rows = self._store.list_cicd_builds(build_token)
        failed = [r for r in rows if r["result"] in ("FAILURE", "ABORTED")]
        if failed:
            summaries = [
                f"{r['repo']}: {r['console_snippet'] or r['result']}" for r in failed
            ]
            self._store.update_build(
                build_token,
                phase="done_cicd_failure",
                report_json="[构建失败]\n" + "\n".join(summaries),
            )
            return
        if all(r["result"] == "SUCCESS" for r in rows):
            await self._trigger_autotest(build_token)

    async def _trigger_autotest(self, build_token: str) -> None:
        url = f"{self._base}/job/{self._autotest_job}/buildWithParameters"
        build = self._store.get_build(build_token)
        params = {
            "token": self._autotest_token,
            "RUN_MODE": self._run_mode,
            "THREADS": str(self._threads),
            "ISSUE_ID": (build or {}).get("linear_identifier", ""),
        }
        try:
            resp = await self._http.post(url, params=params)
            if resp.status_code != 201:
                raise RuntimeError(f"autotest trigger failed: {resp.status_code}")
            location = resp.headers.get("Location", "")
            m = re.search(r"/queue/item/(\d+)/", location)
            if not m:
                raise RuntimeError(f"cannot parse autotest queue id: {location}")
            self._store.update_build(
                build_token,
                phase="autotest_queued",
                autotest_queue_id=m.group(1),
            )
        except Exception as exc:
            logger.error("[Jenkins] trigger autotest failed token=%s: %s", build_token, exc)
            self._store.update_build(
                build_token,
                phase="done_test_aborted",
                report_json=f"autotest 触发失败: {exc}",
            )

    async def _advance_autotest_queued(self, build_token: str) -> None:
        build = self._store.get_build(build_token)
        queue_id = build.get("autotest_queue_id", "")
        if not queue_id:
            self._store.update_build(
                build_token,
                phase="done_test_aborted",
                report_json="autotest_queue_id 丢失，无法继续",
            )
            return
        url = f"{self._base}/queue/item/{queue_id}/api/json"
        resp = await self._http.get(url)
        data = resp.json()
        executable = data.get("executable")
        if executable and executable.get("number"):
            self._store.update_build(
                build_token,
                phase="autotest_building",
                autotest_build_no=executable["number"],
            )

    async def _advance_autotest_building(self, build_token: str) -> None:
        build = self._store.get_build(build_token)
        build_no = build.get("autotest_build_no", 0)
        if not build_no:
            return
        url = f"{self._base}/job/{self._autotest_job}/{build_no}/api/json"
        resp = await self._http.get(url)
        data = resp.json()
        if data.get("building"):
            return
        result = data.get("result", "ABORTED")
        self._store.update_build(build_token, jenkins_result=result)
        if result == "SUCCESS":
            test_report = data.get("testReport") or {}
            pass_count = test_report.get("passCount", 0)
            fail_count = test_report.get("failCount", 0)
            report_path = await self._download_artifacts_report(build_token)
            self._store.update_build(
                build_token,
                phase="done_success",
                report_json=f"{pass_count} passed, {fail_count} failed",
                report_path=report_path,
            )
        elif result == "FAILURE":
            test_report = data.get("testReport") or {}
            fail_count = test_report.get("failCount", 0)
            report_path = await self._download_artifacts_report(build_token)
            self._store.update_build(
                build_token,
                phase="done_test_failure",
                report_json=f"测试失败：{fail_count} 个用例未通过",
                report_path=report_path,
            )
        else:
            self._store.update_build(
                build_token,
                phase="done_test_aborted",
                report_json=f"autotest 未正常完成，Jenkins result={result}",
            )

    async def _download_artifacts_report(self, build_token: str) -> str:
        """从 GitHub artifacts 仓库下载 autotest 报告到本地临时文件，返回路径；失败返回空串。"""
        if not self._github_artifacts:
            return ""
        build = self._store.get_build(build_token)
        identifier = (build or {}).get("linear_identifier", "")
        if not identifier:
            return ""
        dest = f"/tmp/repair/reports/{build_token}-run.md"
        ok = await self._github_artifacts.download_latest_autotest_report(identifier, dest)
        return dest if ok else ""

    async def _get_console_snippet(self, job: str, build_no: int, max_lines: int = 20) -> str:
        """拉构建日志末尾片段。失败静默返回空串。"""
        try:
            url = f"{self._base}/job/{job}/{build_no}/consoleText"
            resp = await self._http.get(url)
            lines = resp.text.strip().splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception:
            return ""

    async def start_driver(self, build_token: str) -> None:
        """启动 per-build 后台驱动。已有新鲜驱动则跳过。"""
        if not self._store.try_acquire_driver(build_token, self._owner):
            return
        asyncio.create_task(self._run_driver(build_token))

    async def _run_driver(self, build_token: str) -> None:
        """驱动主循环：推进 phase 直到 done，按 phase 选轮询间隔。"""
        logger.info("[Jenkins] driver started: %s", build_token)
        while True:
            build = self._store.get_build(build_token)
            if not build or build["phase"].startswith("done_"):
                break
            if build.get("driver_owner") != self._owner:
                logger.info("[Jenkins] driver preempted, exiting: %s", build_token)
                break
            await self._advance(build_token)
            build = self._store.get_build(build_token)
            if not build or build["phase"].startswith("done_"):
                break
            phase = build["phase"]
            if "queued" in phase:
                interval = self._queue_poll
            elif "autotest" in phase:
                interval = self._autotest_poll
            else:
                interval = self._cicd_poll
            self._store.refresh_heartbeat(build_token, self._owner)
            await asyncio.sleep(interval)
        logger.info("[Jenkins] driver done: %s", build_token)

    async def resume_pending_drivers(self) -> None:
        """扫表，对无驱动或驱动陈旧的非 done 记录拉起驱动。on_start / poller 调用。"""
        for build in self._store.list_non_done_builds():
            await self.start_driver(build["build_token"])

    async def aclose(self) -> None:
        await self._http.aclose()
