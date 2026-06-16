import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.bundled.repair.github_artifacts_client import GitHubArtifactsClient


def _make_client(repo="invagent/develop-workflow-artifacts", token="ghp_test"):
    return GitHubArtifactsClient(repo=repo, token=token)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


@pytest.mark.asyncio
async def test_download_success(tmp_path):
    client = _make_client()
    dest = str(tmp_path / "report.md")
    report_content = "# 测试报告\n\n## 汇总\n成功: 5, 失败: 0"

    dir_resp = MagicMock()
    dir_resp.status_code = 200
    dir_resp.raise_for_status = MagicMock()
    dir_resp.json.return_value = [
        {"type": "file", "name": "2026-04-27-20-00-00-run.md", "url": "https://api.github.com/file1"},
        {"type": "file", "name": "2026-04-27-21-00-00-run.md", "url": "https://api.github.com/file2"},
    ]

    file_resp = MagicMock()
    file_resp.status_code = 200
    file_resp.raise_for_status = MagicMock()
    file_resp.json.return_value = {"content": _b64(report_content)}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(side_effect=[dir_resp, file_resp])

    with patch("plugins.bundled.repair.github_artifacts_client.httpx.AsyncClient", return_value=mock_http):
        ok = await client.download_latest_autotest_report("INV-123", dest)

    assert ok
    assert Path(dest).read_text() == report_content
    # 取最新文件（file2，时间戳更大）
    call_args = mock_http.get.call_args_list
    assert "file2" in call_args[1][0][0]


@pytest.mark.asyncio
async def test_download_no_files(tmp_path):
    client = _make_client()
    dest = str(tmp_path / "report.md")

    dir_resp = MagicMock()
    dir_resp.status_code = 200
    dir_resp.raise_for_status = MagicMock()
    dir_resp.json.return_value = [
        {"type": "dir", "name": "subdir", "url": "https://api.github.com/subdir"},
    ]

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(return_value=dir_resp)

    with patch("plugins.bundled.repair.github_artifacts_client.httpx.AsyncClient", return_value=mock_http):
        ok = await client.download_latest_autotest_report("INV-123", dest)

    assert not ok
    assert not Path(dest).exists()


@pytest.mark.asyncio
async def test_download_404_directory(tmp_path):
    client = _make_client()
    dest = str(tmp_path / "report.md")

    dir_resp = MagicMock()
    dir_resp.status_code = 404
    dir_resp.raise_for_status = MagicMock()
    dir_resp.json.return_value = []

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(return_value=dir_resp)

    with patch("plugins.bundled.repair.github_artifacts_client.httpx.AsyncClient", return_value=mock_http):
        ok = await client.download_latest_autotest_report("INV-999", dest)

    assert not ok


@pytest.mark.asyncio
async def test_download_disabled_when_no_token(tmp_path):
    client = GitHubArtifactsClient(repo="invagent/repo", token="")
    dest = str(tmp_path / "report.md")
    ok = await client.download_latest_autotest_report("INV-123", dest)
    assert not ok


@pytest.mark.asyncio
async def test_download_network_error_returns_false(tmp_path):
    import httpx as _httpx
    client = _make_client()
    dest = str(tmp_path / "report.md")

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(side_effect=_httpx.ConnectError("network down"))

    with patch("plugins.bundled.repair.github_artifacts_client.httpx.AsyncClient", return_value=mock_http):
        ok = await client.download_latest_autotest_report("INV-123", dest)

    assert not ok


@pytest.mark.asyncio
async def test_download_truncates_large_report(tmp_path):
    client = _make_client()
    dest = str(tmp_path / "report.md")
    large_content = "x" * (512 * 1024 + 100)

    dir_resp = MagicMock()
    dir_resp.status_code = 200
    dir_resp.raise_for_status = MagicMock()
    dir_resp.json.return_value = [
        {"type": "file", "name": "2026-04-27-20-00-00-run.md", "url": "https://api.github.com/file1"},
    ]

    file_resp = MagicMock()
    file_resp.status_code = 200
    file_resp.raise_for_status = MagicMock()
    file_resp.json.return_value = {"content": _b64(large_content)}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(side_effect=[dir_resp, file_resp])

    with patch("plugins.bundled.repair.github_artifacts_client.httpx.AsyncClient", return_value=mock_http):
        ok = await client.download_latest_autotest_report("INV-123", dest)

    assert ok
    written = Path(dest).read_text()
    assert "已截断" in written
    assert len(written.encode()) <= 512 * 1024 + 200  # 截断 + 截断提示
