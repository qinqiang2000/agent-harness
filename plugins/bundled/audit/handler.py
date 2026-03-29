"""Audit handler - orchestrates file management, rules, and query pipeline."""

import json
import logging
from typing import AsyncGenerator, List, Optional

from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

from plugins.bundled.audit import file_manager, rule_store
from plugins.bundled.audit.models import AuditQueryRequest, AuditRule

logger = logging.getLogger(__name__)


class AuditHandler:
    """Orchestrates audit queries."""

    def __init__(
        self,
        agent_service: AgentService,
        session_service: SessionService,
        config: dict,
    ):
        self.agent_service = agent_service
        self.session_service = session_service
        self.default_skill = config.get("default_skill", "financial-audit")

        self.session_mapper = PluginSessionMapper(
            timeout_seconds=config.get("session_timeout", 3600),
            channel_id="audit",
        )

    def build_audit_prompt(
        self,
        files: list,
        rules: List[AuditRule],
        user_prompt: Optional[str] = None,
    ) -> str:
        """Build the prompt for the audit agent."""
        parts = ["你是一名财务审核专家。请对以下文件按给定规则执行审核。"]

        # File list
        parts.append("\n## 上传的文件")
        for f in files:
            parts.append(f"- {f['name']}: {f['path']}")

        # Rules (include rule.id so Agent returns matching IDs in JSON)
        parts.append("\n## 审核规则")
        for i, rule in enumerate(rules, 1):
            parts.append(f"{i}. [{rule.id}] {rule.text}")

        # User message
        if user_prompt:
            parts.append(f"\n## 用户补充说明\n{user_prompt}")

        parts.append("\n请按 financial-audit skill 的流程执行。")
        return "\n".join(parts)

    async def process_audit(
        self,
        request: AuditQueryRequest,
    ) -> AsyncGenerator[dict, None]:
        """Run an audit and yield SSE events."""
        tenant_id = request.tenant_id

        # Get files
        all_files = file_manager.list_files(tenant_id)
        if request.files:
            all_files = [f for f in all_files if f.name in request.files]

        if not all_files:
            from api.utils import format_sse_message
            yield format_sse_message("error", {"message": "没有找到可审核的文件，请先上传文件。"})
            return

        # Get rules
        if request.rule_ids:
            all_rules = rule_store.get_rules(tenant_id)
            rules = [r for r in all_rules if r.id in request.rule_ids and r.enabled]
        else:
            rules = rule_store.get_enabled_rules(tenant_id)

        if not rules:
            from api.utils import format_sse_message
            yield format_sse_message("error", {"message": "没有启用的审核规则，请先配置规则。"})
            return

        # Build prompt
        file_list = [{"name": f.name, "path": f.path} for f in all_files]

        if request.session_id:
            # Resume session - just send user prompt
            prompt = request.prompt or "请继续"
        else:
            prompt = self.build_audit_prompt(file_list, rules, request.prompt)

        # Create QueryRequest for AgentService (use Sonnet for better PDF/vision)
        query_request = QueryRequest(
            tenant_id=tenant_id,
            prompt=prompt,
            skill=self.default_skill,
            language="中文",
            session_id=request.session_id,
            metadata={"model": "claude-sonnet-4-6", "max_turns": 30},
        )

        logger.info(f"[Audit] Starting audit: tenant={tenant_id}, files={len(all_files)}, rules={len(rules)}")

        # Stream from AgentService
        async for event in self.agent_service.process_query(query_request):
            yield event
