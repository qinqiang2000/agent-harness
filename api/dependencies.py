"""Dependency injection container for services."""

import logging
import os
from functools import lru_cache

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
_yunzhijia_handler_instance = None


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


def get_yunzhijia_handler():
    """Get Yunzhijia handler (singleton)."""
    global _yunzhijia_handler_instance
    if _yunzhijia_handler_instance is None:
        from api.handlers.yunzhijia import YunzhijiaHandler
        agent_service = get_agent_service()
        session_service = get_session_service()
        default_skill = os.getenv("YZJ_DEFAULT_SKILL", "customer-service")
        _yunzhijia_handler_instance = YunzhijiaHandler(agent_service, session_service, default_skill)
        logger.info(f"Created YunzhijiaHandler instance with default_skill={default_skill}")
    return _yunzhijia_handler_instance


# Test utility function (for unit testing - resets all singletons)
def reset_services():
    """Reset all service instances (only for testing)."""
    global _session_service_instance, _config_service_instance, _agent_service_instance, _yunzhijia_handler_instance

    _session_service_instance = None
    _config_service_instance = None
    _agent_service_instance = None
    _yunzhijia_handler_instance = None
    logger.info("Reset all service instances")
