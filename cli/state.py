"""REPL state management."""

from datetime import datetime
from typing import Optional

from api.models.requests import QueryRequest


class REPLState:
    """REPL state management."""

    def __init__(self, skill: str = "customer-service"):
        """初始化REPL状态

        Args:
            skill: 要使用的skill名称，默认为 customer-service
        """
        self.session_id: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.language: str = "中文"
        self.skill: str = skill
        self.session_history: list = []

    def build_request(self, prompt: str) -> QueryRequest:
        """Build QueryRequest with proper validation.

        Args:
            prompt: User prompt

        Returns:
            QueryRequest instance
        """
        return QueryRequest(
            tenant_id=self.tenant_id,
            prompt=prompt,
            skill=self.skill,
            language=self.language if not self.session_id else None,
            session_id=self.session_id,
            metadata={"source": "cli"}
        )

    def set_session(self, session_id: str):
        """Save session ID.

        Args:
            session_id: New session ID
        """
        self.session_id = session_id
        self.session_history.append({
            "session_id": session_id,
            "created_at": datetime.now().isoformat()
        })

    def clear_session(self):
        """Clear session to start new conversation."""
        self.session_id = None
