"""Diagnosis cases management API."""

import logging
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Literal
from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnosis", tags=["diagnosis"])

CASES_FILE = DATA_DIR / "issue-diagnosis" / "instincts" / "cases.md"

# 分类关键词映射
CATEGORY_KEYWORDS = [
    ("开票",              ["开票", "红冲", "票种", "errcode", "1639", "开具"]),
    ("收票",              ["收票", "查验", "合规", "台账", "PDF", "OFD", "版式"]),
    ("鉴权登录",          ["登录", "鉴权", "token", "clientId", "验证码", "roleCode", "身份"]),
    ("接口参数",          ["参数", "字段", "格式", "校验", "必填", "报文"]),
    ("进项发票采集",      ["进项", "采集", "下票", "抵扣", "勾选"]),
    ("性能超时",          ["超时", "timeout", "连接失败", "限流", "响应慢"]),
    ("faq-newtimeai-invoice", ["newtimeai", "新时代", "局端", "blueTicket"]),
]


def _detect_category(text: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS:
        if any(kw.lower() in text.lower() for kw in keywords):
            return category
    return "开票"


def _parse_cases(content: str) -> list[dict]:
    cases = []
    blocks = re.split(r"\n## Case #", content)
    for block in blocks[1:]:
        lines = block.strip().split("\n")
        case_id = lines[0].strip()
        fields = {}
        current_key = None
        current_val_lines = []

        for line in lines[1:]:
            m = re.match(r"^- ([\w_一-鿿]+):\s*(.*)$", line)
            if m:
                if current_key:
                    fields[current_key] = "\n".join(current_val_lines).strip()
                current_key = m.group(1)
                current_val_lines = [m.group(2)]
            elif current_key and (line.startswith("  ") or line.startswith("\t")):
                # 缩进行：多行内容（编号列表、子项等）
                current_val_lines.append(line.strip())
            elif current_key and re.match(r"^\s*$", line):
                # 空行：继续收集（段落间空行）
                current_val_lines.append("")
            else:
                if current_key:
                    fields[current_key] = "\n".join(current_val_lines).strip()
                    current_key = None
                    current_val_lines = []

        if current_key:
            fields[current_key] = "\n".join(current_val_lines).strip()

        trigger = fields.get("触发场景", "")
        correct_path = fields.get("正确路径", fields.get("初次诊断", ""))
        disposal = fields.get("处置建议", "")
        if disposal:
            answer_text = f"{correct_path}\n\n**处置建议：**\n{disposal}".strip() if correct_path else disposal
        else:
            answer_text = correct_path
        status = fields.get("状态", "pending_review")
        match_conf = float(fields.get("match_confidence", "0.7"))
        answer_conf = float(fields.get("answer_confidence", "0.7"))

        category = _detect_category(trigger + " " + answer_text)

        cases.append({
            "id": case_id,
            "trigger": trigger,
            "diagnosis": fields.get("初次诊断", ""),
            "correct_path": answer_text,
            "conditions": fields.get("适用条件", ""),
            "match_confidence": match_conf,
            "answer_confidence": answer_conf,
            "status": status,
            "created_at": fields.get("创建时间", ""),
            "suggested_category": category,
            "suggested_question": trigger[:100] if trigger else "",
            "suggested_answer": answer_text,
        })

    return sorted(cases, key=lambda x: x["answer_confidence"], reverse=True)


def _update_case_status(case_id: str, new_status: str):
    content = CASES_FILE.read_text(encoding="utf-8")
    pattern = rf"(## Case #{re.escape(case_id)}.*?- 状态: )\w+"
    updated = re.sub(pattern, rf"\g<1>{new_status}", content, flags=re.DOTALL)
    CASES_FILE.write_text(updated, encoding="utf-8")


@router.get("/cases", response_class=PlainTextResponse)
async def get_cases():
    """获取云端 issue-diagnosis 经验库（cases.md 原始内容）"""
    if not CASES_FILE.exists():
        raise HTTPException(status_code=404, detail="cases.md 不存在")
    return CASES_FILE.read_text(encoding="utf-8")


@router.get("/cases-list")
async def list_cases(status: str = ""):
    """获取结构化 case 列表"""
    if not CASES_FILE.exists():
        return {"cases": [], "total": 0}
    content = CASES_FILE.read_text(encoding="utf-8")
    cases = _parse_cases(content)
    if status:
        cases = [c for c in cases if c["status"] == status]
    return {"cases": cases, "total": len(cases)}


class PromoteRequest(BaseModel):
    category: str
    question: str
    answer: str


class RejectRequest(BaseModel):
    pass


@router.post("/cases/{case_id}/promote")
async def promote_case(case_id: str, body: PromoteRequest):
    """将 case promote 到 FAQ 待审核队列"""
    if not CASES_FILE.exists():
        raise HTTPException(status_code=404, detail="cases.md 不存在")

    from api.db import get_faq_pool
    from api.routers.faq import FAQ_CATEGORIES
    if body.category not in FAQ_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类：{body.category}")

    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO faq_items (category, type, question, answer, submitter, sort_order)
               VALUES ($1, 'qa', $2, $3, $4, 1000) RETURNING id""",
            body.category, body.question, body.answer, f"diagnosis-case-{case_id}"
        )

    _update_case_status(case_id, "merged")
    return {"ok": True, "faq_id": row["id"], "case_id": case_id}


@router.post("/cases/{case_id}/reject")
async def reject_case(case_id: str):
    """标记 case 为 rejected"""
    if not CASES_FILE.exists():
        raise HTTPException(status_code=404, detail="cases.md 不存在")
    _update_case_status(case_id, "rejected")
    return {"ok": True, "case_id": case_id}


@router.post("/cases/{case_id}/keep")
async def keep_case(case_id: str):
    """保留 case 为 pending_review"""
    return {"ok": True, "case_id": case_id, "status": "pending_review"}
