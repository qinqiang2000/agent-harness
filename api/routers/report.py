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


@router.get("/tokens")
async def get_token_usage(
    date: str = Query(
        default=None,
        description="日期 YYYYMMDD，默认昨天",
        pattern=r"^\d{8}$",
    ),
):
    """查询某一天的 token 用量聚合：总量、按 issue 排行、消耗结构归因。

    Args:
        date: 日期 YYYYMMDD，缺省取昨天

    Returns:
        summarize_day 的聚合结果字典
    """
    from api.services import token_usage_store

    date_str = date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    try:
        return token_usage_store.summarize_day(date_str)
    except Exception as e:
        logger.exception("Token usage query failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tokens/issue/{issue_key}")
async def get_issue_token_usage(issue_key: str):
    """查询单个 issue 跨多次对话的 token 用量明细与归因。

    Args:
        issue_key: Linear issue identifier，如 CNPRD-1276

    Returns:
        issue_detail 的结果字典，含每次对话明细与消耗结构
    """
    from api.services import token_usage_store

    try:
        return token_usage_store.issue_detail(issue_key)
    except Exception as e:
        logger.exception("Issue token usage query failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tokens/send")
async def trigger_token_report(
    date: str = Query(
        default=None,
        description="日期 YYYYMMDD，默认昨天",
        pattern=r"^\d{8}$",
    ),
    dry_run: bool = Query(default=False, description="只生成不发送"),
):
    """手动触发 token 成本日报的生成与私聊推送。

    Args:
        date: 日期 YYYYMMDD，缺省取昨天
        dry_run: 为 True 时只生成不发送

    Returns:
        含 date / requests / cost_usd / sent 的执行结果
    """
    from scripts.token_report import generate_and_send

    date_str = date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    try:
        return await generate_and_send(date_str, dry_run=dry_run)
    except Exception as e:
        logger.exception("Token report failed")
        raise HTTPException(status_code=500, detail=str(e))
