"""Analyze the first message of a new session to detect product and problem."""

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个消息分析模块。分析用户消息，判断是否包含以下两类信息：

1. **产品**：是否明确提到了以下产品之一（含别名）
   - 标准版发票云（aws发票云、标准版、商家平台）
   - 星瀚旗舰版（星瀚发票云、星瀚、旗舰版）
   - 星空旗舰版（发票云for星空旗舰版、星空旗舰版）
   - 国际版（海外发票、国际发票、海外开票）

2. **问题**：是否描述了具体问题或诉求（报错、功能咨询、配置、操作等）
   - 不算问题：纯打招呼、"在吗"、"转人工"、"你好"等

以 JSON 格式返回，不要任何解释：
{
  "has_product": true/false,
  "product": "识别到的产品名称，未识别则为null",
  "has_problem": true/false,
  "problem_summary": "用户问题的简短摘要（10字以内），未识别则为null"
}"""

TIMEOUT_SECONDS = 3.0


async def analyze_first_message(question: str) -> dict:
    """
    Analyze whether the first message contains product and/or problem info.

    Returns:
        {"has_product": bool, "has_problem": bool}
    """
    try:
        from anthropic import AsyncAnthropic

        kwargs = {}
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url

        api_key = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        elif not base_url:
            return _fallback(question)

        client = AsyncAnthropic(**kwargs)
        model = os.getenv("ANTHROPIC_SMALL_FAST_MODEL", "claude-haiku-4-5-20251001")

        resp = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=60,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": question}],
            ),
            timeout=TIMEOUT_SECONDS,
        )
        result = json.loads(resp.content[0].text.strip())
        logger.debug(f"[SessionAnalyzer] {question!r} → {result}")
        return result

    except asyncio.TimeoutError:
        logger.warning("[SessionAnalyzer] Timed out, using fallback")
        return _fallback(question)
    except Exception as e:
        logger.warning(f"[SessionAnalyzer] Failed ({e}), using fallback")
        return _fallback(question)


# 产品关键词（fallback 用）
_PRODUCT_KEYWORDS = ["标准版", "星瀚", "旗舰版", "星空", "国际版", "aws", "商家平台", "海外发票", "海外开票"]
# 打招呼关键词（fallback 用）
_GREETING_PATTERN = {"你好", "您好", "hi", "hello", "在吗", "有人吗", "转人工", "人工"}


def _fallback(question: str) -> dict:
    """Rule-based fallback when AI is unavailable."""
    q = question.lower()
    has_product = any(kw in q for kw in _PRODUCT_KEYWORDS)
    product = next((kw for kw in _PRODUCT_KEYWORDS if kw in q), None)
    has_problem = len(question.strip()) > 5 and not any(kw in q for kw in _GREETING_PATTERN)
    return {
        "has_product": has_product,
        "product": product,
        "has_problem": has_problem,
        "problem_summary": None,
    }
