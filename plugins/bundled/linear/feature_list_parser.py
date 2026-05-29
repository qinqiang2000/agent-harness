"""Feature list (特性清单) Markdown parser."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import frontmatter


@dataclass
class FeatureItem:
    id: str
    title: str
    object: str
    action: str
    priority: str  # P0 / P1 / P2
    is_mvp: bool
    blocked_by: List[str]  # feature ID 列表，无依赖为空列表
    group: str


@dataclass
class FeatureList:
    req_id: str
    title: str
    owner: str
    priority: str
    project: Optional[str]
    labels: List[str]
    stage: str  # draft / confirmed
    requirement_report_path: str
    ontology_reports_dir: str
    features: List[FeatureItem] = field(default_factory=list)


def parse_feature_list(file_path: str) -> FeatureList:
    """解析特性清单 Markdown 文件，返回结构化 FeatureList。

    Args:
        file_path: 特性清单文件路径

    Returns:
        FeatureList 数据对象

    Raises:
        ValueError: frontmatter 缺少必填字段
        FileNotFoundError: 文件不存在
    """
    path = Path(file_path)
    post = frontmatter.load(str(path))
    meta = post.metadata

    # 必填字段校验
    for key in ("id", "title", "stage"):
        if key not in meta:
            raise ValueError(f"特性清单缺少必填 frontmatter 字段: {key}")

    artifacts = meta.get("artifacts", {})
    fl = FeatureList(
        req_id=str(meta["id"]),
        title=str(meta["title"]),
        owner=str(meta.get("owner", "")),
        priority=str(meta.get("priority", "P1")),
        project=meta.get("project"),
        labels=list(meta.get("labels", [])),
        stage=str(meta["stage"]),
        requirement_report_path=str(artifacts.get("requirement_report", "")),
        ontology_reports_dir=str(
            artifacts.get("ontology_reports_dir", "ontology-reports/")
        ),
    )

    fl.features = _parse_table(post.content)
    return fl


def _parse_table(content: str) -> List[FeatureItem]:
    """从 Markdown 正文中解析子需求表格。"""
    lines = content.splitlines()
    header_idx = None

    # 找到表头行（包含 id 和 title 列）
    for i, line in enumerate(lines):
        if re.match(r"\|\s*id\s*\|", line, re.IGNORECASE):
            header_idx = i
            break

    if header_idx is None:
        return []

    # 解析表头，确定列索引
    headers = _split_row(lines[header_idx])
    col = {h.strip().lower(): idx for idx, h in enumerate(headers)}

    features = []
    # 跳过分隔行（header_idx + 1），从数据行开始
    for line in lines[header_idx + 2 :]:
        line = line.strip()
        if not line.startswith("|"):
            break
        cells = _split_row(line)
        if len(cells) < len(headers):
            continue

        def get(name: str) -> str:
            idx = col.get(name)
            return cells[idx].strip() if idx is not None and idx < len(cells) else ""

        feature_id = get("id")
        if not feature_id or feature_id == "id":
            continue

        blocked_raw = get("blocked_by")
        if blocked_raw in ("—", "-", ""):
            blocked_by = []
        else:
            blocked_by = [
                b.strip() for b in re.split(r"[,，]", blocked_raw) if b.strip()
            ]

        is_mvp_raw = get("is_mvp").lower()
        is_mvp = is_mvp_raw in ("true", "yes", "1", "✅")

        features.append(
            FeatureItem(
                id=feature_id,
                title=get("title"),
                object=get("object"),
                action=get("action"),
                priority=get("priority") or "P1",
                is_mvp=is_mvp,
                blocked_by=blocked_by,
                group=get("group"),
            )
        )

    return features


def _split_row(line: str) -> List[str]:
    """将 Markdown 表格行按 | 分割，去掉首尾空列。"""
    parts = line.split("|")
    # 去掉首尾空字符串（行首/尾的 |）
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return parts
