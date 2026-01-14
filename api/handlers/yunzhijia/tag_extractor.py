"""标签提取器 - 从消息内容中提取特定 XML 标签.

DEPRECATED: This module is deprecated and no longer used.
The system now uses Claude SDK native mechanisms:
- Direct output to ResultMessage.result (no tags needed)
- AskUserQuestion tool for user interaction (instead of <ask> tags)

This file is kept for potential rollback only.
"""

import re
import warnings
from typing import List

warnings.warn(
    "TagExtractor is deprecated. Use Claude SDK native mechanisms instead "
    "(ResultMessage.result and AskUserQuestion tool).",
    DeprecationWarning,
    stacklevel=2
)


class TagExtractor:
    """提取消息中的特定标签内容

    DEPRECATED: 不再使用标签系统。

    旧系统用于从 Agent 输出中提取 <reply> 和 <ask> 标签。
    新系统使用 Claude SDK 原生机制：
    - 直接输出到 ResultMessage.result
    - 使用 AskUserQuestion 工具询问用户
    """

    @staticmethod
    def extract_tags(content: str, tag_name: str) -> List[str]:
        """从内容中提取指定标签的内容

        Args:
            content: 消息内容
            tag_name: 标签名称（不包含尖括号）

        Returns:
            提取的内容列表（可能有多个相同标签）

        Examples:
            >>> TagExtractor.extract_tags("<reply>你好</reply>", "reply")
            ['你好']
            >>> TagExtractor.extract_tags("<ask>请问</ask><ask>如何</ask>", "ask")
            ['请问', '如何']
        """
        pattern = rf'<{tag_name}>(.*?)</{tag_name}>'
        matches = re.findall(pattern, content, re.DOTALL)
        return [m.strip() for m in matches if m.strip()]

    @staticmethod
    def extract_replies(content: str) -> List[str]:
        """提取 <reply> 标签内容

        用于提取 Agent 的最终回复内容。
        SKILL 规定最终答案必须包裹在 <reply> 标签中。

        Args:
            content: Agent 输出的消息内容

        Returns:
            回复内容列表
        """
        return TagExtractor.extract_tags(content, "reply")

    @staticmethod
    def extract_asks(content: str) -> List[str]:
        """提取 <ask> 标签内容

        用于提取需要用户回复的交互式问题。
        SKILL 规定询问用户的内容必须包裹在 <ask> 标签中。

        Args:
            content: Agent 输出的消息内容

        Returns:
            问题内容列表
        """
        return TagExtractor.extract_tags(content, "ask")
