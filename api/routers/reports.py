"""诊断报告 Web 展示路由."""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from api.services.report_store import get_report, list_reports, save_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/", response_class=JSONResponse)
async def get_reports_list(limit: int = 50):
    """获取报告列表."""
    return list_reports(limit=limit)


@router.post("/", response_class=JSONResponse)
async def create_report(request_data: dict):
    """Agent 调用此接口保存诊断报告."""
    required_fields = ["server_name", "ip", "alert_type", "alert_time", "summary", "full_report"]
    for field in required_fields:
        if field not in request_data:
            raise HTTPException(status_code=400, detail=f"缺少字段: {field}")

    report_id = save_report(
        server_name=request_data["server_name"],
        ip=request_data["ip"],
        alert_type=request_data["alert_type"],
        alert_time=request_data["alert_time"],
        summary=request_data["summary"],
        full_report=request_data["full_report"],
    )
    return {"report_id": report_id}


@router.get("/{report_id}", response_class=HTMLResponse)
async def view_report(report_id: str):
    """Web 页面展示完整诊断报告."""
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>诊断报告 - {report['server_name']}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .header {{ background: #fff; border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 20px; margin-bottom: 12px; }}
        .meta {{ display: flex; flex-wrap: wrap; gap: 16px; color: #666; font-size: 14px; }}
        .meta span {{ background: #f0f2f5; padding: 4px 10px; border-radius: 4px; }}
        .alert-badge {{ background: #fff2f0 !important; color: #cf1322; border: 1px solid #ffa39e; }}
        .content {{ background: #fff; border-radius: 8px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .content pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: "SF Mono", Monaco, "Cascadia Code", monospace; font-size: 14px; line-height: 1.7; background: #fafafa; padding: 16px; border-radius: 6px; border: 1px solid #eee; }}
        .summary {{ background: #fffbe6; border: 1px solid #ffe58f; border-radius: 6px; padding: 16px; margin-bottom: 20px; }}
        .summary h3 {{ font-size: 14px; color: #ad6800; margin-bottom: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 运维诊断报告</h1>
            <div class="meta">
                <span class="alert-badge">🚨 {report['alert_type']}</span>
                <span>🖥️ {report['server_name']} ({report['ip']})</span>
                <span>⏰ {report['alert_time']}</span>
                <span>📅 生成于 {report['created_at']}</span>
            </div>
        </div>
        <div class="content">
            <div class="summary">
                <h3>📋 摘要</h3>
                <p>{report['summary']}</p>
            </div>
            <h3 style="margin-bottom: 12px;">📊 完整诊断详情</h3>
            <pre>{report['full_report']}</pre>
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/{report_id}/json", response_class=JSONResponse)
async def get_report_json(report_id: str):
    """获取报告 JSON 数据."""
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report
