"""日报手动触发接口。"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report", tags=["report"])


class ReportResult(BaseModel):
    date: str
    total: int
    sent: bool
    dry_run: bool = False


@router.post("/daily", response_model=ReportResult)
async def trigger_daily_report(
    date: str = Query(
        default=None,
        description="日期 YYYYMMDD，默认昨天",
        pattern=r"^\d{8}$",
    ),
    dry_run: bool = Query(default=False, description="只生成不发送"),
):
    """手动触发 issue-diagnosis 日报生成与发送。"""
    from scripts.daily_report import generate_and_send

    date_str = date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    try:
        result = await generate_and_send(date_str, dry_run=dry_run)
        return ReportResult(**result)
    except Exception as e:
        logger.exception("Daily report failed")
        raise HTTPException(status_code=500, detail=str(e))
