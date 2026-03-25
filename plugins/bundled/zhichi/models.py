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


class ThirdAlgorithmRespWrapper(BaseModel):
    """智齿第三方算法响应外层包装."""

    ret_code: str = "000000"
    ret_msg: str = "success"
    data: Optional["ThirdAlgorithmRespVo"] = None


class ThirdAlgorithmRespVo(BaseModel):
    """智齿第三方算法响应体."""

    llm_answer: str
    answer_type: str = "QA_DIRECT"
    robot_answer_message_type: str = "MESSAGE"
    success: bool = True
    message_end: bool = True
    hit_sensitive_word: bool = False
    roundid: Optional[str] = None
    runtimeid: Optional[str] = None
    questionid: Optional[str] = None
    companyid: Optional[str] = None
    lan: Optional[str] = None
    third_interface_info: Optional[dict] = None
    third_processid: Optional[str] = None
    third_nodeid: Optional[str] = None
    third_variable_value_enums: Optional[List[str]] = None
    third_variable_id: Optional[str] = None
