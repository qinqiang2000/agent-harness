"""Diagnosis cases management API."""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnosis", tags=["diagnosis"])

CASES_FILE = DATA_DIR / "issue-diagnosis" / "instincts" / "cases.md"


@router.get("/cases", response_class=PlainTextResponse)
async def get_cases():
    """获取云端 issue-diagnosis 经验库（cases.md 原始内容）"""
    if not CASES_FILE.exists():
        raise HTTPException(status_code=404, detail="cases.md 不存在")
    return CASES_FILE.read_text(encoding="utf-8")
