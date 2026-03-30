"""Request models for API endpoints."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, Any


class QueryRequest(BaseModel):
    """Generic request model for agent queries."""

    # Required fields
    tenant_id: Optional[str] = Field(None, description="租户ID")
    prompt: str = Field(..., min_length=1, description="用户请求")

    # Optional fields - generic
    skill: Optional[str] = Field(None, description="Skill 名称")
    language: Optional[str] = Field(None, description="响应语言 (新会话必填)")
    session_id: Optional[str] = Field(None, description="会话ID (续会话用)")
    context: Optional[str] = Field(None, description="附加上下文数据")
    metadata: Optional[Dict[str, Any]] = Field(None, description="扩展元数据")

    @field_validator('prompt')
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('prompt cannot be empty')
        return v.strip()

    @field_validator('language')
    @classmethod
    def language_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError('language cannot be empty string')
        return v.strip() if v else None

    @model_validator(mode='after')
    def validate_new_session_requirements(self):
        """Require language for new sessions only."""
        if not self.session_id:  # New session
            if not self.language:
                raise ValueError('language is required for new sessions')
        return self

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "summary": "New session",
                    "description": "Starting a new conversation (requires language)",
                    "value": {
                        "prompt": "如何配置开票模板？",
                        "skill": "customer-service",
                        "language": "中文",
                        "session_id": None
                    }
                },
                {
                    "summary": "Continuation session",
                    "description": "Resuming an existing conversation",
                    "value": {
                        "prompt": "继续前面的对话",
                        "session_id": "abc-123-def"
                    }
                }
            ]
        }
