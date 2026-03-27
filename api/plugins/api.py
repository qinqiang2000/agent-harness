"""PluginAPI - the API object passed to each plugin's register() function."""

import logging
from typing import Callable, Optional

from fastapi import APIRouter

from api.services.agent_service import AgentService
from api.services.session_service import SessionService


class PluginAPI:
    """API object provided to plugins during registration.

    Plugins use this to register routes, hooks, and access core services.
    """

    def __init__(
        self,
        plugin_id: str,
        config: dict,
        agent_service: AgentService,
        session_service: SessionService,
    ):
        self.plugin_id = plugin_id
        self.config = config
        self.agent_service = agent_service
        self.session_service = session_service
        self._routers: list[tuple[APIRouter, str]] = []
        self._hooks: dict[str, list[Callable]] = {}
        self._logger = logging.getLogger(f"plugin.{plugin_id}")

    def register_router(self, router: APIRouter, prefix: str = "") -> None:
        """Register a FastAPI router for this plugin.

        Args:
            router: FastAPI APIRouter instance
            prefix: URL prefix for the router (e.g. "/yzj")
        """
        self._routers.append((router, prefix))
        self._logger.info(f"Registered router with prefix '{prefix}'")

    def register_hook(self, hook_type: str, handler: Callable) -> None:
        """Register a lifecycle hook handler.

        Args:
            hook_type: Hook type (e.g. 'pre_query', 'post_query', 'message_received')
            handler: Async callable hook handler
        """
        if hook_type not in self._hooks:
            self._hooks[hook_type] = []
        self._hooks[hook_type].append(handler)
        self._logger.info(f"Registered hook: {hook_type}")

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """Get a logger for this plugin.

        Args:
            name: Optional sub-logger name (appended to plugin.{plugin_id})

        Returns:
            Logger instance
        """
        if name:
            return logging.getLogger(f"plugin.{self.plugin_id}.{name}")
        return self._logger

    @property
    def routers(self) -> list[tuple[APIRouter, str]]:
        """Get all registered routers."""
        return self._routers

    @property
    def hooks(self) -> dict[str, list[Callable]]:
        """Get all registered hooks."""
        return self._hooks
