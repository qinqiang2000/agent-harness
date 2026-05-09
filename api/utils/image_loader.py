"""Fetch images via HTTP and build Anthropic image content blocks (base64)."""

import asyncio
import base64
import logging
from typing import List

import httpx

logger = logging.getLogger(__name__)

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_BYTES = 5 * 1024 * 1024
_TIMEOUT = 30.0


class ImageLoadError(Exception):
    """图片加载或校验失败时抛出。"""


async def _fetch_one(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url)
    resp.raise_for_status()
    content = resp.content
    if len(content) > _MAX_BYTES:
        raise ImageLoadError(f"图片超过 5MB 上限: {url} ({len(content)} bytes)")

    mime = (resp.headers.get("content-type", "") or "").split(";")[0].strip().lower()
    if mime not in _ALLOWED_MIME:
        if not mime or mime == "application/octet-stream":
            mime = "image/png"
        else:
            raise ImageLoadError(f"不支持的图片类型 {mime}: {url}")

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime,
            "data": base64.b64encode(content).decode("ascii"),
        },
    }


async def load_image_blocks(urls: List[str]) -> List[dict]:
    """并发加载图片并返回 Anthropic content block 列表。

    单张失败仅警告，全部失败才抛出 ImageLoadError。
    """
    if not urls:
        return []

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_fetch_one(client, url) for url in urls),
            return_exceptions=True,
        )

    blocks: List[dict] = []
    errors: List[str] = []
    for url, r in zip(urls, results):
        if isinstance(r, Exception):
            errors.append(f"{url}: {r}")
        else:
            blocks.append(r)

    if not blocks:
        raise ImageLoadError("所有图片加载失败: " + "; ".join(errors))
    if errors:
        logger.warning(f"部分图片加载失败: {errors}")
    return blocks
