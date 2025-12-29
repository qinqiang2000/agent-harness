"""Context file storage utilities."""

import logging
from datetime import datetime
from pathlib import Path

from api.constants import TENANTS_DIR

logger = logging.getLogger(__name__)


def save_context(tenant_id: str, context: str) -> str:
    """
    Save context data to file.

    Args:
        tenant_id: Tenant identifier
        context: Context data to save

    Returns:
        File path where the context was saved
    """
    # Create directory if not exists: data/tenants/{tenant_id}/contexts/
    contexts_dir = TENANTS_DIR / tenant_id / "contexts"
    contexts_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"context_{timestamp}.txt"
    file_path = contexts_dir / filename

    # Write context to file
    file_path.write_text(context, encoding='utf-8')

    logger.info(f"Saved context to: {file_path}")
    return str(file_path)
