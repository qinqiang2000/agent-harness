"""PRD Backfiller — Phase B: match PRD files to Linear issues and backfill."""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from plugins.bundled.linear.linear_client import LinearClient

logger = logging.getLogger(__name__)

_RESULT_FILE = "linear_result.yaml"
# PRD 文件名模式：{特性ID}_*_用户故事设计规格说明书_v*.md
_PRD_PATTERN = re.compile(r"^([^_]+(?:_[^_]+)?)_.*_用户故事设计规格说明书_v.*\.md$")


class PRDBackfiller:
    """阶段 B：匹配 PRD 文件到 Linear 子 Issue，上传附件，更新描述，变更状态。"""

    def __init__(self, client: LinearClient, prd_root: str):
        self.client = client
        self.prd_root = Path(prd_root)

    async def backfill(
        self,
        prd_file_path: str,
        req_dir: str,
        review_state_id: str,
    ) -> None:
        """回填单个 PRD 文件到对应 Linear 子 Issue。

        Args:
            prd_file_path: PRD 文件绝对路径
            req_dir: 特性清单所在目录（含 linear_result.yaml）
            review_state_id: 回填完成后变更的目标状态 ID
        """
        prd_file = Path(prd_file_path)
        req_path = Path(req_dir)
        result_file = req_path / _RESULT_FILE

        # 从文件名提取 feature_id
        feature_id = _extract_feature_id(prd_file.name)
        if not feature_id:
            logger.warning(f"[Linear] Cannot extract feature_id from: {prd_file.name}")
            return

        # 读取 linear_result.yaml
        result_data = _load_result(result_file)
        if not result_data:
            logger.error(f"[Linear] linear_result.yaml not found: {result_file}")
            return

        # 查找对应 issue
        issue_entry = next(
            (i for i in result_data.get("issues", []) if i["feature_id"] == feature_id),
            None,
        )
        if not issue_entry:
            logger.error(
                f"[Linear] feature_id {feature_id} not found in linear_result.yaml"
            )
            return

        linear_id = issue_entry["linear_id"]
        identifier = issue_entry["identifier"]
        logger.info(f"[Linear] Backfilling PRD for {feature_id} → {identifier}")

        # 上传 PRD 附件（使用 GitHub raw URL 或本地路径作为 URL）
        prd_url = _file_url(prd_file)
        try:
            await self.client.create_attachment(
                issue_id=linear_id,
                url=prd_url,
                title=prd_file.stem,
                subtitle="用户故事设计规格说明书",
            )
        except Exception:
            logger.warning(
                f"[Linear] Failed to upload PRD attachment: {prd_file.name}",
                exc_info=True,
            )

        # 检查并上传单测初版
        unit_test_file = prd_file.parent / f"{feature_id}_unit_test_draft.md"
        if unit_test_file.exists():
            try:
                await self.client.create_attachment(
                    issue_id=linear_id,
                    url=_file_url(unit_test_file),
                    title=unit_test_file.stem,
                    subtitle="单测初版",
                )
            except Exception:
                logger.warning(
                    f"[Linear] Failed to upload unit test attachment", exc_info=True
                )

        # 提取 PRD 摘要（「一、特性概述」+「二、用户故事.主故事」）
        prd_content = prd_file.read_text(encoding="utf-8")
        summary = _extract_prd_summary(prd_content)

        # 更新子 Issue 描述（追加 PRD 摘要）
        if summary:
            try:
                issue_data = await self.client.get_issue(linear_id)
                existing_desc = issue_data.get("description") or ""
                new_desc = existing_desc + f"\n\n---\n\n## PRD 摘要\n\n{summary}"
                await self.client.update_issue(linear_id, description=new_desc)
            except Exception:
                logger.warning(
                    f"[Linear] Failed to update issue description", exc_info=True
                )

        # 变更状态
        if review_state_id:
            try:
                await self.client.update_issue(linear_id, state_id=review_state_id)
            except Exception:
                logger.warning(f"[Linear] Failed to update issue state", exc_info=True)

        # 更新 linear_result.yaml backfill_status
        from plugins.bundled.linear.issue_creator import _write_result, _iso_now

        for entry in result_data.get("issues", []):
            if entry["feature_id"] == feature_id:
                entry["backfill_status"] = "completed"
                entry["backfill_at"] = _iso_now()
                break
        _write_result(result_file, result_data)
        logger.info(f"[Linear] Backfill completed: {feature_id} → {identifier}")


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _extract_feature_id(filename: str) -> Optional[str]:
    """从 PRD 文件名提取 feature_id（前缀匹配）。

    命名规范：{特性ID}_*_用户故事设计规格说明书_v*.md
    """
    m = _PRD_PATTERN.match(filename)
    if m:
        return m.group(1)
    # 降级：取第一个 _ 之前的部分
    parts = filename.split("_")
    if parts:
        return parts[0]
    return None


def _load_result(result_file: Path):
    if not result_file.exists():
        return None
    try:
        with open(result_file, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _file_url(path: Path) -> str:
    """生成文件 URL（优先使用 Git 仓库 raw URL，降级为 file://）。"""
    import os

    repo_url = os.environ.get("LINEAR_GIT_REPO_URL", "")
    branch = os.environ.get("LINEAR_GIT_BRANCH", "master")
    local_path = os.environ.get("LINEAR_GIT_LOCAL_PATH", "data/linear/git-repo")

    if repo_url:
        # 将本地路径转换为 GitHub raw URL
        # https://github.com/org/repo → https://raw.githubusercontent.com/org/repo/branch/...
        rel = None
        try:
            rel = path.relative_to(Path(local_path))
        except ValueError:
            pass
        if rel:
            raw_base = repo_url.replace(
                "https://github.com/", "https://raw.githubusercontent.com/"
            )
            return f"{raw_base}/{branch}/{rel}"

    return f"file://{path.resolve()}"


def _extract_prd_summary(content: str) -> str:
    """提取 PRD 中「一、特性概述」和「二、用户故事」主故事部分作为摘要。"""
    lines = content.splitlines()
    sections = []

    # 提取「一、特性概述」章节
    overview = _extract_section(
        lines, ["一、特性概述", "1. 特性概述", "## 一、特性概述"]
    )
    if overview:
        sections.append(f"### 特性概述\n\n{overview}")

    # 提取「二、用户故事」中的主故事
    user_story = _extract_section(
        lines, ["二、用户故事", "2. 用户故事", "## 二、用户故事"]
    )
    if user_story:
        # 只取前 500 字符
        sections.append(f"### 用户故事（摘要）\n\n{user_story[:500]}")

    return "\n\n".join(sections)


def _extract_section(lines, headings) -> str:
    """提取指定标题下的内容，直到下一个同级标题。"""
    start = None
    heading_level = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        for h in headings:
            if stripped == h or stripped.startswith(h):
                start = i + 1
                # 判断标题级别
                m = re.match(r"^(#{1,6})\s", line)
                heading_level = len(m.group(1)) if m else None
                break
        if start is not None:
            break

    if start is None:
        return ""

    result_lines = []
    for line in lines[start:]:
        # 遇到同级或更高级标题则停止
        m = re.match(r"^(#{1,6})\s", line)
        if m and heading_level and len(m.group(1)) <= heading_level:
            break
        result_lines.append(line)

    return "\n".join(result_lines).strip()
