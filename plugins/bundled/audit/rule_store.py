"""JSON-file-based rules CRUD per tenant."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from api.constants import TENANTS_DIR
from plugins.bundled.audit.models import AuditRule

logger = logging.getLogger(__name__)

# Default rules (example for financial audit demo)
DEFAULT_RULES: List[dict] = [
    {"id": "rule-1", "text": "报价单甲方为：环胜电子商务（上海）有限公司", "enabled": True, "category": "identity", "color": "#3B82F6"},
    {"id": "rule-2", "text": "报价单需要乙方加盖合同专用章（红章）", "enabled": True, "category": "seal", "color": "#EF4444"},
    {"id": "rule-3", "text": "报价单\"费用总计\"金额需要与收货单\"折扣后收货含税总金额\"一致", "enabled": True, "category": "amount", "color": "#10B981"},
    {"id": "rule-4", "text": "报价单项目抬头与收货单备注摘要关键字要一致", "enabled": True, "category": "keyword", "color": "#F59E0B"},
    {"id": "rule-5", "text": "报价单项目周期要与订单服务完成日期的区间相匹配", "enabled": True, "category": "date", "color": "#8B5CF6"},
    {"id": "rule-6", "text": "报价单的项目抬头和推文物料抬头项目关键字要一致", "enabled": True, "category": "keyword", "color": "#F97316"},
    {"id": "rule-7", "text": "推文物料抓取到与报价单中\"品项名称\"相匹配的关键字字段", "enabled": True, "category": "keyword", "color": "#EC4899"},
]

# Category display names
CATEGORY_NAMES = {
    "identity": "身份校验",
    "seal": "印章校验",
    "amount": "金额核对",
    "keyword": "关键字匹配",
    "date": "日期核对",
}


def _rules_file(tenant_id: str) -> Path:
    d = TENANTS_DIR / tenant_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "audit-rules.json"


def get_rules(tenant_id: str) -> List[AuditRule]:
    """Get all rules for a tenant. Initializes with defaults if none exist."""
    path = _rules_file(tenant_id)
    if not path.exists():
        save_rules(tenant_id, [AuditRule(**r) for r in DEFAULT_RULES])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [AuditRule(**r) for r in data.get("rules", [])]
    except Exception as e:
        logger.error(f"[Audit] Error reading rules for {tenant_id}: {e}")
        return [AuditRule(**r) for r in DEFAULT_RULES]


def save_rules(tenant_id: str, rules: List[AuditRule]) -> None:
    """Save rules for a tenant."""
    path = _rules_file(tenant_id)
    data = {
        "rules": [r.model_dump() for r in rules],
        "updated_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[Audit] Saved {len(rules)} rules for tenant {tenant_id}")


def get_enabled_rules(tenant_id: str) -> List[AuditRule]:
    """Get only enabled rules."""
    return [r for r in get_rules(tenant_id) if r.enabled]


def get_rules_by_category(tenant_id: str) -> dict:
    """Get rules grouped by category. Returns {category: [AuditRule, ...]}."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in get_rules(tenant_id):
        cat = r.category or "other"
        groups[cat].append(r)
    return dict(groups)
