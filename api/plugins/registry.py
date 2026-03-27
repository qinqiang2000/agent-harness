"""Plugin registry - tracks all discovered and loaded plugins."""
from __future__ import annotations

import logging
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from api.plugins.manifest import PluginManifest

if TYPE_CHECKING:
    from api.plugins.api import PluginAPI

logger = logging.getLogger(__name__)


class PluginState(str, Enum):
    """Plugin lifecycle states."""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    REGISTERED = "registered"
    STARTED = "started"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PluginInstance:
    """Represents a loaded plugin instance."""

    manifest: PluginManifest
    path: Path
    source: str  # "bundled" | "installed" | "external"
    state: PluginState = PluginState.DISCOVERED
    enabled: bool = False
    api: Optional[PluginAPI] = field(default=None, repr=False)
    plugin_object: Any = field(default=None, repr=False)  # ChannelPlugin or other
    error: Optional[str] = None

    @property
    def id(self) -> str:
        return self.manifest.id

    def to_dict(self) -> dict:
        """Serialize plugin instance to dict for API responses."""
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "type": self.manifest.type,
            "source": self.source,
            "state": self.state.value,
            "enabled": self.enabled,
            "error": self.error,
            "config_schema": self.manifest.config_schema,
        }


class PluginRegistry:
    """Central registry for all plugins."""

    def __init__(self):
        self._plugins: Dict[str, PluginInstance] = {}

    def register(self, instance: PluginInstance) -> None:
        """Register a plugin instance."""
        if instance.id in self._plugins:
            logger.warning(f"Plugin '{instance.id}' already registered, overwriting")
        self._plugins[instance.id] = instance
        logger.info(f"Registered plugin: {instance.id} ({instance.source})")

    def get(self, plugin_id: str) -> Optional[PluginInstance]:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)

    def get_all(self) -> list[PluginInstance]:
        """Get all registered plugins."""
        return list(self._plugins.values())

    def get_by_type(self, plugin_type: str) -> list[PluginInstance]:
        """Get all plugins of a specific type."""
        return [p for p in self._plugins.values() if p.manifest.type == plugin_type]

    def get_enabled(self) -> list[PluginInstance]:
        """Get all enabled plugins."""
        return [p for p in self._plugins.values() if p.enabled]

    def get_started(self) -> list[PluginInstance]:
        """Get all started plugins."""
        return [p for p in self._plugins.values() if p.state == PluginState.STARTED]

    def remove(self, plugin_id: str) -> Optional[PluginInstance]:
        """Remove a plugin from the registry."""
        return self._plugins.pop(plugin_id, None)

    def has(self, plugin_id: str) -> bool:
        """Check if a plugin is registered."""
        return plugin_id in self._plugins

    def count(self) -> int:
        """Get total number of registered plugins."""
        return len(self._plugins)
