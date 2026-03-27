"""Generic session mapper for channel plugins.

Extracted from yunzhijia's SessionMapper to be reusable across all channel plugins.
Maps external platform session IDs to internal agent session IDs with timeout management.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Session mapping information."""

    agent_session_id: str
    last_active: float
    pending_questions: Optional[list] = None  # AskUserQuestion awaiting reply


class PluginSessionMapper:
    """Generic session mapper for channel plugins.

    Maps external_session_id ↔ agent_session_id with automatic timeout handling.
    """

    def __init__(self, timeout_seconds: int, channel_id: str = "plugin"):
        """Initialize session mapper.

        Args:
            timeout_seconds: Session timeout in seconds
            channel_id: Channel identifier for logging
        """
        self.timeout_seconds = timeout_seconds
        self.channel_id = channel_id
        self.session_map: Dict[str, SessionInfo] = {}

    def get_or_create(self, external_session_id: str) -> Optional[str]:
        """Get valid agent_session_id or None if expired/new.

        Args:
            external_session_id: External platform session ID

        Returns:
            Agent session ID if valid, None if needs new session
        """
        if external_session_id not in self.session_map:
            return None

        session_info = self.session_map[external_session_id]
        elapsed = time.time() - session_info.last_active

        if elapsed > self.timeout_seconds:
            logger.info(
                f"[{self.channel_id}] Session timeout: external={external_session_id}, "
                f"agent={session_info.agent_session_id}, "
                f"inactive={elapsed:.0f}s (threshold={self.timeout_seconds}s)"
            )
            del self.session_map[external_session_id]
            return None

        return session_info.agent_session_id

    def update_activity(self, external_session_id: str, agent_session_id: str) -> None:
        """Update session activity timestamp.

        Args:
            external_session_id: External platform session ID
            agent_session_id: Agent session ID
        """
        self.session_map[external_session_id] = SessionInfo(
            agent_session_id=agent_session_id,
            last_active=time.time(),
        )

    def set_pending_questions(self, external_session_id: str, questions: list) -> None:
        """Store pending AskUserQuestion questions for a session.

        Args:
            external_session_id: External platform session ID
            questions: List of question dicts from AskUserQuestion
        """
        if external_session_id in self.session_map:
            self.session_map[external_session_id].pending_questions = questions

    def get_and_clear_pending_questions(self, external_session_id: str) -> Optional[list]:
        """Get and clear pending questions for a session.

        Args:
            external_session_id: External platform session ID

        Returns:
            List of pending questions, or None if no pending questions
        """
        if external_session_id not in self.session_map:
            return None

        questions = self.session_map[external_session_id].pending_questions
        if questions:
            self.session_map[external_session_id].pending_questions = None
        return questions

    def cleanup_expired(self) -> None:
        """Remove all expired sessions."""
        current_time = time.time()
        expired = [
            sid
            for sid, info in self.session_map.items()
            if (current_time - info.last_active) > self.timeout_seconds
        ]

        for sid in expired:
            info = self.session_map[sid]
            logger.info(
                f"[{self.channel_id}] Cleaning expired: external={sid}, "
                f"agent={info.agent_session_id}"
            )
            del self.session_map[sid]

        if expired:
            logger.info(f"[{self.channel_id}] Cleaned {len(expired)} expired sessions")

    def get_stats(self) -> dict:
        """Get session statistics."""
        current_time = time.time()
        sessions = []

        for external_id, info in self.session_map.items():
            inactive = current_time - info.last_active
            sessions.append({
                "external_session_id": external_id,
                "agent_session_id": info.agent_session_id,
                "inactive_seconds": int(inactive),
                "will_expire_in": max(0, int(self.timeout_seconds - inactive)),
            })

        return {
            "channel_id": self.channel_id,
            "total_sessions": len(self.session_map),
            "session_timeout_seconds": self.timeout_seconds,
            "sessions": sessions,
        }
