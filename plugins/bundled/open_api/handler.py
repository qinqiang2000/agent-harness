"""Open API 消息处理器."""

import asyncio
import json
import logging
import os
import re
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import httpx

from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.session_service import SessionService
from api.utils.perf_timer import PerfTimer, set_session_id

from plugins.bundled.open_api.models import AnswerReq

logger = logging.getLogger(__name__)

# 情绪触发关键词 - 直接触发，无需历史
_EMOTION_KEYWORDS = {
    "投诉", "举报", "太差了", "垃圾", "坑人", "骗人",
    "气死了", "烦死了", "破系统", "完全不能用",
    "找领导", "找媒体", "曝光", "起诉",
}

# 转人工关键词 - 需回溯历史
_TRANSFER_KEYWORDS = {"转人工", "人工", "转人工客服", "客服", "坐席", "售后", "真人", "活人", "人工服务"}

# 有效产品咨询特征词（回溯判断用）
_VALID_INQUIRY_PATTERN = re.compile(
    r"(报错|异常|失败|错误|问题|不能|无法|怎么|如何|配置|接口|功能|模块|开票|收票|影像|发票|标准版|星瀚|星空|国际版|API|接入|对接)"
)


def _has_emotion(text: str) -> bool:
    return any(kw in text for kw in _EMOTION_KEYWORDS)


def _has_transfer_keyword(text: str) -> bool:
    return any(kw in text for kw in _TRANSFER_KEYWORDS)


def _has_valid_inquiry(history: List[Tuple[str, str]]) -> bool:
    for question, _ in list(history)[-5:]:
        if _VALID_INQUIRY_PATTERN.search(question):
            return True
    return False


