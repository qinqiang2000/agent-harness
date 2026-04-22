"""Open API 请求/响应数据模型."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


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
