"""Quick reply generator: rule-based contextual instant reply."""

import re

GREETING_PATTERN = re.compile(
    r"^[\s\W]*(你好|您好|hi|hello|hey|在吗|在不在|有人吗|有人在吗|哈喽|嗨)[\s\W]*$",
    re.IGNORECASE,
)


def generate_quick_reply(question: str) -> str:
    """Return a contextual instant reply based on simple keyword rules."""
    if GREETING_PATTERN.match(question.strip()):
        return "你好，请说～"
    return "收到～正在帮您查询"