class OpenApiHandler:
    def __init__(self, agent_service: AgentService, session_service: SessionService, config: dict):
        self.agent_service = agent_service
        self.session_service = session_service
        self.default_skill = config.get("default_skill", "customer-service")
        self.session_mapper = PluginSessionMapper(
            timeout_seconds=config.get("session_timeout", 3600),
            channel_id="open_api",
        )
        self._history: Dict[str, Deque[Tuple[str, str]]] = {}

    def _get_history(self, cid: str) -> Deque[Tuple[str, str]]:
        if cid not in self._history:
            self._history[cid] = deque(maxlen=5)
        return self._history[cid]

    def _cleanup_history(self) -> None:
        """清理已过期会话的历史记录."""
        active_cids = set(self.session_mapper.session_map.keys())
        expired = [c for c in self._history if c not in active_cids]
        for c in expired:
            del self._history[c]

    async def _send_escalation(self, cid: str, session_id: Optional[str], reason: str, current_question: Optional[str] = None) -> None:
        """异步向 ticket-hub 发送 escalation 回调，不阻塞主流程。"""
        ticket_hub_url = os.getenv("TICKET_HUB_WEBHOOK_URL", "").strip()
        ticket_hub_token = os.getenv("TICKET_HUB_WEBHOOK_TOKEN", "").strip()
        if not ticket_hub_url:
            return

        rows = []
        if session_id:
            try:
                from api.db import get_faq_pool
                pool = await get_faq_pool()
                rows = await pool.fetch(
                    """
                    SELECT question, answer, skills_used, cited_urls, created_at
                    FROM cs_interactions
                    WHERE session_id = $1
                    ORDER BY created_at ASC
                    """,
                    session_id,
                )
            except Exception as e:
                logger.warning(f"[OpenAPI] escalation: failed to query interactions: {e}")

        conversation: List[dict] = []
        all_cited_urls: List[str] = []
        all_skills: List[str] = []
        original_question: Optional[str] = None
        last_answer: Optional[str] = None

        for row in rows:
            ts = row["created_at"].isoformat() if row["created_at"] else ""
            if row["question"]:
                if original_question is None:
                    original_question = row["question"]
                conversation.append({"role": "user", "text": row["question"], "ts": ts})
            if row["answer"]:
                last_answer = row["answer"]
                conversation.append({"role": "assistant", "text": row["answer"], "ts": ts})
            for url in (row["cited_urls"] or []):
                if url not in all_cited_urls:
                    all_cited_urls.append(url)
            for skill in (row["skills_used"] or []):
                if skill not in all_skills:
                    all_skills.append(skill)

        # 代码层转人工时当前轮问题未经 agent，DB 里没有这条记录，手动补入
        if current_question:
            if original_question is None:
                original_question = current_question
            conversation.append({"role": "user", "text": current_question, "ts": ""})

        payload = {
            "session_id": session_id or cid,
            "original_question": original_question or "",
            "ai_answer": last_answer or "",
            "dissatisfaction": reason,
            "conversation": conversation,
            "cited_knowledge": [{"url": u} for u in all_cited_urls],
            "skills_used": all_skills,
        }
        url = ticket_hub_url
        if ticket_hub_token:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}access_token={ticket_hub_token}"
        headers = {"Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers)
                logger.info(f"[OpenAPI] escalation sent: session={session_id} status={resp.status_code}")
        except Exception as e:
            logger.warning(f"[OpenAPI] escalation POST failed: {e}")

    def _check_transfer(self, cid: str, question: str) -> bool:
        # 情绪触发：直接 TRANSFER，无需历史
        if _has_emotion(question):
            logger.info(f"[OpenAPI] Transfer by emotion: cid={cid[:8]}")
            return True
        # 关键词触发：回溯5轮，有有效咨询才 TRANSFER
        if _has_transfer_keyword(question):
            history = list(self._get_history(cid))
            if _has_valid_inquiry(history):
                logger.info(f"[OpenAPI] Transfer by keyword+history: cid={cid[:8]}")
                return True
            logger.info(f"[OpenAPI] Transfer keyword hit but no valid inquiry: cid={cid[:8]}")
        return False

    async def get_answer(self, req: AnswerReq) -> tuple[str, bool]:
        """同步问答，返回 (answer, is_transfer)."""
        cid = req.ai_agent_cid
        self.session_mapper.cleanup_expired()
        self._cleanup_history()

        agent_session_id = self.session_mapper.get_or_create(cid)

        perf = PerfTimer(request_id=cid[:8] if cid else None)
        perf.attach()
        if agent_session_id:
            set_session_id(agent_session_id)

        # 代码层转人工判断，优先于 Agent
        if self._check_transfer(cid, req.question):
            self._get_history(cid).append((req.question, "[TRANSFER]"))
            asyncio.create_task(self._send_escalation(cid, agent_session_id, req.question, current_question=req.question))
            return "正在为您转接人工客服，请稍候。", True

        prompt = req.question
        if agent_session_id:
            pending = self.session_mapper.get_and_clear_pending_questions(cid)
            if pending:
                prompt = f"用户回答: {req.question}\n请根据用户的回答继续处理。"

        request = QueryRequest(
            prompt=prompt,
            skill=req.skill or self.default_skill,
            tenant_id="open_api",
            language="中文",
            session_id=agent_session_id,
            images=req.images,
        )

        answer = "抱歉，处理您的问题时出现错误，请稍后再试。"

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                new_session_id = data["session_id"]
                set_session_id(new_session_id)
                self.session_mapper.update_activity(cid, new_session_id)

            elif event_type == "transfer_human":
                # Agent 的转人工信号忽略，由代码层统一控制
                data = json.loads(event["data"])
                answer = data.get("reason", "正在为您转接人工客服，请稍候。")
                current_session_id = self.session_mapper.get_or_create(cid) or agent_session_id
                asyncio.create_task(self._send_escalation(cid, current_session_id, answer))
                break

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])
                self.session_mapper.set_pending_questions(cid, questions)
                if questions:
                    q = questions[0]
                    lines = [q.get("question", "请选择"), ""]
                    for i, opt in enumerate(q.get("options", []), 1):
                        lines.append(f"{i}. {opt.get('label', '')}")
                    answer = "\n".join(lines)
                if agent_session_id:
                    await self.session_service.interrupt(agent_session_id)
                    from api.services.sdk_pool import get_cache
                    cache = get_cache()
                    if cache:
                        await cache.release(agent_session_id, healthy=False)
                break

            elif event_type == "result":
                data = json.loads(event.get("data", "{}"))
                answer = data.get("result", answer)

            elif event_type == "error":
                data = json.loads(event.get("data", "{}"))
                answer = f"抱歉，处理时出现错误：{data.get('message', '未知错误')}"
                break

        self._get_history(cid).append((req.question, answer))
        return answer, False

    def remove_session(self, cid: str) -> None:
        self.session_mapper.remove(cid)
        self._history.pop(cid, None)

    def get_stats(self) -> dict:
        return self.session_mapper.get_stats()
