"""Channel plugin abstract base class and related types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import APIRouter


@dataclass
class ChannelMeta:
    """Channel metadata."""

    id: str
    name: str
    webhook_path: str  # e.g. "/yzj/chat"
    description: str = ""


@dataclass
class ChannelCapabilities:
    """Declares what a channel can do."""

    send_text: bool = True
    send_images: bool = False
    send_cards: bool = False
    receive_webhook: bool = True
    session_management: bool = True


class ChannelPlugin(ABC):
    """Abstract base class for channel plugins.

    Channel plugins bridge external messaging platforms with the agent service.
    """

    @abstractmethod
    def get_meta(self) -> ChannelMeta:
        """Return channel metadata."""
        ...

    @abstractmethod
    def get_capabilities(self) -> ChannelCapabilities:
        """Return channel capabilities."""
        ...

    @abstractmethod
    def create_router(self) -> APIRouter:
        """Create and return the FastAPI router for this channel."""
        ...

    @abstractmethod
    async def send_text(self, recipient_id: str, text: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Send a text message to a recipient.

        Args:
            recipient_id: Target recipient identifier
            text: Message text
            context: Optional context (e.g. token, session info)

        Returns:
            True if sent successfully
        """
        ...

    async def on_start(self) -> None:
        """Called when the plugin is started. Override for initialization."""
        pass

    async def on_stop(self) -> None:
        """Called when the plugin is stopped. Override for cleanup."""
        pass
