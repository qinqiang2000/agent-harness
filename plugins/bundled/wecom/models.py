"""企业微信消息数据模型."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WecomMessage:
    """企业微信接收到的消息（解密后的 XML 解析结果）."""

    to_user_name: str        # 企业微信 CorpID
    from_user_name: str      # 发送者 UserID
    create_time: int         # 消息创建时间
    msg_type: str            # 消息类型：text / image / voice / event 等
    msg_id: Optional[str] = None
    agent_id: Optional[int] = None

    # text
    content: Optional[str] = None

    # event
    event: Optional[str] = None

    @classmethod
    def from_xml(cls, xml_str: str) -> "WecomMessage":
        root = ET.fromstring(xml_str)

        def text(tag: str) -> Optional[str]:
            el = root.find(tag)
            return el.text if el is not None else None

        agent_id_str = text("AgentID")
        msg_id_str = text("MsgId")
        create_time_str = text("CreateTime")

        return cls(
            to_user_name=text("ToUserName") or "",
            from_user_name=text("FromUserName") or "",
            create_time=int(create_time_str) if create_time_str else 0,
            msg_type=text("MsgType") or "",
            msg_id=msg_id_str,
            agent_id=int(agent_id_str) if agent_id_str else None,
            content=text("Content"),
            event=text("Event"),
        )
