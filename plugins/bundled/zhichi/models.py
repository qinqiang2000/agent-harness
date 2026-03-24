"""智齿客服机器人请求/响应数据模型."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ThirdAlgorithmReqVo(BaseModel):
    """智齿第三方算法请求体."""

    question: str
    ai_agent_cid: str
    uid: Optional[str] = None
    user_name: Optional[str] = None
    show_question: Optional[str] = None
    robotid: Optional[str] = None
    msg_type: Optional[str] = None
    req_stream: bool = False
    copilot: bool = False
    robot_model: Optional[str] = "THIRD_STANDARD"
    input_type_enum: Optional[str] = "INPUT"
    params: Optional[Dict[str, Any]] = None
    multi_params: Optional[List[Any]] = None
    runtimeid: Optional[str] = None


class ThirdAlgorithmRespVo(BaseModel):
    """智齿第三方算法响应体."""

    ai_agent_cid: str
    llm_answer: str
    answer_type: str = "text"
    robot_answer_message_type: str = "THIRD_ANSWER_INFO"
    roundid: Optional[str] = None
    third_transfer_flag: bool = False
    third_interface_info: Optional[dict] = None
