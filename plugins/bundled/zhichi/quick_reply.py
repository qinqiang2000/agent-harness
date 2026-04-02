"""Quick reply generator: use AI to generate a contextual instant reply."""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是客服系统的即时应答模块。根据用户的第一条消息，生成一句自然、简短的即时回复（不超过15字）。

规则：
- 打招呼（你好、在吗、hi 等）→ 自然应答，如"你好，请说。"或"在的，请问有什么事？"
- 转人工请求 → 不提转人工，回复如"好的，让我先帮您看看。"
- 具体问题咨询 → 回复如"好的，帮您查一下。"或"收到，稍等一下。"
- 其他 → "收到，稍等一下。"

只输出回复内容，不要任何标点以外的多余内容，不要解释。"""

FALLBACK_REPLY = "您好！"
TIMEOUT_SECONDS = 2.5


async def generate_quick_reply(question: str) -> str:
    """Generate a contextual instant reply using AI. Falls back to default on error/timeout."""
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
            # No base_url and no key — official API but no key available, skip AI
            return FALLBACK_REPLY

        client = AsyncAnthropic(**kwargs)
        model = os.getenv("ANTHROPIC_SMALL_FAST_MODEL", "claude-haiku-4-5-20251001")

        resp = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=30,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": question}],
            ),
            timeout=TIMEOUT_SECONDS,
        )
        reply = resp.content[0].text.strip()
        logger.debug(f"[QuickReply] AI reply: {reply!r}")
        return reply

    except asyncio.TimeoutError:
        logger.warning("[QuickReply] Timed out, using fallback")
        return FALLBACK_REPLY
    except Exception as e:
        logger.warning(f"[QuickReply] Failed ({e}), using fallback")
        return FALLBACK_REPLY
