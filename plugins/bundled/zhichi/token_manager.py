"""智齿 OAuth Token 管理器 - 每次实时获取."""

import hashlib
import logging
import time

import httpx

logger = logging.getLogger(__name__)


class ZhichiTokenManager:
    """管理智齿 API Token（MD5 签名获取，每次调用实时请求）."""

    def __init__(
        self,
        app_id: str,
        app_key: str,
        token_api_url: str = "https://www.soboten.com/api/get_token",
        refresh_buffer_seconds: int = 300,
    ):
        self.app_id = app_id
        self.app_key = app_key
        self.token_api_url = token_api_url
        logger.info(
            f"[Zhichi] TokenManager init: app_id={app_id!r}, app_key={app_key!r}, "
            f"token_api_url={token_api_url}"
        )

    def start_background_refresh(self) -> None:
        pass

    def stop_background_refresh(self) -> None:
        pass

    def _build_signature(self, timestamp: int) -> str:
        """MD5(appid + create_time + app_key)，时间戳为秒级."""
        raw = f"{self.app_id}{timestamp}{self.app_key}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def get_token(self) -> str:
        """每次调用实时获取 Token."""
        timestamp = int(time.time())
        sign = self._build_signature(timestamp)

        params = {
            "appid": self.app_id,
            "sign": sign,
            "create_time": timestamp,
        }
        logger.info(
            f"[Zhichi] get_token request: appid={self.app_id!r}, "
            f"app_key={self.app_key!r}, create_time={timestamp}, sign={sign}"
        )

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.token_api_url, params=params)
                logger.info(
                    f"[Zhichi] get_token response: status={resp.status_code}, "
                    f"url={resp.request.url}, body={resp.text}"
                )
                resp.raise_for_status()
                data = resp.json()

            ret_code = data.get("ret_code", "")
            if ret_code != "000000":
                raise ValueError(f"Token API error: ret_code={ret_code}, msg={data.get('ret_msg')}")

            item = data.get("item", {})
            token = item.get("token")
            if not token:
                raise ValueError(f"No token field in response: {data}")

            logger.info(f"[Zhichi] Token fetched: {token[:6]}...{token[-4:]}")
            return token

        except Exception as e:
            logger.error(f"[Zhichi] Failed to fetch token: {e}", exc_info=True)
            raise
