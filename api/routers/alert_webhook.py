"""Alertmanager webhook receiver.

Receives Prometheus Alertmanager alerts and triggers ops-diagnosis skill
for automated root cause analysis.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from ..dependencies import get_agent_service, get_session_service
from ..models.requests import QueryRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["alert"])

# ============================================================
# 告警去重配置（防止 10 分钟内 100 条相同告警把 agent 打爆）
# ============================================================
# 同一 (alert_type, ip) 在冷却期内不再触发新诊断
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "1800"))  # 默认 30 分钟
# 全局并发上限，超出直接丢弃
ALERT_MAX_CONCURRENT = int(os.getenv("ALERT_MAX_CONCURRENT", "5"))

# In-flight：正在执行的诊断 key 集合
_inflight: set[tuple[str, str]] = set()
# Cooldown：上次诊断完成时间，key=(alert_type, ip), value=完成时间
_cooldown: dict[tuple[str, str], datetime] = {}
# 跳过计数：在 in-flight 或 cooldown 期间被跳过的告警，key=(alert_type, ip)
# value: {"count": N, "first_skipped_at": dt, "last_skipped_at": dt, "alertname": str}
_skip_count: dict[tuple[str, str], dict] = {}
# 全局并发信号量
_concurrency_sem: Optional[asyncio.Semaphore] = None
# 状态字典并发保护
_state_lock = asyncio.Lock()


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy init 信号量（必须在事件循环中创建）。"""
    global _concurrency_sem
    if _concurrency_sem is None:
        _concurrency_sem = asyncio.Semaphore(ALERT_MAX_CONCURRENT)
    return _concurrency_sem


async def _should_skip(key: tuple[str, str], alertname: str = "") -> Optional[str]:
    """检查是否应跳过该告警。返回跳过原因，None 表示继续处理。

    被跳过时累加 _skip_count，用于冷却期结束时发送汇总。
    """
    async with _state_lock:
        now = datetime.now(timezone.utc)

        # 1. 正在诊断中
        if key in _inflight:
            _record_skip(key, alertname, now)
            return f"in-flight (already diagnosing {key[0]} on {key[1]})"

        # 2. 冷却期内
        last_done = _cooldown.get(key)
        if last_done:
            elapsed = (now - last_done).total_seconds()
            if elapsed < ALERT_COOLDOWN_SECONDS:
                _record_skip(key, alertname, now)
                remaining = int(ALERT_COOLDOWN_SECONDS - elapsed)
                return f"in cooldown ({remaining}s remaining)"

        # 3. 标记为 in-flight（同时清空之前的计数，新一轮开始）
        _inflight.add(key)
        _skip_count.pop(key, None)
        return None


def _record_skip(key: tuple[str, str], alertname: str, now: datetime):
    """记录一次跳过（必须在 _state_lock 持有时调用）。"""
    if key in _skip_count:
        _skip_count[key]["count"] += 1
        _skip_count[key]["last_skipped_at"] = now
    else:
        _skip_count[key] = {
            "count": 1,
            "first_skipped_at": now,
            "last_skipped_at": now,
            "alertname": alertname,
        }


async def _release_inflight(key: tuple[str, str]):
    """诊断结束，从 in-flight 移到 cooldown。"""
    async with _state_lock:
        _inflight.discard(key)
        _cooldown[key] = datetime.now(timezone.utc)
        # 顺便清理过期的 cooldown 条目（避免无限增长）
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ALERT_COOLDOWN_SECONDS)
        expired = [k for k, t in _cooldown.items() if t < cutoff]
        for k in expired:
            _cooldown.pop(k, None)

