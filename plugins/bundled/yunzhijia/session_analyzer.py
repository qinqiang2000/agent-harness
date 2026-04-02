"""Analyze the first message of a new session to detect product and problem.

Pure rule-based implementation — no LLM dependency.
"""

import logging
import re

logger = logging.getLogger(__name__)

# 产品别名 → 规范名称
_PRODUCT_ALIAS_MAP = {
    "标准版": "标准版发票云",
    "基础版": "标准版发票云",
    "aws": "标准版发票云",
    "aws发票云": "标准版发票云",
    "商家平台": "标准版发票云",
    "星瀚": "星瀚旗舰版",
    "旗舰版": "星瀚旗舰版",
    "星瀚发票云": "星瀚旗舰版",
    "星瀚旗舰版": "星瀚旗舰版",
    "星空旗舰版": "星空旗舰版",
    "星空": "星空旗舰版",
    "国际版": "国际版",
    "海外发票": "国际版",
    "国际发票": "国际版",
    "海外开票": "国际版",
}

# 问题关键词（含任一即视为描述了具体问题）
_PROBLEM_KEYWORDS = [
    "报错", "错误", "失败", "异常", "问题", "不能", "无法", "提示",
    "如何", "怎么", "怎样", "如何配置", "怎么配置",
    "配置", "设置", "开启", "关闭", "开通",
    "开票", "收票", "影像", "抵扣", "认证",
    "接口", "api", "对接", "集成", "参数",
    "查询", "搜索", "找不到",
    "登录", "账号", "密码", "权限",
    "通道", "乐企", "rpa", "数电",
    "支持", "能不能", "可以吗", "是否",
    "什么", "哪个", "哪些",
    "?", "？",
]

# 纯打招呼 / 无意义内容（精确匹配清理后的内容）
_GREETING_EXACT = {"你好", "您好", "hi", "hello", "hey", "哈喽", "嗨", "在吗", "在不在", "有人吗", "有人在吗"}

# 转人工关键词
_TRANSFER_KEYWORDS = {"转人工", "人工", "客服", "转接"}


def analyze_first_message(question: str) -> dict:
    """
    Rule-based analysis of whether the first message contains product and/or problem info.

    Returns:
        {"has_product": bool, "product": str|None, "has_problem": bool, "problem_summary": None}
    """
    # 清理 @机器人名 前缀
    cleaned = re.sub(r"@\S+\s*", "", question).strip()
    lower = cleaned.lower()

    # 检测产品
    product = None
    for alias, canonical in _PRODUCT_ALIAS_MAP.items():
        if alias.lower() in lower:
            product = canonical
            break
    has_product = product is not None

    # 检测问题
    is_greeting = cleaned in _GREETING_EXACT
    is_transfer_only = cleaned in _TRANSFER_KEYWORDS or (
        all(kw in lower for kw in ["转", "人工"]) and len(cleaned) <= 6
    )
    has_problem_keyword = any(kw in lower for kw in _PROBLEM_KEYWORDS)
    has_problem = not is_greeting and not is_transfer_only and (
        has_problem_keyword or len(cleaned) > 10
    )

    result = {
        "has_product": has_product,
        "product": product,
        "has_problem": has_problem,
        "problem_summary": None,
    }
    logger.debug(f"[SessionAnalyzer] {cleaned!r} → {result}")
    return result
