"""Plugin manager - top-level orchestrator for the plugin system."""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI

from api.plugins.api import PluginAPI
from api.plugins.config import PluginConfigService
from api.plugins.discovery import PluginDiscovery
from api.plugins.lifecycle import PluginLifecycle
from api.plugins.registry import PluginInstance, PluginRegistry, PluginState
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

logger = logging.getLogger(__name__)


class PluginManager:
    """Top-level plugin system orchestrator.

    Coordinates discovery, loading, registration, and lifecycle management.
    """

    def __init__(
        self,
        bundled_dir: Path,
        installed_dir: Path,
        config_file: Path,
        agent_service: AgentService,
        session_service: SessionService,
        extra_paths: Optional[List[Path]] = None,
    ):
        self.bundled_dir = bundled_dir
        self.installed_dir = installed_dir
        self.agent_service = agent_service
        self.session_service = session_service

        self.registry = PluginRegistry()
        self.config_service = PluginConfigService(config_file)
        self.lifecycle = PluginLifecycle()

        # Build search paths: (path, source_label)
        search_paths = [
            (bundled_dir, "bundled"),
            (installed_dir, "installed"),
        ]
        # Add extra paths from PLUGIN_PATHS env var
        if extra_paths:
            for p in extra_paths:
                search_paths.append((p, "external"))

        self.discovery = PluginDiscovery(search_paths)

    async def load_all(self, app: FastAPI) -> None:
        """Discover, load, and start all enabled plugins.

        Args:
            app: FastAPI application to register routers on
        """
        # 1. Discover all plugins
        instances = self.discovery.discover_all()
        for instance in instances:
            self.registry.register(instance)

        # 2. Load and start enabled plugins
        enabled_ids = self.config_service.get_enabled_list()
        for instance in self.registry.get_all():
            instance.enabled = instance.id in enabled_ids
            if not instance.enabled:
                logger.info(f"Plugin '{instance.id}' is disabled, skipping")
                continue

            await self._activate_plugin(instance, app)

        started = self.registry.get_started()
        logger.info(
            f"Plugin system initialized, "
            f"{len(started)}/{self.registry.count()} plugins started"
        )

    async def stop_all(self) -> None:
        """Stop all running plugins."""
        for instance in self.registry.get_started():
            await self.lifecycle.stop(instance)
        logger.info("All plugins stopped")

    async def enable_plugin(self, plugin_id: str, app: FastAPI) -> Optional[PluginInstance]:
        """Enable and start a plugin.

        Args:
            plugin_id: Plugin ID to enable
            app: FastAPI application

        Returns:
            PluginInstance if successful, None otherwise
        """
        instance = self.registry.get(plugin_id)
        if not instance:
            logger.error(f"Plugin not found: {plugin_id}")
            return None

        self.config_service.enable(plugin_id)
        instance.enabled = True

        if instance.state == PluginState.STARTED:
            return instance

        await self._activate_plugin(instance, app)
        return instance

    async def disable_plugin(self, plugin_id: str) -> Optional[PluginInstance]:
        """Disable and stop a plugin.

        Note: Router removal requires restart. The plugin is marked disabled
        and will not be loaded on next startup.

        Args:
            plugin_id: Plugin ID to disable

        Returns:
            PluginInstance if successful, None otherwise
        """
        instance = self.registry.get(plugin_id)
        if not instance:
            logger.error(f"Plugin not found: {plugin_id}")
            return None

        self.config_service.disable(plugin_id)
        instance.enabled = False

        if instance.state == PluginState.STARTED:
            await self.lifecycle.stop(instance)

        return instance

    def update_plugin_config(self, plugin_id: str, config: dict) -> bool:
        """Update plugin configuration.

        Args:
            plugin_id: Plugin ID
            config: New configuration dict

        Returns:
            True if successful
        """
        instance = self.registry.get(plugin_id)
        if not instance:
            return False

        self.config_service.update_plugin_config(plugin_id, config)
        return True

    def install_plugin(self, source_path: Path) -> Optional[PluginInstance]:
        """Install a plugin from a local path.

        Copies the plugin directory to installed_dir.

        Args:
            source_path: Path to the plugin directory

        Returns:
            PluginInstance if successful, None otherwise
        """
        # Discover the plugin first
        instance = self.discovery.discover_single(source_path, "installed")
        if not instance:
            logger.error(f"Invalid plugin at {source_path}")
            return None

        # Check for conflicts
        if self.registry.has(instance.id):
            logger.error(f"Plugin '{instance.id}' already exists")
            return None

        # Copy to installed directory
        dest = self.installed_dir / instance.id
        if dest.exists():
            logger.error(f"Plugin directory already exists: {dest}")
            return None

        self.installed_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_path, dest)
        logger.info(f"Installed plugin '{instance.id}' to {dest}")

        # Re-discover from installed location
        instance = self.discovery.discover_single(dest, "installed")
        if instance:
            self.registry.register(instance)

        return instance

    def get_plugin_info(self, plugin_id: str) -> Optional[dict]:
        """Get plugin information as dict."""
        instance = self.registry.get(plugin_id)
        if not instance:
            return None
        info = instance.to_dict()
        info["config"] = self.config_service.get_plugin_config(plugin_id)
        return info

    def list_plugins(self) -> List[dict]:
        """List all plugins as dicts."""
        return [p.to_dict() for p in self.registry.get_all()]

    async def _activate_plugin(self, instance: PluginInstance, app: FastAPI) -> bool:
        """Load, register, and start a plugin.

        Args:
            instance: Plugin instance to activate
            app: FastAPI application

        Returns:
            True if plugin was fully activated
        """
        # Load
        if not self.lifecycle.load(instance):
            return False

        # Create PluginAPI
        config = self.config_service.get_plugin_config(instance.id)
        api = PluginAPI(
            plugin_id=instance.id,
            config=config,
            agent_service=self.agent_service,
            session_service=self.session_service,
        )

        # Register
        if not self.lifecycle.register(instance, api):
            return False

        # Mount routers
        for router, prefix in api.routers:
            app.include_router(router, prefix=prefix)
            logger.info(f"Mounted router for plugin '{instance.id}' at '{prefix}'")

        # Start
        if not await self.lifecycle.start(instance):
            return False

        logger.info(f"Activated plugin: {instance.id} ({instance.manifest.type})")
        return True
