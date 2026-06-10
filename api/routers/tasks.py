"""任务工单 Web 展示和 API 路由."""

import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from api.services.task_store import get_task, list_tasks, get_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/", response_class=HTMLResponse)
async def tasks_list_page(status: str = Query(None), limit: int = 50):
    """任务列表页面。"""
    stats = get_stats()
    tasks = list_tasks(limit=limit, status=status)

    # 构建任务行
    rows_html = ""
    for t in tasks:
        status_badge = {
            "pending": '<span style="color:#faad14">⏳ 等待</span>',
            "running": '<span style="color:#1890ff">🔄 执行中</span>',
            "completed": '<span style="color:#52c41a">✅ 完成</span>',
            "failed": '<span style="color:#ff4d4f">❌ 失败</span>',
        }.get(t["status"], t["status"])

        rows_html += f"""
        <tr onclick="window.location='/api/tasks/{t['id']}'" style="cursor:pointer">
            <td><code>{t['id']}</code></td>
            <td>{status_badge}</td>
            <td>{t['creator']}</td>
            <td>{t['task_type']}</td>
            <td title="{t.get('target','')}">{(t.get('target','') or '')[:40]}</td>
            <td>{t['created_at']}</td>
            <td>{t.get('completed_at') or '-'}</td>
        </tr>"""

    # 筛选按钮
    filter_active = lambda s: 'active' if status == s else ''
    current_filter = status or '全部'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>任务工单列表</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        h1 {{ font-size: 22px; margin-bottom: 20px; }}
        .stats {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
        .stat-card {{ background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 120px; text-align: center; }}
        .stat-card .num {{ font-size: 28px; font-weight: 700; }}
        .stat-card .label {{ font-size: 12px; color: #999; margin-top: 4px; }}
        .filters {{ margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; }}
        .filters a {{ padding: 6px 14px; border-radius: 4px; text-decoration: none; font-size: 13px; background: #fff; color: #333; border: 1px solid #d9d9d9; }}
        .filters a.active {{ background: #1890ff; color: #fff; border-color: #1890ff; }}
        .filters a:hover {{ border-color: #1890ff; }}
        table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        th {{ background: #fafafa; text-align: left; padding: 12px 16px; font-size: 13px; color: #666; border-bottom: 1px solid #f0f0f0; }}
        td {{ padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #f5f5f5; }}
        tr:hover td {{ background: #f9fbff; }}
        code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
        .empty {{ text-align: center; padding: 40px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 任务工单</h1>

        <div class="stats">
            <div class="stat-card"><div class="num">{stats['total']}</div><div class="label">总计</div></div>
            <div class="stat-card"><div class="num" style="color:#52c41a">{stats['completed']}</div><div class="label">已完成</div></div>
            <div class="stat-card"><div class="num" style="color:#1890ff">{stats['running']}</div><div class="label">执行中</div></div>
            <div class="stat-card"><div class="num" style="color:#ff4d4f">{stats['failed']}</div><div class="label">失败</div></div>
            <div class="stat-card"><div class="num" style="color:#faad14">{stats['pending']}</div><div class="label">等待</div></div>
        </div>

        <div class="filters">
            <a href="/api/tasks/" class="{'active' if not status else ''}">全部</a>
            <a href="/api/tasks/?status=running" class="{'active' if status == 'running' else ''}">执行中</a>
            <a href="/api/tasks/?status=completed" class="{'active' if status == 'completed' else ''}">已完成</a>
            <a href="/api/tasks/?status=failed" class="{'active' if status == 'failed' else ''}">失败</a>
            <a href="/api/tasks/?status=pending" class="{'active' if status == 'pending' else ''}">等待</a>
        </div>

        <table>
            <thead>
                <tr>
                    <th>任务ID</th>
                    <th>状态</th>
                    <th>创建人</th>
                    <th>分类</th>
                    <th>目标</th>
                    <th>创建时间</th>
                    <th>完单时间</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="7" class="empty">暂无任务</td></tr>'}
            </tbody>
        </table>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/list", response_class=JSONResponse)
async def get_tasks_api(limit: int = 50, status: str = Query(None)):
    """获取任务列表 JSON API。"""
    return list_tasks(limit=limit, status=status)


@router.get("/stats", response_class=JSONResponse)
async def get_tasks_stats():
    """获取任务统计。"""
    return get_stats()


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
        .back {{ display: inline-block; margin-bottom: 16px; color: #1890ff; text-decoration: none; font-size: 14px; }}
        .back:hover {{ text-decoration: underline; }}
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
        .result {{ background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 6px; padding: 16px; white-space: pre-wrap; font-size: 14px; line-height: 1.7; }}
        .result.failed {{ background: #fff2f0; border-color: #ffa39e; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; font-size: 13px; line-height: 1.7; background: #fafafa; padding: 16px; border-radius: 6px; border: 1px solid #eee; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/api/tasks/" class="back">← 返回任务列表</a>
        <div class="header">
            <h1>📋 任务单 <code>{task['id']}</code></h1>
            <span class="status-badge">{status_text}</span>
            <div class="meta-grid">
                <div class="meta-item"><label>创建人</label><span>{task['creator']}</span></div>
                <div class="meta-item"><label>任务分类</label><span>{task['task_type']}</span></div>
                <div class="meta-item"><label>目标</label><span>{task.get('target') or '-'}</span></div>
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
            <pre>{task["full_report"]}</pre>
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
