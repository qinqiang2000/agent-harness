"""智齿 OAuth Token 管理器 - 获取、缓存、后台自动刷新."""

import asyncio
import hashlib
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ZhichiTokenManager:
    """管理智齿 API Token（MD5 签名获取，24h 有效期，自动后台刷新）.

    签名公式（待与智齿官方文档确认）:
        MD5(app_id + app_key + timestamp)
    Token API 响应字段（待确认）:
        {"ret_code": 0, "token": "xxx", "expires_in": 86400}
    """

    def __init__(
        self,
        app_id: str,
        app_key: str,
        token_api_url: str = "https://www.sobot.com/api/get_token",
        refresh_buffer_seconds: int = 300,
    ):
        self.app_id = app_id
        self.app_key = app_key
        self.token_api_url = token_api_url
        self.refresh_buffer_seconds = refresh_buffer_seconds

        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._bg_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_token(self) -> str:
        """返回有效 Token，过期则同步刷新."""
        if self._is_valid():
            return self._token  # type: ignore[return-value]
        async with self._lock:
            # 双重检查：锁内再次判断
            if self._is_valid():
                return self._token  # type: ignore[return-value]
            await self._fetch_and_store()
            return self._token  # type: ignore[return-value]

    def start_background_refresh(self) -> None:
        """启动后台 Token 刷新循环（在 plugin.on_start 中调用）."""
        if self._bg_task and not self._bg_task.done():
            return
        self._bg_task = asyncio.create_task(self._refresh_loop())
        logger.info("[Zhichi] Background token refresh started")

    def stop_background_refresh(self) -> None:
        """停止后台刷新（在 plugin.on_stop 中调用）."""
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            logger.info("[Zhichi] Background token refresh stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_valid(self) -> bool:
        return bool(self._token) and time.time() < self._expires_at

    def _build_signature(self, timestamp: int) -> str:
        """MD5(appid + create_time + app_key)，时间戳为秒级."""
        raw = f"{self.app_id}{timestamp}{self.app_key}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def _fetch_and_store(self) -> None:
        """调用智齿 Token API 并更新缓存."""
        timestamp = int(time.time())  # 秒级时间戳
        sign = self._build_signature(timestamp)

        params = {
            "appid": self.app_id,
            "sign": sign,
            "create_time": timestamp,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.token_api_url, params=params)
                resp.raise_for_status()
                data = resp.json()

            ret_code = data.get("ret_code", "")
            if ret_code != "000000":
                raise ValueError(f"Token API error: ret_code={ret_code}, msg={data.get('ret_msg')}")

            item = data.get("item", {})
            token = item.get("token")
            if not token:
                raise ValueError(f"No token field in response: {data}")

            expires_in = int(item.get("expires_in", 86400))  # 默认 24h
            self._token = token
            self._expires_at = time.time() + expires_in
            logger.info(f"[Zhichi] Token refreshed, expires in {expires_in}s")

        except Exception as e:
            logger.error(f"[Zhichi] Failed to fetch token: {e}", exc_info=True)
            raise

    async def _refresh_loop(self) -> None:
        """后台刷新循环：在 Token 到期前 buffer 秒自动刷新."""
        while True:
            try:
                if not self._is_valid():
                    async with self._lock:
                        if not self._is_valid():
                            await self._fetch_and_store()

                # 动态计算下次唤醒时间
                sleep_seconds = max(
                    self._expires_at - time.time() - self.refresh_buffer_seconds,
                    60,  # 最短 60s，避免忙轮询
                )
                logger.debug(f"[Zhichi] Next token refresh in {sleep_seconds:.0f}s")
                await asyncio.sleep(sleep_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Zhichi] Background refresh error: {e}", exc_info=True)
                await asyncio.sleep(60)  # 出错后等 60s 重试
