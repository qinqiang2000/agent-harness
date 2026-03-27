"""File upload, listing, and deletion for audit plugin."""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile

from api.constants import TENANTS_DIR
from plugins.bundled.audit.models import FileInfo

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_SIZE_MB = 20


def _audit_files_dir(tenant_id: str) -> Path:
    """Get the audit files directory for a tenant."""
    d = TENANTS_DIR / tenant_id / "audit-files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _file_type(ext: str) -> str:
    return "pdf" if ext == "pdf" else "image"


async def save_upload(tenant_id: str, file: UploadFile, max_size_mb: int = MAX_UPLOAD_SIZE_MB) -> FileInfo:
    """Save an uploaded file and return its metadata."""
    ext = _get_extension(file.filename or "unknown")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: .{ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    size = len(content)

    if size > max_size_mb * 1024 * 1024:
        raise ValueError(f"File too large: {size / 1024 / 1024:.1f}MB (max {max_size_mb}MB)")

    dest_dir = _audit_files_dir(tenant_id)
    filename = file.filename or f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"

    # Avoid overwriting: append timestamp if file exists
    dest = dest_dir / filename
    if dest.exists():
        stem = dest.stem
        filename = f"{stem}_{datetime.now().strftime('%H%M%S')}{dest.suffix}"
        dest = dest_dir / filename

    dest.write_bytes(content)
    logger.info(f"[Audit] Saved upload: {dest} ({size} bytes)")

    return FileInfo(
        name=filename,
        size=size,
        type=_file_type(ext),
        path=str(dest),
        uploaded_at=datetime.now().isoformat(),
    )


def list_files(tenant_id: str) -> List[FileInfo]:
    """List all uploaded files for a tenant."""
    d = _audit_files_dir(tenant_id)
    files = []
    for f in sorted(d.iterdir()):
        if f.is_file() and _get_extension(f.name) in ALLOWED_EXTENSIONS:
            stat = f.stat()
            files.append(FileInfo(
                name=f.name,
                size=stat.st_size,
                type=_file_type(_get_extension(f.name)),
                path=str(f),
                uploaded_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            ))
    return files


def delete_file(tenant_id: str, filename: str) -> bool:
    """Delete a file. Returns True if deleted."""
    d = _audit_files_dir(tenant_id)
    target = d / filename
    if target.exists() and target.is_file():
        target.unlink()
        logger.info(f"[Audit] Deleted file: {target}")
        return True
    return False


def get_file_path(tenant_id: str, filename: str) -> Optional[Path]:
    """Get absolute path to a file if it exists."""
    d = _audit_files_dir(tenant_id)
    target = d / filename
    return target if target.exists() and target.is_file() else None
