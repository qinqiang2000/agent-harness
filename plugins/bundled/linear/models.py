"""Linear plugin Pydantic models."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class LinearActor(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    type: Optional[str] = None  # "user" | "app"


class LinearIssueData(BaseModel):
    id: str
    identifier: str
    title: str
    description: Optional[str] = None
    teamId: Optional[str] = None
    stateId: Optional[str] = None
    assigneeId: Optional[str] = None
    priorityLabel: Optional[str] = None


class LinearAgentSessionData(BaseModel):
    id: str
    status: Optional[str] = None
    issueId: Optional[str] = None
    promptContext: Optional[str] = None
    # prompted 事件中的用户消息
    prompt: Optional[str] = None


class LinearWebhookPayload(BaseModel):
    """Linear Webhook payload 通用结构。"""

    action: str  # "created" | "updated" | "prompted" | "stopped"
    type: str  # "AgentSession" | "Issue" | ...
    actor: Optional[LinearActor] = None
    createdAt: Optional[str] = None
    organizationId: Optional[str] = None
    webhookTimestamp: Optional[int] = None
    webhookId: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class AgentActivityContent(BaseModel):
    type: str  # "thought" | "action" | "elicitation" | "response" | "error"
    body: Optional[str] = None
    action: Optional[str] = None
    parameter: Optional[str] = None
    result: Optional[str] = None


class AgentSessionPlanItem(BaseModel):
    content: str
    status: str  # "pending" | "inProgress" | "completed" | "canceled"
