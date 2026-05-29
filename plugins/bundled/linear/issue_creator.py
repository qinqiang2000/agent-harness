"""Issue creator — Phase A: create parent + child Issue skeletons."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from plugins.bundled.linear.feature_list_parser import FeatureList, FeatureItem
from plugins.bundled.linear.linear_client import LinearClient

logger = logging.getLogger(__name__)

_RESULT_FILE = "linear_result.yaml"


class IssueCreator:
    """阶段 A：解析特性清单，创建父子 Issue 骨架，回写 linear_result.yaml。"""

    def __init__(self, client: LinearClient, prd_root: str):
        self.client = client
        self.prd_root = Path(prd_root)

    async def create_skeleton(
        self,
        feature_list: FeatureList,
        req_dir: str,
        team_id: str,
        pending_state_id: str,
        assignee_id: Optional[str] = None,
        app_user_id: Optional[str] = None,
        source_issue_identifier: Optional[str] = None,
        parent_issue_id: Optional[str] = None,
        parent_issue_identifier: Optional[str] = None,
        parent_priority: int = 0,
    ) -> Dict[str, Any]:
        """创建子 Issue 骨架。

        如果传入 parent_issue_id，直接将子 Issue 挂在该 Issue 下，不新建骨架父 Issue。

        Returns:
            linear_result 数据字典
        """
        req_path = Path(req_dir)
        result_file = req_path / _RESULT_FILE

        # 幂等检查
        existing = _load_result(result_file)
        if existing and existing.get("requirement_id") == feature_list.req_id:
            logger.info(
                f"[Linear] Skeleton already exists for {feature_list.req_id}, skipping"
            )
            return existing

        # 优先级映射
        priority_map = {"P0": 1, "P1": 2, "P2": 3}

        # 使用传入的父 Issue，不新建骨架父 Issue
        if parent_issue_id and parent_issue_identifier:
            parent_issue = {
                "id": parent_issue_id,
                "identifier": parent_issue_identifier,
                "url": f"https://linear.app/issue/{parent_issue_identifier}",
            }
            logger.info(
                f"[Linear] Using existing parent issue: {parent_issue_identifier}"
            )
        else:
            # 兜底：新建骨架父 Issue（旧逻辑，保留兼容）
            req_report_content = _read_file(
                req_path / feature_list.requirement_report_path
            )
            feature_list_files = list(
                req_path.glob(f"{feature_list.req_id}_特性清单.md")
            )
            feature_list_content = (
                _read_file(feature_list_files[0]) if feature_list_files else ""
            )
            parent_description = ""
            if req_report_content:
                parent_description += f"## 需求分析报告\n\n{req_report_content}\n\n"
            if feature_list_content:
                parent_description += f"## 特性清单\n\n{feature_list_content}"

            label_ids = []
            for label_name in feature_list.labels:
                try:
                    lid = await self.client.get_or_create_label(team_id, label_name)
                    label_ids.append(lid)
                except Exception:
                    logger.warning(
                        f"[Linear] Failed to get/create label: {label_name}",
                        exc_info=True,
                    )

            project_id = None
            if feature_list.project:
                try:
                    project_id = await self.client.get_project_by_name(
                        team_id, feature_list.project
                    )
                except Exception:
                    logger.warning(
                        f"[Linear] Failed to find project: {feature_list.project}",
                        exc_info=True,
                    )

            parent_priority = priority_map.get(feature_list.priority, 0)
            logger.info(f"[Linear] Creating parent issue: {feature_list.title}")
            parent_issue = await self.client.create_issue(
                team_id=team_id,
                title=feature_list.title,
                description=parent_description,
                priority=parent_priority,
                label_ids=label_ids if label_ids else None,
                project_id=project_id,
            )
            logger.info(f"[Linear] Parent issue created: {parent_issue['identifier']}")

        # 提前写入 linear_result.yaml（只含父 Issue 骨架），确保子 Issue created 事件触发时能找到
        now_iso = _iso_now()
        result_data: Dict[str, Any] = {
            "version": "1.0",
            "created_at": now_iso,
            "requirement_id": feature_list.req_id,
            "source_issue_identifier": source_issue_identifier,
            "parent_issue": {
                "id": parent_issue["id"],
                "identifier": parent_issue["identifier"],
                "url": parent_issue.get("url", ""),
            },
            "issues": [],
        }
        _write_result(result_file, result_data)
        logger.info(
            f"[Linear] linear_result.yaml pre-written (skeleton): {result_file}"
        )

        # 并发创建子 Issue 骨架（过滤掉没有本体映射报告的特性，避免创建无法完成 PRD 的子 Issue）
        ontology_dir = req_path / feature_list.ontology_reports_dir
        valid_features = [
            feat
            for feat in feature_list.features
            if (ontology_dir / f"{feat.id}_本体映射报告.md").exists()
        ]
        skipped = len(feature_list.features) - len(valid_features)
        if skipped:
            logger.warning(
                f"[Linear] Skipping {skipped} features without ontology report: "
                + ", ".join(
                    feat.id
                    for feat in feature_list.features
                    if not (ontology_dir / f"{feat.id}_本体映射报告.md").exists()
                )
            )
        child_tasks = [
            self._create_child_issue(
                feature=feat,
                parent_id=parent_issue["id"],
                team_id=team_id,
                pending_state_id=pending_state_id,
                ontology_dir=ontology_dir,
                priority_map=priority_map,
                assignee_id=assignee_id,
                app_user_id=app_user_id,
                default_priority=parent_priority,
            )
            for feat in valid_features
        ]
        child_results = await asyncio.gather(*child_tasks, return_exceptions=True)

        # 构建 feature_id → issue 映射
        feature_issue_map: Dict[str, Dict] = {}
        issues_list = []
        for feat, result in zip(valid_features, child_results):
            if isinstance(result, Exception):
                logger.error(
                    f"[Linear] Failed to create child issue for {feat.id}: {result}"
                )
                continue
            feature_issue_map[feat.id] = result
            issues_list.append(
                {
                    "feature_id": feat.id,
                    "linear_id": result["id"],
                    "identifier": result["identifier"],
                    "url": result["url"],
                    "backfill_status": "pending",
                    "backfill_at": None,
                }
            )

        # 更新 linear_result.yaml，补充子 Issue 列表
        now_iso = _iso_now()
        result_data: Dict[str, Any] = {
            "version": "1.0",
            "created_at": now_iso,
            "requirement_id": feature_list.req_id,
            "source_issue_identifier": source_issue_identifier,  # 原始需求 Issue，供子 Issue 查找产物目录
            "parent_issue": {
                "id": parent_issue["id"],
                "identifier": parent_issue["identifier"],
                "url": parent_issue["url"],
            },
            "issues": issues_list,
        }
        _write_result(result_file, result_data)
        logger.info(f"[Linear] linear_result.yaml written: {result_file}")

        return result_data

    async def _create_child_issue(
        self,
        feature: FeatureItem,
        parent_id: str,
        team_id: str,
        pending_state_id: str,
        ontology_dir: Path,
        priority_map: Dict[str, int],
        assignee_id: Optional[str] = None,
        app_user_id: Optional[str] = None,
        default_priority: int = 0,
    ) -> Dict[str, Any]:
        # 读取本体映射报告
        report_file = ontology_dir / f"{feature.id}_本体映射报告.md"
        description = _read_file(report_file)
        if not description:
            logger.warning(f"[Linear] Ontology report not found: {report_file}")
            description = f"*本体映射报告未找到：{feature.id}_本体映射报告.md*"

        # 子 Issue 标签
        label_ids = []
        for label_name in [feature.group, feature.priority]:
            if label_name:
                try:
                    lid = await self.client.get_or_create_label(team_id, label_name)
                    label_ids.append(lid)
                except Exception:
                    pass

        # 优先级：特性自身有 priority 则用特性的，否则复用父 Issue 优先级
        child_priority = priority_map.get(feature.priority, default_priority)

        issue = await self.client.create_issue(
            team_id=team_id,
            title=f"{feature.id} {feature.title}",
            description=description,
            parent_id=parent_id,
            state_id=pending_state_id or None,
            priority=child_priority,
            label_ids=label_ids if label_ids else None,
            assignee_id=assignee_id,
            delegate_id=app_user_id,
        )
        logger.info(
            f"[Linear] Child issue created: {issue['identifier']} ({feature.id})"
        )
        return issue

    async def _set_blocking_relations(
        self,
        features: List[FeatureItem],
        feature_issue_map: Dict[str, Dict],
    ) -> None:
        for feat in features:
            if not feat.blocked_by:
                continue
            issue_id = feature_issue_map.get(feat.id, {}).get("id")
            if not issue_id:
                continue
            for blocker_feat_id in feat.blocked_by:
                blocker_issue = feature_issue_map.get(blocker_feat_id)
                if not blocker_issue:
                    logger.warning(
                        f"[Linear] Blocker feature not found: {blocker_feat_id} (for {feat.id})"
                    )
                    continue
                try:
                    # blocker_feat_id blocks feat.id → blocker issue blocks this issue
                    await self.client.create_issue_relation(
                        issue_id=blocker_issue["id"],
                        related_issue_id=issue_id,
                        relation_type="blocks",
                    )
                except Exception:
                    logger.warning(
                        f"[Linear] Failed to set blocking: {blocker_feat_id} → {feat.id}",
                        exc_info=True,
                    )


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _read_file(path) -> str:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _load_result(result_file: Path) -> Optional[Dict]:
    if not result_file.exists():
        return None
    try:
        with open(result_file, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _write_result(result_file: Path, data: Dict) -> None:
    tmp = result_file.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, allow_unicode=True, default_flow_style=False, sort_keys=False
        )
    tmp.replace(result_file)


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
