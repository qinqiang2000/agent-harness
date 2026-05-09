"""企业微信群机器人消息数据模型."""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


@dataclass
class WecomGroupMessage:
    """企业微信群机器人接收到的消息（解密后解析结果，支持 JSON 和 XML）."""

    from_user_name: str      # 发送者 UserID
    msg_type: str            # 消息类型：text / image / voice / event 等
    chat_id: Optional[str] = None       # 群聊 ID
    response_url: Optional[str] = None  # 回复消息用的 URL（智能机器人模式）
    webhook_url: Optional[str] = None   # 群机器人 Webhook URL（普通机器人模式）
    msg_id: Optional[str] = None
    create_time: int = 0
    to_user_name: str = ""

    # text
    content: Optional[str] = None

    # event
    event: Optional[str] = None

    @classmethod
    def from_payload(cls, plaintext: str) -> "WecomGroupMessage":
        """自动识别 JSON 或 XML 格式并解析."""
        if plaintext.strip().startswith("{"):
            return cls._from_json(plaintext)
        return cls._from_xml(plaintext)

    @classmethod
    def _from_json(cls, json_str: str) -> "WecomGroupMessage":
        """解析智能机器人 JSON 格式消息."""
        data = json.loads(json_str)
        from_info = data.get("from", {})
        user_id = from_info.get("userid", "") or from_info.get("alias", "")

        content = None
        msg_type = data.get("msgtype", "")
        if msg_type == "text":
            text_data = data.get("text", {})
            content = text_data.get("content", "") if isinstance(text_data, dict) else ""

        return cls(
            from_user_name=user_id,
            msg_type=msg_type,
            chat_id=data.get("chatid"),
            response_url=data.get("response_url"),
            msg_id=data.get("msgid"),
            content=content,
        )

    @classmethod
    def _from_xml(cls, xml_str: str) -> "WecomGroupMessage":
        """解析普通群机器人 XML 格式消息."""
        root = ET.fromstring(xml_str)

        def text(tag: str) -> Optional[str]:
            el = root.find(tag)
            return el.text if el is not None else None

        create_time_str = text("CreateTime")

        return cls(
            to_user_name=text("ToUserName") or "",
            from_user_name=text("FromUserName") or "",
            create_time=int(create_time_str) if create_time_str else 0,
            msg_type=text("MsgType") or "",
            chat_id=text("ChatId"),
            webhook_url=text("WebhookUrl"),
            msg_id=text("MsgId"),
            content=text("Content"),
            event=text("Event"),
        )