# alertname 关键词 → 告警类型映射（顺序匹配，优先级从高到低）
ALERT_TYPE_MAP = [
    ("IO利用率", "磁盘IO利用率高"),
    ("IO", "磁盘IO利用率高"),
    ("io", "磁盘IO利用率高"),
    ("CPU", "CPU使用率高"),
    ("cpu", "CPU使用率高"),
    ("内存", "内存使用率高"),
    ("Memory", "内存使用率高"),
    ("memory", "内存使用率高"),
    ("硬盘", "磁盘空间不足"),
    ("Disk", "磁盘空间不足"),
    ("disk", "磁盘空间不足"),
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


async def _run_diagnosis(prompt: str, key: tuple[str, str]):
    """Run diagnosis in background with concurrency limit and inflight release."""
    sem = _get_semaphore()

    # 全局并发限流：拿不到信号量就等
    async with sem:
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
                    logger.error(f"Diagnosis error [{key}]: {message.get('data')}")
                elif event == "result":
                    logger.info(f"Diagnosis completed [{key}]: {message.get('data')}")
        except Exception as e:
            logger.error(f"Diagnosis failed [{key}]: {e}", exc_info=True)
        finally:
            # 不管成功失败，都释放 inflight 并进入冷却期
            await _release_inflight(key)
            # 启动延迟汇总任务：冷却期结束时若有跳过的告警则发汇总
            asyncio.create_task(_send_skip_summary_after_cooldown(key))


async def _send_skip_summary_after_cooldown(key: tuple[str, str]):
    """冷却期结束时检查跳过计数，若有则推送汇总到云之家。

    时机：诊断完成后等待 ALERT_COOLDOWN_SECONDS 秒（与冷却期同步），
    然后读取 _skip_count 一次性发汇总。
    """
    try:
        await asyncio.sleep(ALERT_COOLDOWN_SECONDS)
    except asyncio.CancelledError:
        return

    async with _state_lock:
        info = _skip_count.pop(key, None)

    if not info or info["count"] <= 0:
        return

    alert_type, target = key
    first = info["first_skipped_at"].astimezone(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
    last = info["last_skipped_at"].astimezone(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
    minutes = ALERT_COOLDOWN_SECONDS // 60

    summary = (
        f"📊 【告警频次汇总】\n"
        f"{alert_type} - {target}\n"
        f"过去 {minutes} 分钟内重复触发 {info['count']} 次\n"
        f"首次: {first}  末次: {last}\n"
        f"（已自动诊断 1 次，详情见之前推送）"
    )
    logger.info(f"Sending skip summary [{key}]: count={info['count']}")
    await _push_text_to_yunzhijia(summary)


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
    skipped = []

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

        # Parse alert time (convert to Asia/Shanghai UTC+8)
        starts_at = alert.get("startsAt", "")
        if starts_at:
            try:
                dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
                dt_shanghai = dt.astimezone(timezone(timedelta(hours=8)))
                alert_time = dt_shanghai.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                alert_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        else:
            alert_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

        # 去重检查：同一 (alert_type, ip) 在 in-flight 或冷却期内则跳过
        key = (alert_type, ip)
        skip_reason = await _should_skip(key, alertname)
        if skip_reason:
            logger.info(f"Skip duplicate alert [{key}]: {skip_reason}")
            skipped.append({
                "ip": ip,
                "alert_type": alert_type,
                "alertname": alertname,
                "reason": skip_reason,
            })
            continue

        prompt = _build_diagnosis_prompt(alert_type, ip, alert_time, alertname)
        logger.info(f"Triggering ops-diagnosis: type={alert_type}, ip={ip}, time={alert_time}")

        background_tasks.add_task(_run_diagnosis, prompt, key)
        triggered.append({"ip": ip, "alert_type": alert_type, "alertname": alertname})

    return JSONResponse(
        status_code=200,
        content={
            "msg": "ok",
            "triggered": len(triggered),
            "skipped": len(skipped),
            "details": triggered,
            "skipped_details": skipped,
        },
    )


# ============================================================
# 文本告警接入与恢复告警识别
# ============================================================

import re
import aiohttp

# 恢复告警关键词（命中任一即视为恢复，不诊断，原文转发到云之家）
RECOVERY_KEYWORDS = [
    "✅",
    "恢复",
    "已解决",
    "已恢复",
    "resolved",
    "Resolved",
    "RESOLVED",
    "RECOVERY",
    "recovery",
]


def _is_recovery_alert(text: str) -> bool:
    """判断文本告警是否为恢复消息。"""
    if not text:
        return False
    return any(kw in text for kw in RECOVERY_KEYWORDS)


async def _push_text_to_yunzhijia(content: str) -> bool:
    """直接 POST 原文到云之家 webhook，不调用 LLM。

    返回 True 表示推送成功。
    """
    webhook_url = os.getenv("YZJ_ALERT_WEBHOOK")
    if not webhook_url:
        logger.error("YZJ_ALERT_WEBHOOK env not configured, cannot forward alert")
        return False

    payload = {"msgType": 0, "content": content}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                if resp.status == 200 and '"errorCode":0' in body:
                    logger.info(f"Forwarded recovery alert to yunzhijia: {content[:80]}")
                    return True
                logger.error(f"Yunzhijia push failed: status={resp.status}, body={body[:200]}")
                return False
    except Exception as e:
        logger.error(f"Yunzhijia push exception: {e}", exc_info=True)
        return False


@router.post("/alert-text")
async def alert_text(request: Request, background_tasks: BackgroundTasks):
    """文本告警接入端点。

    接收纯文本告警（运维群里的脚本告警、腾讯云推送等非结构化文本），
    自动识别恢复消息并直接转发到云之家，不触发 LLM 诊断。

    请求方式：
    - Content-Type: text/plain  → body 即为告警原文
    - Content-Type: application/json  → body 形如 {"text": "..."}

    返回：
        {"msg": "ok", "action": "forwarded|diagnose|ignored", "reason": "..."}
    """
    # 读取告警原文（兼容 text/plain 和 JSON）
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
            text = data.get("text") or data.get("content") or data.get("message") or ""
        except Exception:
            text = ""
    else:
        body = await request.body()
        text = body.decode("utf-8", errors="replace").strip()

    if not text:
        return JSONResponse(
            status_code=400,
            content={"msg": "empty alert text"},
        )

    # 恢复告警：原文转发到云之家，不调用 LLM
    if _is_recovery_alert(text):
        logger.info(f"Recovery alert detected, forwarding text only: {text[:120]}")
        background_tasks.add_task(_push_text_to_yunzhijia, text)
        return JSONResponse(
            status_code=200,
            content={
                "msg": "ok",
                "action": "forwarded",
                "reason": "recovery alert (no diagnosis)",
            },
        )

    # 非恢复告警：原文直接转发到云之家（透传，不调 LLM）
    logger.info(f"Non-recovery text alert, forwarding as-is: {text[:120]}")
    background_tasks.add_task(_push_text_to_yunzhijia, text)
    return JSONResponse(
        status_code=200,
        content={
            "msg": "ok",
            "action": "forwarded",
            "reason": "non-recovery text alert forwarded to yunzhijia (no diagnosis)",
        },
    )
