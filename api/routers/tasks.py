"""任务工单 Web 展示和 API 路由."""

import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from api.services.task_store import get_task, list_tasks, get_stats, list_creators, mark_alert_resolved, cancel_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/", response_class=HTMLResponse)
async def tasks_list_page(
    status: str = Query(None),
    creator: str = Query(None),
    alert: str = Query(None, description="告警状态筛选: resolved / unresolved"),
    limit: int = 50,
):
    """任务列表页面。"""
    stats = get_stats()

    alert_resolved_filter = None
    if alert == "resolved":
        alert_resolved_filter = True
    elif alert == "unresolved":
        alert_resolved_filter = False

    tasks = list_tasks(limit=limit, status=status, creator=creator, alert_resolved=alert_resolved_filter)
    creators = list_creators()

    # 构建任务行
    rows_html = ""
    for t in tasks:
        status_badge = {
            "pending": '<span style="color:#faad14">⏳ 等待</span>',
            "running": '<span style="color:#1890ff">🔄 执行中</span>',
            "completed": '<span style="color:#52c41a">✅ 完成</span>',
            "failed": '<span style="color:#ff4d4f">❌ 失败</span>',
            "timeout": '<span style="color:#fa8c16">⏰ 超时</span>',
            "cancelled": '<span style="color:#8c8c8c">⛔ 已取消</span>',
        }.get(t["status"], t["status"])

        # 告警状态徽章（只对 ops-diagnosis 任务有意义）
        is_unresolved_alert = False
        if t.get("task_type") == "ops-diagnosis":
            if t.get("alert_resolved"):
                alert_badge = '<span style="color:#52c41a;background:#f6ffed;border:1px solid #b7eb8f;padding:2px 8px;border-radius:3px;font-size:12px">🟢 已恢复</span>'
            elif t["status"] in ("completed", "failed"):
                alert_badge = '<span style="color:#ff4d4f;background:#fff2f0;border:1px solid #ffa39e;padding:2px 8px;border-radius:3px;font-size:12px">🔴 未恢复</span>'
                is_unresolved_alert = True
            else:
                alert_badge = '<span style="color:#999">-</span>'
        else:
            alert_badge = '<span style="color:#999">N/A</span>'

        # checkbox 只在未恢复任务上启用
        checkbox = (
            f'<input type="checkbox" class="task-cb" data-id="{t["id"]}" onclick="event.stopPropagation()">'
            if is_unresolved_alert else
            '<input type="checkbox" disabled style="opacity:0.3">'
        )

        rows_html += f"""
        <tr onclick="window.location='/api/tasks/{t['id']}'" style="cursor:pointer">
            <td onclick="event.stopPropagation()" style="text-align:center;width:40px">{checkbox}</td>
            <td><code>{t['id']}</code></td>
            <td>{status_badge}</td>
            <td>{alert_badge}</td>
            <td>{t['creator']}</td>
            <td>{t['task_type']}</td>
            <td title="{t.get('target','')}">{(t.get('target','') or '')[:40]}</td>
            <td>{t['created_at']}</td>
            <td>{t.get('completed_at') or '-'}</td>
        </tr>"""

    # 创建人快捷筛选标签
    creator_tags_html = ""
    for c in creators[:10]:  # 最多显示 10 个
        active_class = 'active' if creator == c["name"] else ''
        # URL 拼接保留当前 status
        params = []
        if status:
            params.append(f"status={status}")
        params.append(f"creator={c['name']}")
        url = "/api/tasks/?" + "&".join(params)
        creator_tags_html += f'<a href="{url}" class="creator-tag {active_class}">{c["name"]} ({c["count"]})</a>'

    # 当前筛选条件文字提示
    filter_hint = ""
    if creator or status or alert:
        parts = []
        if creator:
            parts.append(f"创建人=「{creator}」")
        if status:
            parts.append(f"状态=「{status}」")
        if alert:
            parts.append(f"告警=「{'已恢复' if alert == 'resolved' else '未恢复'}」")
        filter_hint = f'<span style="color:#666;font-size:13px;margin-left:8px">筛选条件: {", ".join(parts)}（共 {len(tasks)} 条）<a href="/api/tasks/" style="margin-left:8px;color:#1890ff">清空</a></span>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>任务工单列表</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
        .container {{ max-width: 1280px; margin: 0 auto; }}
        h1 {{ font-size: 22px; margin-bottom: 20px; }}
        .stats {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
        .stat-card {{ background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 120px; text-align: center; }}
        .stat-card .num {{ font-size: 28px; font-weight: 700; }}
        .stat-card .label {{ font-size: 12px; color: #999; margin-top: 4px; }}
        .filter-section {{ background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .filter-row {{ display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }}
        .filter-row:last-child {{ margin-bottom: 0; }}
        .filter-row .label {{ font-size: 13px; color: #666; min-width: 60px; }}
        .filter-row a {{ padding: 4px 12px; border-radius: 4px; text-decoration: none; font-size: 13px; background: #fafafa; color: #333; border: 1px solid #d9d9d9; }}
        .filter-row a.active {{ background: #1890ff; color: #fff; border-color: #1890ff; }}
        .filter-row a:hover {{ border-color: #1890ff; }}
        .creator-tag {{ font-size: 12px !important; }}
        .search-form {{ display: flex; gap: 8px; align-items: center; }}
        .search-form input {{ flex: 1; max-width: 300px; padding: 6px 12px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 13px; }}
        .search-form input:focus {{ outline: none; border-color: #1890ff; }}
        .search-form button {{ padding: 6px 16px; background: #1890ff; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }}
        .search-form button:hover {{ background: #096dd9; }}
        table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        th {{ background: #fafafa; text-align: left; padding: 12px 16px; font-size: 13px; color: #666; border-bottom: 1px solid #f0f0f0; white-space: nowrap; }}
        td {{ padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #f5f5f5; white-space: nowrap; }}
        td:nth-child(7) {{ white-space: normal; max-width: 220px; }}  /* 目标列允许换行 */
        tr:hover td {{ background: #f9fbff; }}
        code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
        .empty {{ text-align: center; padding: 40px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 任务工单 {filter_hint}</h1>

        <!-- 批量操作浮动栏 -->
        <div id="batch-bar" style="display:none;position:sticky;top:0;z-index:10;background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;padding:12px 16px;margin-bottom:16px;display:none;align-items:center;gap:12px">
            <span id="batch-count" style="font-size:14px;color:#ad6800">已选中 0 项</span>
            <button onclick="batchResolve()" style="padding:6px 14px;background:#52c41a;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px">🟢 批量标记已恢复</button>
            <button onclick="selectUnresolved()" style="padding:6px 14px;background:#fff;color:#333;border:1px solid #d9d9d9;border-radius:4px;cursor:pointer;font-size:13px">🔴 全选未恢复告警</button>
            <button onclick="clearSelection()" style="padding:6px 14px;background:#fff;color:#666;border:1px solid #d9d9d9;border-radius:4px;cursor:pointer;font-size:13px">取消选择</button>
        </div>

        <div class="stats">
            <div class="stat-card"><div class="num">{stats['total']}</div><div class="label">总计</div></div>
            <div class="stat-card"><div class="num" style="color:#52c41a">{stats['completed']}</div><div class="label">已完成</div></div>
            <div class="stat-card"><div class="num" style="color:#1890ff">{stats['running']}</div><div class="label">执行中</div></div>
            <div class="stat-card"><div class="num" style="color:#ff4d4f">{stats['failed']}</div><div class="label">失败</div></div>
            <div class="stat-card"><div class="num" style="color:#faad14">{stats['pending']}</div><div class="label">等待</div></div>
            <div class="stat-card" style="border-left:3px solid #ff4d4f"><div class="num" style="color:#ff4d4f">{stats['alert_unresolved']}</div><div class="label">🔴 未恢复告警</div></div>
            <div class="stat-card" style="border-left:3px solid #52c41a"><div class="num" style="color:#52c41a">{stats['alert_resolved']}</div><div class="label">🟢 已恢复告警</div></div>
        </div>

        <div class="filter-section">
            <div class="filter-row">
                <span class="label">状态:</span>
                <a href="/api/tasks/{('?creator=' + creator) if creator else ''}" class="{'active' if not status else ''}">全部</a>
                <a href="/api/tasks/?status=running{('&creator=' + creator) if creator else ''}" class="{'active' if status == 'running' else ''}">执行中</a>
                <a href="/api/tasks/?status=completed{('&creator=' + creator) if creator else ''}" class="{'active' if status == 'completed' else ''}">已完成</a>
                <a href="/api/tasks/?status=failed{('&creator=' + creator) if creator else ''}" class="{'active' if status == 'failed' else ''}">失败</a>
                <a href="/api/tasks/?status=pending{('&creator=' + creator) if creator else ''}" class="{'active' if status == 'pending' else ''}">等待</a>
            </div>

            <div class="filter-row">
                <span class="label">创建人:</span>
                <a href="/api/tasks/{('?status=' + status) if status else ''}" class="creator-tag {'active' if not creator else ''}">全部</a>
                {creator_tags_html}
            </div>

            <div class="filter-row">
                <span class="label">告警状态:</span>
                <a href="/api/tasks/" class="{'active' if not alert else ''}">全部</a>
                <a href="/api/tasks/?alert=unresolved" class="{'active' if alert == 'unresolved' else ''}">🔴 未恢复</a>
                <a href="/api/tasks/?alert=resolved" class="{'active' if alert == 'resolved' else ''}">🟢 已恢复</a>
            </div>

            <div class="filter-row">
                <span class="label">搜索:</span>
                <form class="search-form" method="GET" action="/api/tasks/">
                    {f'<input type="hidden" name="status" value="{status}">' if status else ''}
                    <input type="text" name="creator" placeholder="按创建人姓名筛选（支持模糊匹配）" value="{creator or ''}" />
                    <button type="submit">搜索</button>
                </form>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th style="text-align:center;width:40px"><input type="checkbox" id="select-all" onclick="toggleAll(this)"></th>
                    <th>任务ID</th>
                    <th>状态</th>
                    <th>告警状态</th>
                    <th>创建人</th>
                    <th>分类</th>
                    <th>目标</th>
                    <th>创建时间</th>
                    <th>完单时间</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="9" class="empty">暂无任务</td></tr>'}
            </tbody>
        </table>
    </div>
    <script>
        function getCheckboxes() {{
            return Array.from(document.querySelectorAll('.task-cb'));
        }}
        function getCheckedIds() {{
            return getCheckboxes().filter(cb => cb.checked).map(cb => cb.dataset.id);
        }}
        function updateBatchBar() {{
            const ids = getCheckedIds();
            const bar = document.getElementById('batch-bar');
            const count = document.getElementById('batch-count');
            if (ids.length > 0) {{
                bar.style.display = 'flex';
                count.textContent = `已选中 ${{ids.length}} 项`;
            }} else {{
                bar.style.display = 'none';
            }}
        }}
        function toggleAll(masterCb) {{
            getCheckboxes().forEach(cb => cb.checked = masterCb.checked);
            updateBatchBar();
        }}
        function selectUnresolved() {{
            getCheckboxes().forEach(cb => cb.checked = true);
            document.getElementById('select-all').checked = true;
            updateBatchBar();
        }}
        function clearSelection() {{
            getCheckboxes().forEach(cb => cb.checked = false);
            document.getElementById('select-all').checked = false;
            updateBatchBar();
        }}
        // 行内 checkbox 变化时更新顶部栏
        document.addEventListener('change', e => {{
            if (e.target.classList.contains('task-cb')) updateBatchBar();
        }});
        async function batchResolve() {{
            const ids = getCheckedIds();
            if (ids.length === 0) return alert('请先选择任务');
            if (!confirm(`确定要标记 ${{ids.length}} 条任务的告警为已恢复吗？`)) return;
            const reason = prompt("请输入您的姓名（用于记录），留空则记为 manual：") || "manual";
            try {{
                const resp = await fetch('/api/tasks/-/batch/resolve', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{task_ids: ids, resolved_by: reason}})
                }});
                const data = await resp.json();
                alert(`✅ 处理完成：成功 ${{data.resolved}} / ${{data.total}}，跳过 ${{data.already_resolved}}`);
                location.reload();
            }} catch (e) {{
                alert('请求失败：' + e.message);
            }}
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/list", response_class=JSONResponse)
async def get_tasks_api(limit: int = 50, status: str = Query(None), creator: str = Query(None)):
    """获取任务列表 JSON API。"""
    return list_tasks(limit=limit, status=status, creator=creator)


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
        "timeout": ("⏰ 超时", "#fa8c16", "#fff7e6", "#ffd591"),
        "cancelled": ("⛔ 已取消", "#8c8c8c", "#fafafa", "#d9d9d9"),
    }
    status_text, status_color, status_bg, status_border = status_map.get(
        task["status"], ("❓ 未知", "#999", "#f5f5f5", "#d9d9d9")
    )

    # 取消按钮（pending/running 状态可取消）
    cancel_btn = ""
    if task["status"] in ("pending", "running"):
        cancel_btn = '<button onclick="cancelTask()" style="margin-left:8px;padding:6px 14px;background:#ff4d4f;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px">⛔ 取消任务</button>'

    # 告警恢复徽章和按钮
    is_resolved = bool(task.get("alert_resolved"))
    resolved_at = task.get("alert_resolved_at") or "-"
    resolved_by = task.get("alert_resolved_by") or "-"

    if is_resolved:
        resolve_section = f'''
        <span class="status-badge" style="background:#f6ffed;color:#52c41a;border:1px solid #b7eb8f;margin-left:8px">
            🟢 告警已恢复 · {resolved_at} · {resolved_by}
        </span>'''
    else:
        # 只有任务执行完成才能标记恢复
        if task["status"] in ("completed", "failed"):
            resolve_section = f'''
            <button id="resolve-btn" onclick="resolveAlert()" style="margin-left:12px;padding:6px 14px;background:#52c41a;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px">
                🟢 标记告警已恢复
            </button>'''
        else:
            resolve_section = ""

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
            <span class="status-badge">{status_text}</span>{resolve_section}{cancel_btn}
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
    <script>
        async function resolveAlert() {{
            const reason = prompt("请输入您的姓名（用于记录），留空则记为 manual：") || "manual";
            try {{
                const resp = await fetch("/api/tasks/{task['id']}/resolve", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{resolved_by: reason}})
                }});
                const data = await resp.json();
                if (data.msg === "ok" || data.msg === "already_resolved") {{
                    alert("✅ 已标记告警恢复");
                    location.reload();
                }} else {{
                    alert("操作失败：" + JSON.stringify(data));
                }}
            }} catch (e) {{
                alert("请求失败：" + e.message);
            }}
        }}

        async function cancelTask() {{
            if (!confirm("确定要取消此任务吗？取消后无法恢复。")) return;
            const reason = prompt("请输入取消原因（可选）：") || "manual";
            try {{
                const resp = await fetch("/api/tasks/{task['id']}/cancel", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{reason: reason}})
                }});
                const data = await resp.json();
                if (data.msg === "ok") {{
                    alert("⛔ 任务已取消");
                    location.reload();
                }} else {{
                    alert("操作失败：" + (data.reason || JSON.stringify(data)));
                }}
            }} catch (e) {{
                alert("请求失败：" + e.message);
            }}
        }}
    </script>
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


@router.patch("/{task_id}", response_class=JSONResponse)
async def patch_task(task_id: str, body: dict):
    """更新任务单内容（Agent 调用，用于写入完整诊断报告）。

    支持字段: full_report, result_summary
    """
    from api.services.task_store import get_task as _get, update_status, add_stage, STATUS_COMPLETED

    task = _get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    full_report = body.get("full_report")
    result_summary = body.get("summary") or body.get("result_summary")

    if full_report or result_summary:
        update_status(
            task_id,
            task.get("status", STATUS_COMPLETED),
            result_summary=result_summary,
            full_report=full_report,
        )
        if full_report:
            add_stage(task_id, "📝 完整报告已保存")

    return {"msg": "ok", "task_id": task_id}


@router.post("/{task_id}/resolve", response_class=JSONResponse)
async def resolve_task(task_id: str, body: dict = None):
    """标记任务对应的告警已恢复。

    Body 可选:
    - resolved_by: 标记人（默认 "manual"）
    """
    resolved_by = "manual"
    if body and isinstance(body, dict):
        resolved_by = body.get("resolved_by") or "manual"

    success = mark_alert_resolved(task_id, resolved_by=resolved_by)
    if not success:
        # 任务不存在 或 已经标记过
        existing = get_task(task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"msg": "already_resolved", "task_id": task_id}

    return {"msg": "ok", "task_id": task_id}


@router.post("/-/batch/resolve", response_class=JSONResponse)
async def batch_resolve(body: dict):
    """批量标记任务告警已恢复。

    Body:
    - task_ids: ["OPS-...", "OPS-..."]
    - resolved_by: 标记人（可选，默认 "manual"）
    """
    task_ids = body.get("task_ids") or []
    resolved_by = body.get("resolved_by") or "manual"
    if not task_ids:
        raise HTTPException(status_code=400, detail="task_ids 不能为空")

    success_count = 0
    skipped = []
    not_found = []
    for tid in task_ids:
        if not get_task(tid):
            not_found.append(tid)
            continue
        if mark_alert_resolved(tid, resolved_by=resolved_by):
            success_count += 1
        else:
            skipped.append(tid)

    return {
        "msg": "ok",
        "total": len(task_ids),
        "resolved": success_count,
        "already_resolved": len(skipped),
        "not_found": len(not_found),
        "skipped_ids": skipped,
        "not_found_ids": not_found,
    }


@router.post("/{task_id}/cancel", response_class=JSONResponse)
async def cancel_task_endpoint(task_id: str, body: dict = None):
    """手动取消任务（仅适用于 pending/running 状态的任务）。"""
    reason = "manual"
    if body and isinstance(body, dict):
        reason = body.get("reason") or "manual"

    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task["status"] not in ("pending", "running"):
        return {"msg": "cannot_cancel", "reason": f"任务当前状态 {task['status']}，无需取消"}

    success = cancel_task(task_id, reason=reason)
    if not success:
        return {"msg": "failed"}
    return {"msg": "ok", "task_id": task_id}
