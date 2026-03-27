"""Yunzhijia (云之家) message models."""

from pydantic import BaseModel
from typing import Optional


class YZJRobotMsg(BaseModel):
    """云之家机器人消息模型

    云之家群聊机器人接收到的消息结构。
    """
    type: int                           # 消息类型
    robotId: Optional[str] = None       # 机器人ID
    robotName: Optional[str] = None     # 机器人名称
    operatorName: Optional[str] = None  # 操作人姓名
    msgId: Optional[str] = None         # 消息ID
    operatorOpenid: str                 # 操作人OpenID（用于定向回复）
    content: str                        # 消息内容
    time: int                           # 消息时间戳
    sessionId: Optional[str] = None     # 会话ID（从请求头设置）
