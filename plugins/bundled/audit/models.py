"""Pydantic models for the audit plugin."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """Uploaded file metadata."""
    name: str
    size: int
    type: str  # "pdf" or "image"
    path: str  # absolute path on server
    uploaded_at: str


class AuditRule(BaseModel):
    """A single natural language audit rule."""
    id: str
    text: str
    enabled: bool = True
    category: Optional[str] = None
    color: Optional[str] = None


class RulesPayload(BaseModel):
    """Rules collection for a tenant."""
    rules: List[AuditRule]


class AuditQueryRequest(BaseModel):
    """Request to run an audit."""
    tenant_id: str
    prompt: Optional[str] = Field(None, description="Optional natural language prompt")
    files: Optional[List[str]] = Field(None, description="Filenames to audit (None = all)")
    rule_ids: Optional[List[str]] = Field(None, description="Rule IDs to check (None = all enabled)")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class TenantConfig(BaseModel):
    """Tenant configuration."""
    tenant_id: str
    display_name: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    settings: Dict[str, Any] = Field(default_factory=dict)
