"""GitHub develop-workflow-artifacts 仓库客户端。

从 {owner}/{repo}/{identifier}/autotest/ 目录拉取最新 *-run.md 报告文件，
写入本地临时路径供 analyzer 读取，用完后由调用方删除。

环境变量：
  GITHUB_ARTIFACTS_REPO  仓库全名，如 invagent/develop-workflow-artifacts
  GITHUB_TOKEN           Personal Access Token 或 GitHub App token
"""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_MAX_REPORT_BYTES = 512 * 1024  # 512 KB，超出截断


class GitHubArtifactsClient:
    def __init__(self, repo: str, token: str):
        """
        Args:
            repo:  仓库全名，如 invagent/develop-workflow-artifacts
            token: GitHub token，空串时所有方法静默返回 False/None
        """
        self._repo = repo.strip()
        self._token = token.strip()

    def _enabled(self) -> bool:
        return bool(self._repo and self._token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def download_latest_autotest_report(
        self, identifier: str, dest_path: str
    ) -> bool:
        """拉取 {identifier}/autotest/ 下最新的 *-run.md，写入 dest_path。

        Returns:
            True  — 成功写入
            False — 未配置、无文件、网络失败等，均静默降级
        """
        if not self._enabled():
            return False

        try:
            content = await self._fetch_latest(identifier)
        except Exception:
            logger.warning(
                "[GitHubArtifacts] fetch failed for %s", identifier, exc_info=True
            )
            return False

        if content is None:
            logger.info("[GitHubArtifacts] no autotest report found for %s", identifier)
            return False

        try:
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            Path(dest_path).write_text(content, encoding="utf-8")
        except Exception:
            logger.warning(
                "[GitHubArtifacts] write failed: %s", dest_path, exc_info=True
            )
            return False

        logger.info(
            "[GitHubArtifacts] report downloaded: %s -> %s", identifier, dest_path
        )
        return True

    async def _fetch_latest(self, identifier: str) -> Optional[str]:
        """列目录取最新 *-run.md，返回文件文本内容，无则返回 None。"""
        async with httpx.AsyncClient(timeout=30, headers=self._headers()) as http:
            # 1. 列目录
            url = f"{_GITHUB_API}/repos/{self._repo}/contents/{identifier}/autotest"
            resp = await http.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            entries = resp.json()

            # 2. 过滤 *-run.md，按文件名（时间戳前缀）降序取最新
            run_files = [
                e for e in entries
                if isinstance(e, dict)
                and e.get("type") == "file"
                and e.get("name", "").endswith("-run.md")
            ]
            if not run_files:
                return None
            latest = max(run_files, key=lambda e: e["name"])

            # 3. 拉文件内容：超过 1MB 时 contents API 返回空 content，改用 blob API
            file_resp = await http.get(latest["url"])
            file_resp.raise_for_status()
            file_data = file_resp.json()
            if file_data.get("content"):
                raw = base64.b64decode(file_data["content"]).decode("utf-8", errors="replace")
            else:
                # 大文件走 git blob API，Accept raw 直接返回文本
                blob_url = f"{_GITHUB_API}/repos/{self._repo}/git/blobs/{latest['sha']}"
                blob_resp = await http.get(blob_url, headers={**self._headers(), "Accept": "application/vnd.github.raw+json"})
                blob_resp.raise_for_status()
                raw = blob_resp.text

            # 超大文件截断，保留头部（汇总行在文件前段）
            if len(raw.encode("utf-8")) > _MAX_REPORT_BYTES:
                raw = raw.encode("utf-8")[:_MAX_REPORT_BYTES].decode("utf-8", errors="ignore")
                raw += "\n\n...(报告过大，已截断)"

            return raw
