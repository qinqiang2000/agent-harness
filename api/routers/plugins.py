"""Plugin management REST API endpoints."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import get_plugin_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class PluginConfigUpdate(BaseModel):
    """Request body for updating plugin configuration."""

    config: dict


class PluginInstallRequest(BaseModel):
    """Request body for installing a plugin from local path."""

    path: str


@router.get("/")
async def list_plugins():
    """List all discovered plugins and their status."""
    manager = get_plugin_manager()
    return {"plugins": manager.list_plugins()}


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str):
    """Get detailed information about a specific plugin."""
    manager = get_plugin_manager()
    info = manager.get_plugin_info(plugin_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return info


@router.post("/{plugin_id}/enable")
async def enable_plugin(plugin_id: str, request: Request):
    """Enable a plugin. Takes effect immediately (routers mounted).

    Note: Requires restart for full effect if the plugin was previously disabled.
    """
    manager = get_plugin_manager()
    instance = await manager.enable_plugin(plugin_id, request.app)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {
        "message": f"Plugin '{plugin_id}' enabled",
        "plugin": instance.to_dict(),
    }


@router.post("/{plugin_id}/disable")
async def disable_plugin(plugin_id: str):
    """Disable a plugin. Router removal requires restart."""
    manager = get_plugin_manager()
    instance = await manager.disable_plugin(plugin_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {
        "message": f"Plugin '{plugin_id}' disabled (restart to fully unload routes)",
        "plugin": instance.to_dict(),
    }


@router.put("/{plugin_id}/config")
async def update_plugin_config(plugin_id: str, body: PluginConfigUpdate):
    """Update plugin configuration. May require restart to take effect."""
    manager = get_plugin_manager()
    success = manager.update_plugin_config(plugin_id, body.config)
    if not success:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {"message": f"Configuration updated for plugin '{plugin_id}'"}


@router.post("/install")
async def install_plugin(body: PluginInstallRequest):
    """Install a plugin from a local path."""
    source_path = Path(body.path)
    if not source_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {body.path}")
    if not source_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {body.path}")

    manager = get_plugin_manager()
    instance = manager.install_plugin(source_path)
    if not instance:
        raise HTTPException(
            status_code=400,
            detail="Failed to install plugin. Check logs for details.",
        )
    return {
        "message": f"Plugin '{instance.id}' installed. Use /enable to activate.",
        "plugin": instance.to_dict(),
    }
