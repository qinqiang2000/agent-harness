"""Dependency injection container for services."""

import logging
import os
from functools import lru_cache
from typing import Optional

from api.services.agent_service import AgentService
from api.services.session_service import InMemorySessionService
from api.services.config_service import ConfigService

logger = logging.getLogger(__name__)

# ============================================================================
# Global service instances (Singleton pattern, but exposed via functions for easier testing/mocking)
# ============================================================================

_session_service_instance = None
_config_service_instance = None
_agent_service_instance = None
_plugin_manager_instance = None


def get_session_service() -> InMemorySessionService:
    """Get session service (singleton)."""
    global _session_service_instance
    if _session_service_instance is None:
        _session_service_instance = InMemorySessionService()
        logger.info("Created InMemorySessionService instance")
    return _session_service_instance


def get_config_service() -> ConfigService:
    """Get config service (singleton)."""
    global _config_service_instance
    if _config_service_instance is None:
        _config_service_instance = ConfigService()
        logger.info("Created ConfigService instance")
    return _config_service_instance


def get_agent_service() -> AgentService:
    """Get agent service (singleton)."""
    global _agent_service_instance
    if _agent_service_instance is None:
        session_service = get_session_service()
        _agent_service_instance = AgentService(session_service=session_service)
        logger.info("Created AgentService instance")
    return _agent_service_instance


def get_plugin_manager():
    """Get plugin manager (singleton)."""
    global _plugin_manager_instance
    if _plugin_manager_instance is None:
        from pathlib import Path
        from api.plugins.manager import PluginManager
        from api.constants import BUNDLED_PLUGINS_DIR, INSTALLED_PLUGINS_DIR, PLUGIN_CONFIG_FILE

        agent_service = get_agent_service()
        session_service = get_session_service()

        # Parse extra plugin paths from environment
        extra_paths = None
        plugin_paths_env = os.getenv("PLUGIN_PATHS", "")
        if plugin_paths_env:
            extra_paths = [Path(p.strip()) for p in plugin_paths_env.split(":") if p.strip()]

        _plugin_manager_instance = PluginManager(
            bundled_dir=BUNDLED_PLUGINS_DIR,
            installed_dir=INSTALLED_PLUGINS_DIR,
            config_file=PLUGIN_CONFIG_FILE,
            agent_service=agent_service,
            session_service=session_service,
            extra_paths=extra_paths,
        )
        logger.info("Created PluginManager instance")
    return _plugin_manager_instance


# Test utility function (for unit testing - resets all singletons)
def reset_services():
    """Reset all service instances (only for testing)."""
    global _session_service_instance, _config_service_instance, _agent_service_instance, _plugin_manager_instance

    _session_service_instance = None
    _config_service_instance = None
    _agent_service_instance = None
    _plugin_manager_instance = None
    logger.info("Reset all service instances")
