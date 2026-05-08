"""Alertmanager webhook receiver.

Receives Prometheus Alertmanager alerts and triggers ops-diagnosis skill
for automated root cause analysis.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from ..dependencies import get_agent_service, get_session_service
from ..models.requests import QueryRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["alert"])

# alertname 关键词 → 告警类型映射
ALERT_TYPE_MAP = [
    ("CPU", "CPU使用率高"),
    ("cpu", "CPU使用率高"),
    ("内存", "内存使用率高"),
    ("Memory", "内存使用率高"),
    ("memory", "内存使用率高"),
    ("硬盘", "磁盘空间不足"),
    ("Disk", "磁盘空间不足"),
    ("disk", "磁盘空间不足"),
    ("IO", "磁盘IO利用率高"),
    ("io", "磁盘IO利用率高"),
]


def _match_alert_type(alertname: str) -> Optional[str]:
    """Match alertname to alert type."""
    for keyword, alert_type in ALERT_TYPE_MAP:
        if keyword in alertname:
            return alert_type
    return None


def _build_diagnosis_prompt(alert_type: str, ip: str, alert_time: str, alertname: str) -> str:
    """Build the prompt for ops-diagnosis skill."""
    return (
        f"告警类型: {alert_type}\n"
        f"目标IP: {ip}\n"
        f"告警时间: {alert_time}\n"
        f"告警名称: {alertname}\n"
        f"\n"
        f"请按照 ops-diagnosis 流程执行诊断：\n"
        f"1. 根据目标IP查找服务器SSH信息\n"
        f"2. SSH远程采集诊断数据\n"
        f"3. 识别高资源消耗的服务\n"
        f"4. 关联GitLab近期部署变更\n"
        f"5. 分析根因并给出结论\n"
        f"6. 推送结果到云之家"
    )


async def _run_diagnosis(prompt: str):
    """Run diagnosis in background."""
    agent_service = get_agent_service()

    request = QueryRequest(
        tenant_id="alertmanager",
        prompt=prompt,
        skill="ops-diagnosis",
        language="中文",
    )

    try:
        async for message in agent_service.process_query(request):
            event = message.get("event")
            if event == "error":
                logger.error(f"Diagnosis error: {message.get('data')}")
            elif event == "result":
                logger.info(f"Diagnosis completed: {message.get('data')}")
    except Exception as e:
        logger.error(f"Diagnosis failed: {e}", exc_info=True)


@router.post("/alert-webhook")
async def alert_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Alertmanager webhook receiver.

    Receives firing alerts from Prometheus Alertmanager,
    extracts alert info, and triggers ops-diagnosis skill in background.

    Expected payload format:
    {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CPU使用率过高",
                    "instance": "172.31.36.31:9100"
                },
                "startsAt": "2026-05-06T14:30:00.000Z"
            }
        ]
    }
    """
    data = await request.json()

    if not data or "alerts" not in data:
        return JSONResponse(
            status_code=400,
            content={"msg": "invalid payload, missing 'alerts' field"},
        )

    alerts = data.get("alerts", [])
    triggered = []

    for alert in alerts:
        if alert.get("status") != "firing":
            continue

        labels = alert.get("labels", {})
        alertname = labels.get("alertname", "")
        instance = labels.get("instance", "")
        ip = instance.split(":")[0] if instance else ""

        if not ip:
            logger.warning(f"Alert '{alertname}' missing instance IP, skipping")
            continue

        alert_type = _match_alert_type(alertname)
        if not alert_type:
            logger.info(f"Alert '{alertname}' no matching type, skipping")
            continue

        # Parse alert time
        starts_at = alert.get("startsAt", "")
        if starts_at:
            try:
                dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
                alert_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        prompt = _build_diagnosis_prompt(alert_type, ip, alert_time, alertname)
        logger.info(f"Triggering ops-diagnosis: type={alert_type}, ip={ip}, time={alert_time}")

        background_tasks.add_task(_run_diagnosis, prompt)
        triggered.append({"ip": ip, "alert_type": alert_type, "alertname": alertname})

    return JSONResponse(
        status_code=200,
        content={
            "msg": "ok",
            "triggered": len(triggered),
            "details": triggered,
        },
    )
