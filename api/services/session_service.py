"""
Session Management Service for Claude Agent SDK sessions.

This module manages active sessions and provides interrupt functionality.
Designed to be easily replaceable with Redis or other backends for multi-instance deployments.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional
from claude_agent_sdk import ClaudeSDKClient

logger = logging.getLogger(__name__)


class SessionService(ABC):
    """Abstract base class for session management."""

    @abstractmethod
    async def register(self, session_id: str, client: ClaudeSDKClient) -> None:
        """Register an active session."""
        pass

    @abstractmethod
    async def unregister(self, session_id: str) -> None:
        """Unregister a session."""
        pass

    @abstractmethod
    async def interrupt(self, session_id: str) -> bool:
        """Interrupt an active session. Returns True if successful."""
        pass

    @abstractmethod
    async def get_client(self, session_id: str) -> Optional[ClaudeSDKClient]:
        """Get session client."""
        pass


class InMemorySessionService(SessionService):
    """In-memory session manager for single-instance deployments."""

    def __init__(self):
        self._sessions: dict[str, ClaudeSDKClient] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, client: ClaudeSDKClient) -> None:
        async with self._lock:
            self._sessions[session_id] = client
            logger.info(f"Session registered: {session_id}")

    async def unregister(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session unregistered: {session_id}")

    async def interrupt(self, session_id: str) -> bool:
        async with self._lock:
            client = self._sessions.get(session_id)
            if client:
                try:
                    await client.interrupt()
                    logger.info(f"Session interrupted: {session_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to interrupt session {session_id}: {e}")
                    return False
            logger.warning(f"Session not found: {session_id}")
            return False

    async def get_client(self, session_id: str) -> Optional[ClaudeSDKClient]:
        async with self._lock:
            return self._sessions.get(session_id)
