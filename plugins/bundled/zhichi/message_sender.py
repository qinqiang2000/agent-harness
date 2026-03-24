"""智齿回调消息发送器."""

import logging
from typing import Optional

import httpx

from plugins.bundled.zhichi.models import ThirdAlgorithmRespVo
from plugins.bundled.zhichi.token_manager import ZhichiTokenManager

logger = logging.getLogger(__name__)


class ZhichiMessageSender:
    """向智齿回调 API 发送答案."""

    def __init__(
        self,
        token_manager: ZhichiTokenManager,
        answer_url_stream: str = "https://www.sobot.com/api/robot/third_algorithm/stream/answer",
        answer_url_no_stream: str = "https://www.sobot.com/api/robot/third_algorithm/answer",
        mock_send: bool = False,
    ):
        self.token_manager = token_manager
        self.answer_url_stream = answer_url_stream
        self.answer_url_no_stream = answer_url_no_stream
        self.mock_send = mock_send

    async def send_answer(
        self,
        ai_agent_cid: str,
        llm_answer: str,
        req_stream: bool = False,
        answer_type: str = "QA_DIRECT",
        runtimeid: Optional[str] = None,
        message_end: bool = True,
    ) -> bool:
        """向智齿发送答案.

        Args:
            ai_agent_cid: 智齿会话 ID（原样回传）
            llm_answer: 答案文本
            req_stream: 是否为流式请求（决定回调 URL）
            answer_type: 答案类型
            third_transfer_flag: 是否转人工

        Returns:
            True 表示发送成功
        """
        if self.mock_send:
            logger.info(
                f"[Zhichi][MOCK] send_answer: cid={ai_agent_cid}, "
                f"req_stream={req_stream}, answer_type={answer_type}, "
                f"third_transfer_flag={third_transfer_flag}, "
                f"llm_answer={llm_answer}"
            )
            return True

        token = await self.token_manager.get_token()
        url = self.answer_url_stream if req_stream else self.answer_url_no_stream

        resp_vo = ThirdAlgorithmRespVo(
            llm_answer=llm_answer,
            answer_type=answer_type,
            runtimeid=runtimeid,
            message_end=message_end,
        )

        headers = {
            "Content-Type": "application/json",
            "token": token,
        }

        logger.info(f"[Zhichi] Sending response: url={url}, body={resp_vo.model_dump_json()}")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url,
                    content=resp_vo.model_dump_json(),
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"[Zhichi] Callback response: status={response.status_code}, body={response.text}")
                ret_code = data.get("ret_code", -1)
                if ret_code != 0:
                    logger.error(
                        f"[Zhichi] Answer API returned error: ret_code={ret_code}, "
                        f"msg={data.get('msg')}, cid={ai_agent_cid}"
                    )
                    return False
                logger.info(f"[Zhichi] Answer sent successfully: cid={ai_agent_cid}")
                return True

        except Exception as e:
            logger.error(
                f"[Zhichi] Failed to send answer: cid={ai_agent_cid}, error={e}",
                exc_info=True,
            )
            return False

    async def send_error_answer(
        self,
        ai_agent_cid: str,
        error_text: str = "抱歉，处理您的问题时出现错误，请稍后再试。",
        req_stream: bool = False,
        runtimeid: Optional[str] = None,
    ) -> bool:
        """发送错误兜底答案."""
        return await self.send_answer(
            ai_agent_cid=ai_agent_cid,
            llm_answer=error_text,
            req_stream=req_stream,
            runtimeid=runtimeid,
        )
