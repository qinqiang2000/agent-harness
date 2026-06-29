"""Open API 请求/响应数据模型."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class BaseResp(BaseModel):
    errcode: str = "0000"
    description: str = "操作成功"
    data: Optional[Any] = None


class TokenRespData(BaseModel):
    token: str
    expires_in: str  # 秒数字符串，与智齿文档一致


class InitRespData(BaseModel):
    ai_agent_cid: str
    biz_type: str = "AI_AGENT"


class AnswerReq(BaseModel):
    question: str
    ai_agent_cid: str
    uid: Optional[str] = None
    user_name: Optional[str] = None
    show_question: Optional[str] = None
    msg_type: Optional[str] = "TEXT"
    skill: Optional[str] = None  # 指定 skill，不传则使用默认 skill
    callback_url: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    images: Optional[List[str]] = None  # 图片 URL 列表，最多 5 张

    @field_validator('images')
    @classmethod
    def validate_images(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if not v:
            return None
        if len(v) > 5:
            raise ValueError('images 最多 5 张')
        for url in v:
            if not url.startswith(('http://', 'https://')):
                raise ValueError(f'图片 URL 必须以 http:// 或 https:// 开头: {url}')
        return v


class AnswerRespItem(BaseModel):
    answer: str
    robot_answer_type: str = "QA_DIRECT"
    robot_answer_message_type: str = "MESSAGE"
    ai_agent_cid: str
    roundid: Optional[str] = None
    transfer_result: Optional[str] = None


class AsyncAnswerRespData(BaseModel):
    task_id: str
    ai_agent_cid: str
    status: str = "PENDING"


class AsyncTaskResult(BaseModel):
    task_id: str
    status: str  # PENDING | DONE | ERROR
    ai_agent_cid: Optional[str] = None
    answer: Optional[str] = None
    robot_answer_type: str = "QA_DIRECT"
    transfer_result: Optional[str] = None


class EndSessionReq(BaseModel):
    ai_agent_cid: str


# ── Skill 版本管理请求模型 ─────────────────────────────────────────────────────

class SkillFileIn(BaseModel):
    filename: str
    filepath: str
    content: str


class CreateDraftReq(BaseModel):
    files: Optional[List[SkillFileIn]] = None
    operator: Optional[str] = None
    reason: Optional[str] = None


class UpdateDraftReq(BaseModel):
    files: List[SkillFileIn]
    operator: Optional[str] = None
    reason: Optional[str] = None


class RollbackReq(BaseModel):
    version: str           # 格式：{skill_name}:V{N}，如 customer-service:V1
    operator: Optional[str] = None
    reason: Optional[str] = None


# ── Replay 请求模型 ───────────────────────────────────────────────────────────

class ReplayReq(BaseModel):
    session_id: Optional[str] = None
    question: Optional[str] = None
    skill: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    use_latest_knowledge: bool = True
    skill_draft_version: Optional[str] = None  # 格式：{skill_name}:V{N}，如 customer-service:V2
