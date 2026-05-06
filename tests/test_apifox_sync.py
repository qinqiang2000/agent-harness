"""Tests for Apifox sync service."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


def test_build_api_headers():
    """测试请求头构建包含 Authorization"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="test-token", project_id="123")
    headers = svc._build_headers()
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["X-Apifox-Api-Version"] == "2024-01-20"


def test_format_endpoint_to_markdown():
    """测试单个接口格式化为 Markdown"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="t", project_id="p")
    endpoint = {
        "name": "查验发票",
        "method": "POST",
        "path": "/api/v1/invoice/verify",
        "description": "查验发票真伪",
        "status": "released",
    }
    md = svc._format_endpoint(endpoint)
    assert "查验发票" in md
    assert "POST" in md
    assert "/api/v1/invoice/verify" in md


def test_group_name_sanitize():
    """测试分组名称中的特殊字符被清理"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="t", project_id="p")
    assert svc._sanitize_filename("查验/接口") == "查验_接口"
    assert svc._sanitize_filename("开票 接口") == "开票_接口"


def test_flatten_tree_extracts_endpoints():
    """测试 _flatten_tree 正确提取接口"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="t", project_id="p")
    tree = [
        {
            "type": "apiDetailFolder",
            "name": "查验接口",
            "children": [
                {
                    "type": "apiDetail",
                    "name": "查验发票",
                    "api": {
                        "name": "查验发票",
                        "method": "POST",
                        "path": "/api/v1/verify",
                        "description": "查验",
                        "status": "released",
                    }
                }
            ]
        }
    ]
    groups = {}
    svc._flatten_tree(tree, groups, parent_name="")
    assert "查验接口" in groups
    assert len(groups["查验接口"]) == 1
    assert groups["查验接口"][0]["path"] == "/api/v1/verify"


@pytest.mark.asyncio
async def test_sync_returns_summary(tmp_path, monkeypatch):
    """测试 sync() 正常路径：mock HTTP，验证返回 summary 和文件写入"""
    import api.services.apifox_sync as m
    monkeypatch.setattr(m, "KB_API_DOC_DIR", tmp_path / "kb")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {
                "type": "apiDetailFolder",
                "name": "查验接口",
                "children": [
                    {
                        "type": "apiDetail",
                        "name": "查验发票",
                        "api": {
                            "name": "查验发票",
                            "method": "POST",
                            "path": "/api/v1/verify",
                            "description": "查验",
                            "status": "released",
                        }
                    }
                ]
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_resp)

        svc = m.ApifoxSyncService(token="t", project_id="p")
        result = await svc.sync(project_name="测试项目")

    assert result["groups"] == 1
    assert result["endpoints"] == 1
    project_dir = tmp_path / "kb" / "测试项目"
    assert (project_dir / "查验接口.md").exists()
    assert (project_dir / "_sync_meta.json").exists()


def test_create_sync_services_no_env(monkeypatch):
    """未配置环境变量时返回空列表"""
    monkeypatch.delenv("APIFOX_TOKEN", raising=False)
    monkeypatch.delenv("APIFOX_PROJECTS", raising=False)
    import importlib
    import api.services.apifox_sync as m
    importlib.reload(m)
    assert m.create_sync_services() == []


def test_create_sync_services_single(monkeypatch):
    """单项目配置"""
    monkeypatch.setenv("APIFOX_TOKEN", "tok")
    monkeypatch.setenv("APIFOX_PROJECTS", "发票云:123456")
    import importlib
    import api.services.apifox_sync as m
    importlib.reload(m)
    services = m.create_sync_services()
    assert len(services) == 1
    assert services[0][0] == "发票云"
    assert services[0][1].project_id == "123456"


def test_create_sync_services_multi(monkeypatch):
    """多项目配置"""
    monkeypatch.setenv("APIFOX_TOKEN", "tok")
    monkeypatch.setenv("APIFOX_PROJECTS", "发票云:111,星瀚:222")
    import importlib
    import api.services.apifox_sync as m
    importlib.reload(m)
    services = m.create_sync_services()
    assert len(services) == 2
    assert services[1][0] == "星瀚"
    assert services[1][1].project_id == "222"
