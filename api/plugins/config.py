"""Plugin configuration service - manages plugins/config.json."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PluginConfigService:
    """Manages the plugins/config.json configuration file.

    Config format:
    {
        "enabled": ["yunzhijia"],
        "plugins": {
            "yunzhijia": {
                "session_timeout": 3600,
                "default_skill": "customer-service"
            }
        }
    }
    """

    def __init__(self, config_file: Path):
        self.config_file = config_file
        self._config: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load config from file, creating defaults if not found."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading plugin config: {e}")

        return {"enabled": [], "plugins": {}}

    def _save(self) -> None:
        """Save config to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved plugin config to {self.config_file}")

    def is_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is enabled."""
        return plugin_id in self._config.get("enabled", [])

    def get_plugin_config(self, plugin_id: str) -> Dict[str, Any]:
        """Get configuration for a specific plugin."""
        return self._config.get("plugins", {}).get(plugin_id, {})

    def get_enabled_list(self) -> List[str]:
        """Get list of enabled plugin IDs."""
        return list(self._config.get("enabled", []))

    def enable(self, plugin_id: str) -> None:
        """Enable a plugin."""
        enabled = self._config.setdefault("enabled", [])
        if plugin_id not in enabled:
            enabled.append(plugin_id)
            self._save()
            logger.info(f"Enabled plugin: {plugin_id}")

    def disable(self, plugin_id: str) -> None:
        """Disable a plugin."""
        enabled = self._config.get("enabled", [])
        if plugin_id in enabled:
            enabled.remove(plugin_id)
            self._save()
            logger.info(f"Disabled plugin: {plugin_id}")

    def update_plugin_config(self, plugin_id: str, config: Dict[str, Any]) -> None:
        """Update configuration for a specific plugin."""
        plugins = self._config.setdefault("plugins", {})
        plugins[plugin_id] = config
        self._save()
        logger.info(f"Updated config for plugin: {plugin_id}")

    def reload(self) -> None:
        """Reload config from disk."""
        self._config = self._load()
