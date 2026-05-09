"""Describe images via a helper multimodal model (Anthropic Messages API over HTTP)."""

import asyncio
import logging
from typing import List

import httpx

from api.services.config_service import ModelConfig

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0
_DEFAULT_VISION_MODEL = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 1024

_SYSTEM_PROMPT = (
    "你是一个图片理解助手。用户会上传图片并提出问题，你需要准确、详尽地描述"
    "图片中与用户问题相关的所有关键信息，包括：文字内容、报错信息、接口名、"
    "traceId、按钮/界面状态、数据字段等。只输出描述，不要回答用户问题本身，"
    "也不要附带任何解释或推测。"
)


class VisionFallbackError(Exception):
    """Vision 降级识别失败时抛出。"""


def _build_headers(helper_cfg: ModelConfig) -> dict:
    token = helper_cfg.get_auth_token()
    if not token:
        raise VisionFallbackError(
            f"Vision helper {helper_cfg.name} 未配置 auth token（env: {helper_cfg.auth_token_env}）"
        )
    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if helper_cfg.auth_env_target in ("auth_token", "both"):
        headers["authorization"] = f"Bearer {token}"
    if helper_cfg.auth_env_target in ("api_key", "both"):
        headers["x-api-key"] = token
    return headers


async def _describe_one(
    client: httpx.AsyncClient,
    image_block: dict,
    user_question: str,
    helper_cfg: ModelConfig,
    index: int,
) -> str:
    model = helper_cfg.vision_model or _DEFAULT_VISION_MODEL
    user_text = (
        f"用户问题: {user_question}\n\n"
        f"请针对性描述图片中与该问题相关的全部关键信息。"
    )
    payload = {
        "model": model,
        "max_tokens": _MAX_OUTPUT_TOKENS,
        "system": _SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    image_block,
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    }
    url = helper_cfg.base_url.rstrip("/") + "/v1/messages"
    try:
        resp = await client.post(url, json=payload, headers=_build_headers(helper_cfg))
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise VisionFallbackError(f"图片 {index + 1} 识别请求失败: {e}") from e

    data = resp.json()
    parts = [blk.get("text", "") for blk in data.get("content", []) if blk.get("type") == "text"]
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        raise VisionFallbackError(f"图片 {index + 1} 识别返回空内容")
    return text


async def describe_images(
    image_blocks: List[dict],
    user_question: str,
    helper_cfg: ModelConfig,
) -> List[str]:
    """并发识别多张图片，返回每张图的文字描述。

    任一张失败即整体抛 VisionFallbackError——降级链路不吞错，让主流程显式告知用户。
    """
    if not image_blocks:
        return []

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        results = await asyncio.gather(
            *(
                _describe_one(client, block, user_question, helper_cfg, i)
                for i, block in enumerate(image_blocks)
            ),
            return_exceptions=True,
        )

    descriptions: List[str] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            raise VisionFallbackError(f"图片 {i + 1} 识别失败: {r}") from r
        descriptions.append(r)
    logger.info(f"Vision fallback described {len(descriptions)} image(s) via {helper_cfg.name}")
    return descriptions
