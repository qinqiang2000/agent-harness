"""Plugin discovery - scans directories to find plugins."""

import json
import logging
from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from api.plugins.manifest import PluginManifest
from api.plugins.registry import PluginInstance, PluginState

logger = logging.getLogger(__name__)


class PluginDiscovery:
    """Discovers plugins by scanning directories for plugin.json manifests."""

    MANIFEST_FILE = "plugin.json"

    def __init__(self, search_paths: List[Path]):
        """Initialize discovery with search paths.

        Args:
            search_paths: List of (path, source_label) tuples or just paths.
                          Will be searched in order.
        """
        self.search_paths = search_paths

    def discover_all(self) -> List[PluginInstance]:
        """Discover all plugins from configured search paths.

        Returns:
            List of discovered PluginInstance objects (state=DISCOVERED)
        """
        discovered = []
        seen_ids = set()

        for search_path, source in self.search_paths:
            if not search_path.exists():
                logger.debug(f"Plugin search path does not exist: {search_path}")
                continue

            plugins = self._scan_directory(search_path, source)
            for plugin in plugins:
                if plugin.id in seen_ids:
                    logger.warning(
                        f"Duplicate plugin ID '{plugin.id}' found at {plugin.path}, "
                        f"skipping (first-found wins)"
                    )
                    continue
                seen_ids.add(plugin.id)
                discovered.append(plugin)

        logger.info(f"Discovered {len(discovered)} plugin(s)")
        return discovered

    def discover_single(self, plugin_path: Path, source: str = "external") -> Optional[PluginInstance]:
        """Discover a single plugin from a specific path.

        Args:
            plugin_path: Path to the plugin directory
            source: Source label (e.g. "installed", "external")

        Returns:
            PluginInstance if valid, None otherwise
        """
        manifest_file = plugin_path / self.MANIFEST_FILE
        if not manifest_file.exists():
            logger.error(f"No {self.MANIFEST_FILE} found at {plugin_path}")
            return None
        return self._load_manifest(manifest_file, source)

    def _scan_directory(self, search_path: Path, source: str) -> List[PluginInstance]:
        """Scan a directory for plugin subdirectories.

        Args:
            search_path: Directory to scan
            source: Source label

        Returns:
            List of discovered plugins
        """
        plugins = []

        for item in sorted(search_path.iterdir()):
            if not item.is_dir():
                continue
            manifest_file = item / self.MANIFEST_FILE
            if not manifest_file.exists():
                continue

            instance = self._load_manifest(manifest_file, source)
            if instance:
                plugins.append(instance)

        return plugins

    def _load_manifest(self, manifest_file: Path, source: str) -> Optional[PluginInstance]:
        """Load and validate a plugin manifest.

        Args:
            manifest_file: Path to plugin.json
            source: Source label

        Returns:
            PluginInstance if valid, None otherwise
        """
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            manifest = PluginManifest(**data)
            plugin_dir = manifest_file.parent

            instance = PluginInstance(
                manifest=manifest,
                path=plugin_dir,
                source=source,
                state=PluginState.DISCOVERED,
            )
            logger.debug(f"Discovered plugin: {manifest.id} at {plugin_dir}")
            return instance

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {manifest_file}: {e}")
        except ValidationError as e:
            logger.error(f"Invalid manifest in {manifest_file}: {e}")
        except Exception as e:
            logger.error(f"Error loading {manifest_file}: {e}")

        return None
