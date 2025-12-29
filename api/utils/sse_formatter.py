"""SSE (Server-Sent Events) message formatting utilities."""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def format_sse_message(event_type: str, data: Any) -> Dict[str, str]:
    """
    Format a message as Server-Sent Events (SSE) format.

    Args:
        event_type: Event type (e.g., 'user_message', 'assistant_message')
        data: Event data (will be JSON-serialized if not a string)

    Returns:
        Dict with 'event' and 'data' keys for EventSourceResponse
    """
    if isinstance(data, str):
        data_dict = {"content": data}
    else:
        data_dict = data

    # Explicitly convert to JSON to ensure proper formatting
    ret = {"event": event_type, "data": json.dumps(data_dict, ensure_ascii=False)}
    logger.info(f"format_sse_message: {ret}")
    return ret
