"""Jenkins 客户端 —— cicd inline poll + autotest 定时扫表。

trigger_build(repos, branch) -> build_token
    内部 inline poll cicd 直到全部完成（≤5min），
    cicd 全部 SUCCESS 后触发 autotest 并等到拿到 autotest_build_no，
    返回 build_token。phase 停在 autotest_building，由 coordinator 定时任务扫表。

get_report(build_token) -> dict|None
    只读库，autotest_building 时轮询 Jenkins 拿结果并更新 phase；
    phase 以 done_ 开头则返回报告字典，否则返回 None。
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
        cicd_poll_seconds: int = 10,
        autotest_poll_seconds: int = 30,
        queue_poll_seconds: int = 5,
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
        self._github_artifacts = github_artifacts_client

    # ── 公共入口 ─────────────────────────────────────────────────────────

    async def trigger_build(self, repos: List[str], branch: str, linear_identifier: str = "") -> str:
        """并行触发 cicd，inline poll 等完成，成功后触发 autotest 等到拿到 build_no，返回 build_token。"""
        token = self._store.create_build(repos=repos, branch=branch, linear_identifier=linear_identifier)

        # 1. 并行触发所有 repo 的 cicd
        await asyncio.gather(
            *[self._trigger_cicd_one(token, repo, branch) for repo in repos],
            return_exceptions=True,
        )

        # 2. inline poll cicd 直到全部完成
        await self._poll_cicd_until_done(token)

        # 3. 检查 cicd 结果，失败直接返回（phase 已是 done_cicd_failure）
        build = self._store.get_build(token)
        if not build or build["phase"] == "done_cicd_failure":
            return token

        # 4. cicd 全部 SUCCESS，触发 autotest
        await self._trigger_autotest(token)

        # 5. 等到拿到 autotest_build_no（queue → building），超时则标 aborted
        await self._wait_autotest_build_no(token)

        return token

    def get_report(self, build_token: str) -> Optional[Dict]:
        """轮询 autotest 结果（若仍在运行），phase done_ 后返回报告字典，否则 None。"""
        build = self._store.get_build(build_token)
        if not build:
            return None

        phase = build["phase"]

        # 超时检查
        if not phase.startswith("done_") and int(time.time()) - build["started_at"] > self._timeout_s:
            self._store.update_build(
                build_token,
                phase="done_timeout",
                report_json="构建+测试超过配置时限未完成，判定超时",
            )
            phase = "done_timeout"

        # autotest 仍在跑，同步推进一步（coordinator 定时任务调用，非阻塞）
        if phase == "autotest_building":
            # 用 asyncio.get_event_loop().run_until_complete 不安全，
            # get_report 由 coordinator 的 async 定时任务调用，直接返回 None 让下轮再查
            return None

        if not phase.startswith("done_"):
            return None

        return self._build_report(build)

    async def get_report_async(self, build_token: str) -> Optional[Dict]:
        """异步版 get_report，供 coordinator 定时任务调用。"""
        build = self._store.get_build(build_token)
        if not build:
            return None

        phase = build["phase"]

        # 超时检查
        if not phase.startswith("done_") and int(time.time()) - build["started_at"] > self._timeout_s:
            self._store.update_build(
                build_token,
                phase="done_timeout",
                report_json="构建+测试超过配置时限未完成，判定超时",
            )
            return self._build_report(self._store.get_build(build_token))

        # autotest 仍在跑，推进一步
        if phase == "autotest_building":
            await self._advance_autotest_building(build_token)
            build = self._store.get_build(build_token)
            phase = build["phase"] if build else "done_timeout"

        if not phase.startswith("done_"):
            return None

        return self._build_report(self._store.get_build(build_token))

    def _build_report(self, build: Optional[Dict]) -> Optional[Dict]:
        if not build:
            return None
        phase = build["phase"]
        report_json = build.get("report_json", "")
        report_path = build.get("report_path", "")
        if phase == "done_success":
            return {"phase": phase, "status": "success", "summary": report_json, "report_path": report_path, "failures": []}
        elif phase == "done_cicd_failure":
            summary = report_json if report_json.startswith("[构建失败]") else f"[构建失败] {report_json}"
            return {"phase": phase, "status": "failure", "summary": summary, "report_path": "", "failures": []}
        elif phase == "done_test_failure":
            return {"phase": phase, "status": "failure", "summary": report_json, "report_path": report_path, "failures": []}
        elif phase == "done_test_aborted":
            return {"phase": phase, "status": "failure", "summary": f"[测试任务未正常完成] {report_json}", "report_path": "", "failures": []}
        elif phase == "done_timeout":
            return {"phase": phase, "status": "timeout", "summary": report_json or "构建+测试超过配置时限未完成，判定超时", "report_path": "", "failures": []}
        return {"phase": phase, "status": "failure", "summary": report_json, "report_path": report_path, "failures": []}

    # ── cicd inline poll ─────────────────────────────────────────────────

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
            if resp.status_code not in (201, 303):
                raise RuntimeError(f"cicd trigger failed: {resp.status_code}")
            location = resp.headers.get("Location", "")
            m = re.search(r"/queue/item/(\d+)/", location)
            if not m:
                raise RuntimeError(f"cannot parse queue id from: {location}")
            self._store.update_cicd_build(build_token, repo, queue_id=m.group(1))
        except Exception as exc:
            logger.error("[Jenkins] trigger cicd failed repo=%s: %s", repo, exc)
            self._store.update_cicd_build(build_token, repo, result="FAILURE", console_snippet=str(exc))

    async def _poll_cicd_until_done(self, build_token: str) -> None:
        """inline poll cicd：queue → build_no → 等结果，直到全部 repo 完成。"""
        deadline = time.time() + 600  # cicd 最多等 10min
        while time.time() < deadline:
            rows = self._store.list_cicd_builds(build_token)

            # 等 queue → build_no
            for row in rows:
                if row["build_no"] == 0 and row["queue_id"] and row["result"] == "PENDING":
                    await self._resolve_queue_to_build_no(build_token, row)

            rows = self._store.list_cicd_builds(build_token)

            # 等构建结果
            for row in rows:
                if row["result"] == "PENDING" and row["build_no"] > 0:
                    await self._poll_cicd_build_result(build_token, row)

            rows = self._store.list_cicd_builds(build_token)
            pending = [r for r in rows if r["result"] == "PENDING"]
            failed = [r for r in rows if r["result"] in ("FAILURE", "ABORTED")]

            if failed:
                summaries = [f"{r['repo']}: {r['console_snippet'] or r['result']}" for r in failed]
                self._store.update_build(
                    build_token,
                    phase="done_cicd_failure",
                    report_json="[构建失败]\n" + "\n".join(summaries),
                )
                return

            if not pending:
                # 全部 SUCCESS
                return

            await asyncio.sleep(self._cicd_poll)

        # 超时
        self._store.update_build(
            build_token,
            phase="done_cicd_failure",
            report_json="[构建失败] cicd 构建超时（10min）",
        )

    async def _resolve_queue_to_build_no(self, build_token: str, row: Dict) -> None:
        url = f"{self._base}/queue/item/{row['queue_id']}/api/json"
        try:
            resp = await self._http.get(url)
            if resp.status_code == 404:
                self._store.update_cicd_build(build_token, row["repo"], result="FAILURE", console_snippet="queue item 已过期")
                return
            if resp.status_code != 200:
                return
            data = resp.json()
            executable = data.get("executable")
            if executable and executable.get("number"):
                self._store.update_cicd_build(build_token, row["repo"], build_no=executable["number"])
        except Exception as exc:
            logger.warning("[Jenkins] resolve queue failed repo=%s: %s", row["repo"], exc)

    async def _poll_cicd_build_result(self, build_token: str, row: Dict) -> None:
        url = f"{self._base}/job/{self._cicd_job}/{row['build_no']}/api/json"
        try:
            resp = await self._http.get(url)
            data = resp.json()
            if data.get("building"):
                return
            result = data.get("result", "ABORTED")
            self._store.update_cicd_build(build_token, row["repo"], result=result)
            if result in ("FAILURE", "ABORTED"):
                snippet = await self._get_console_snippet(self._cicd_job, row["build_no"])
                self._store.update_cicd_build(build_token, row["repo"], console_snippet=snippet)
        except Exception as exc:
            logger.warning("[Jenkins] poll cicd build failed repo=%s build_no=%s: %s", row["repo"], row["build_no"], exc)

    # ── autotest ─────────────────────────────────────────────────────────

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
            if resp.status_code not in (201, 303):
                raise RuntimeError(f"autotest trigger failed: {resp.status_code}")
            location = resp.headers.get("Location", "")
            m = re.search(r"/queue/item/(\d+)/", location)
            if not m:
                raise RuntimeError(f"cannot parse autotest queue id: {location}")
            self._store.update_build(build_token, phase="autotest_queued", autotest_queue_id=m.group(1))
        except Exception as exc:
            logger.error("[Jenkins] trigger autotest failed token=%s: %s", build_token, exc)
            self._store.update_build(build_token, phase="done_test_aborted", report_json=f"autotest 触发失败: {exc}")

    async def _wait_autotest_build_no(self, build_token: str) -> None:
        """等 autotest queue → build_no，拿到即推进到 autotest_building 并返回。"""
        deadline = time.time() + 120  # queue 等待最多 2min
        while time.time() < deadline:
            build = self._store.get_build(build_token)
            if not build or build["phase"].startswith("done_"):
                return
            if build["phase"] != "autotest_queued":
                return
            queue_id = build.get("autotest_queue_id", "")
            if not queue_id:
                self._store.update_build(build_token, phase="done_test_aborted", report_json="autotest_queue_id 丢失")
                return
            url = f"{self._base}/queue/item/{queue_id}/api/json"
            try:
                resp = await self._http.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    executable = data.get("executable")
                    if executable and executable.get("number"):
                        self._store.update_build(
                            build_token,
                            phase="autotest_building",
                            autotest_build_no=executable["number"],
                        )
                        return
            except Exception as exc:
                logger.warning("[Jenkins] wait autotest build_no failed: %s", exc)
            await asyncio.sleep(self._queue_poll)

        # 2min 内没拿到 build_no，标 aborted
        self._store.update_build(build_token, phase="done_test_aborted", report_json="autotest 排队超时2min）")

    async def _advance_autotest_building(self, build_token: str) -> None:
        """推进 autotest_building：轮询结果，完成后更新 phase。"""
        build = self._store.get_build(build_token)
        build_no = build.get("autotest_build_no", 0) if build else 0
        if not build_no:
            return
        url = f"{self._base}/job/{self._autotest_job}/{build_no}/api/json"
        try:
            resp = await self._http.get(url)
            data = resp.json()
            if data.get("building"):
                return
            result = data.get("result", "ABORTED")
            self._store.update_build(build_token, jenkins_result=result)

            build_url = data.get("url", f"{self._base}/job/{self._autotest_job}/{build_no}/")
            display_name = data.get("displayName", f"#{build_no}")
            duration_ms = data.get("duration", 0)
            duration_str = f"{duration_ms // 60000}min {(duration_ms % 60000) // 1000}s"
            report_json = (
                f"autotest {display_name} 结果：{result}\n"
                f"耗时：{duration_str}\n"
                f"构建地址：{build_url}"
            )

            if result in ("SUCCESS", "FAILURE"):
                report_path = await self._download_artifacts_report(build_token, data)
                phase = "done_success" if result == "SUCCESS" else "done_test_failure"
                self._store.update_build(
                    build_token,
                    phase=phase,
                    report_json=report_json,
                    report_path=report_path,
                )
            else:
                self._store.update_build(
                    build_token,
                    phase="done_test_aborted",
                    report_json=f"autotest 未正常完成，Jenkins result={result}",
                )
        except Exception as exc:
            logger.warning("[Jenkins] advance autotest building failed token=%s: %s", build_token, exc)

    # ── 工具方法 ─────────────────────────────────────────────────────────

    async def _download_artifacts_report(self, build_token: str, job_data: dict = None) -> str:
        """下载测试报告到本地临时文件，返回路径；失败返回空串。

        优先从 GitHub artifacts 仓库拉 *-run.md；不可用时 fallback 到
        Jenkins artifacts 里的 logs.log。
        """
        build = self._store.get_build(build_token)
        identifier = (build or {}).get("linear_identifier", "")
        dest = f"/tmp/repair/reports/{build_token}-run.md"

        # 1. GitHub artifacts（主路径）
        if self._github_artifacts and identifier:
            ok = await self._github_artifacts.download_latest_autotest_report(identifier, dest)
            if ok:
                return dest

        # 2. fallback：Jenkins artifacts 里的 logs.log
        if job_data:
            artifacts = job_data.get("artifacts") or []
            log_artifact = next(
                (a for a in artifacts if a.get("fileName", "").endswith(".log")),
                None,
            )
            if log_artifact:
                build_url = job_data.get("url", "")
                rel_path = log_artifact.get("relativePath", log_artifact["fileName"])
                log_url = f"{build_url}artifact/{rel_path}"
                try:
                    resp = await self._http.get(log_url)
                    if resp.status_code == 200:
                        from pathlib import Path as _Path
                        _Path(dest).parent.mkdir(parents=True, exist_ok=True)
                        _Path(dest).write_text(resp.text, encoding="utf-8")
                        return dest
                except Exception as exc:
                    logger.warning("[Jenkins] download logs.log failed token=%s: %s", build_token, exc)

        return ""

    async def _get_console_snippet(self, job: str, build_no: int, max_lines: int = 20) -> str:
        """拉构建日志末尾片段。失败静默返回空串。"""
        try:
            url = f"{self._base}/job/{job}/{build_no}/consoleText"
            resp = await self._http.get(url)
            lines = resp.text.strip().splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception:
            return ""

    async def aclose(self) -> None:
        await self._http.aclose()
