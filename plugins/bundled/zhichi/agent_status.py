"""智齿客服实时数据查询 - 转人工前判断是否有坐席在线."""

import logging
from typing import Optional

import httpx

from plugins.bundled.zhichi.token_manager import ZhichiTokenManager

logger = logging.getLogger(__name__)


class ZhichiAgentStatusClient:
    """查询智齿客服实时数据（admin_size 等）.

    文档: https://developer.zhichi.com/pages/7dbd90/
    接口: POST /api/chat/5/user/get_once_data
    """

    def __init__(
        self,
        token_manager: ZhichiTokenManager,
        once_data_url: str = "https://www.soboten.com/api/chat/5/user/get_once_data",
        timeout: float = 5.0,
    ):
        self.token_manager = token_manager
        self.once_data_url = once_data_url
        self.timeout = timeout

    async def get_online_admin_size(self) -> Optional[int]:
        """返回在线客服数量；查询失败返回 None，调用方应视为不可转人工."""
        try:
            token = await self.token_manager.get_token()
        except Exception as e:
            logger.error(f"[Zhichi] Get token failed before agent status query: {e}")
            return None

        headers = {
            "language": "zh",
            "content-type": "application/json",
            "token": token,
        }
        logger.info(
            f"[Zhichi] get_once_data request: url={self.once_data_url}, "
            f"token={token[:6]}...{token[-4:]}"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.once_data_url, headers=headers)
                logger.info(
                    f"[Zhichi] get_once_data response: status={resp.status_code}, body={resp.text}"
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"[Zhichi] Query agent status failed: {e}")
            return None

        ret_code = data.get("ret_code", "")
        if ret_code != "000000":
            logger.error(f"[Zhichi] Agent status API error: ret_code={ret_code}, msg={data.get('ret_msg')}")
            return None

        item = data.get("item") or {}
        admin_size = item.get("admin_size")
        try:
            return int(admin_size) if admin_size is not None else 0
        except (TypeError, ValueError):
            logger.warning(f"[Zhichi] Unexpected admin_size value: {admin_size!r}")
            return None
