"""任务工单 Web 展示和 API 路由."""

import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from api.services.task_store import get_task, list_tasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/", response_class=JSONResponse)
async def get_tasks_list(limit: int = 50, status: str = Query(None)):
    """获取任务列表。"""
    return list_tasks(limit=limit, status=status)


@router.get("/{task_id}", response_class=HTMLResponse)
async def view_task(task_id: str):
    """Web 页面展示任务工单详情。"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 状态样式
    status_map = {
        "pending": ("⏳ 等待执行", "#faad14", "#fffbe6", "#ffe58f"),
        "running": ("🔄 执行中", "#1890ff", "#e6f7ff", "#91d5ff"),
        "completed": ("✅ 已完单", "#52c41a", "#f6ffed", "#b7eb8f"),
        "failed": ("❌ 失败", "#ff4d4f", "#fff2f0", "#ffa39e"),
    }
    status_text, status_color, status_bg, status_border = status_map.get(
        task["status"], ("❓ 未知", "#999", "#f5f5f5", "#d9d9d9")
    )

    # 构建阶段列表 HTML
    stages_html = ""
    for stage in task.get("stages", []):
        stages_html += f'<div class="stage-item"><span class="stage-time">{stage["time"]}</span> {stage["msg"]}</div>\n'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>任务单 {task['id']}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .header {{ background: #fff; border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 20px; margin-bottom: 16px; }}
        .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 14px; font-weight: 500; background: {status_bg}; color: {status_color}; border: 1px solid {status_border}; }}
        .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 16px; }}
        .meta-item {{ background: #f9fafb; padding: 12px; border-radius: 6px; }}
        .meta-item label {{ font-size: 12px; color: #999; display: block; margin-bottom: 4px; }}
        .meta-item span {{ font-size: 14px; font-weight: 500; }}
        .section {{ background: #fff; border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .section h3 {{ font-size: 16px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #f0f0f0; }}
        .stage-item {{ padding: 10px 0; border-bottom: 1px solid #f5f5f5; font-size: 14px; line-height: 1.6; }}
        .stage-item:last-child {{ border-bottom: none; }}
        .stage-time {{ color: #999; font-size: 12px; margin-right: 8px; font-family: monospace; }}
        .result {{ background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 6px; padding: 16px; margin-top: 12px; white-space: pre-wrap; font-size: 14px; line-height: 1.7; }}
        .result.failed {{ background: #fff2f0; border-color: #ffa39e; }}
        a {{ color: #1890ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 任务单 <code>{task['id']}</code></h1>
            <span class="status-badge">{status_text}</span>
            <div class="meta-grid">
                <div class="meta-item"><label>创建人</label><span>{task['creator']}</span></div>
                <div class="meta-item"><label>任务分类</label><span>{task['task_type']}</span></div>
                <div class="meta-item"><label>目标</label><span>{task['target']}</span></div>
                <div class="meta-item"><label>创建时间</label><span>{task['created_at']}</span></div>
                <div class="meta-item"><label>最后更新</label><span>{task['updated_at']}</span></div>
                <div class="meta-item"><label>完单时间</label><span>{task.get('completed_at') or '-'}</span></div>
            </div>
        </div>

        <div class="section">
            <h3>📍 执行阶段</h3>
            {stages_html if stages_html else '<p style="color:#999">暂无执行记录</p>'}
        </div>

        {"" if not task.get('result_summary') else f'''
        <div class="section">
            <h3>📊 执行结果</h3>
            <div class="result {"failed" if task["status"] == "failed" else ""}">{task["result_summary"]}</div>
        </div>
        '''}

        {"" if not task.get('full_report') else f'''
        <div class="section">
            <h3>📋 完整诊断详情</h3>
            <pre style="white-space:pre-wrap;word-wrap:break-word;font-size:13px;line-height:1.7;background:#fafafa;padding:16px;border-radius:6px;border:1px solid #eee;">{task["full_report"]}</pre>
        </div>
        '''}
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/{task_id}/json", response_class=JSONResponse)
async def get_task_json(task_id: str):
    """获取任务 JSON 数据。"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
