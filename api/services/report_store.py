"""诊断报告存储服务 - 保存完整报告，生成短链接供 IM 推送."""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

REPORTS_DIR = DATA_DIR / "diagnosis-reports"


def _ensure_dir():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def save_report(
    server_name: str,
    ip: str,
    alert_type: str,
    alert_time: str,
    summary: str,
    full_report: str,
) -> str:
    """保存诊断报告，返回 report_id."""
    _ensure_dir()
    report_id = uuid.uuid4().hex[:12]
    report = {
        "id": report_id,
        "server_name": server_name,
        "ip": ip,
        "alert_type": alert_type,
        "alert_time": alert_time,
        "summary": summary,
        "full_report": full_report,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    report_file = REPORTS_DIR / f"{report_id}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[ReportStore] Saved report {report_id} for {server_name}({ip})")
    return report_id


def get_report(report_id: str) -> Optional[dict]:
    """根据 ID 获取报告."""
    report_file = REPORTS_DIR / f"{report_id}.json"
    if not report_file.exists():
        return None
    return json.loads(report_file.read_text(encoding="utf-8"))


def list_reports(limit: int = 50) -> list:
    """列出最近的报告（按时间倒序）."""
    _ensure_dir()
    files = sorted(REPORTS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    reports = []
    for f in files[:limit]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "id": data["id"],
                "server_name": data.get("server_name", ""),
                "ip": data.get("ip", ""),
                "alert_type": data.get("alert_type", ""),
                "alert_time": data.get("alert_time", ""),
                "summary": data.get("summary", "")[:100],
                "created_at": data.get("created_at", ""),
            })
        except Exception:
            continue
    return reports
