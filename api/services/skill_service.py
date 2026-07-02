"""Skill 版本管理服务。

职责：
- 从磁盘 import 现有 skill 作为初始 published 版本
- 创建/更新 draft
- 发布 draft（写回磁盘）
- 回滚到历史版本（创建新 draft）

对外版本号格式：{skill_name}:V{N}，如 customer-service:V1，大小写不敏感。
数据库 id 仅在服务内部流转，不暴露到接口层。
"""

import logging
import os
import re
from pathlib import Path

from api.constants import AGENT_CWD

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^(.+):v(\d+)$", re.IGNORECASE)


def get_managed_skills() -> list[str]:
    """从环境变量读取受管理的 skill 列表。"""
    raw = os.getenv("MANAGED_SKILLS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def format_version_key(skill_name: str, version_num: int) -> str:
    """将 skill_name + 整数版本号格式化为对外版本号，如 customer-service:V1。"""
    return f"{skill_name}:V{version_num}"


def parse_version_key(version_key: str) -> tuple[str, int]:
    """
    解析对外版本号，返回 (skill_name, version_num)。
    支持大小写，如 customer-service:V1、customer-service:v1。
    解析失败抛 ValueError。
    """
    m = _VERSION_RE.match(version_key.strip())
    if not m:
        raise ValueError(f"版本号格式错误，应为 {{skill_name}}:V{{N}}，实际：{version_key!r}")
    return m.group(1), int(m.group(2))


def _skill_dir(skill_name: str) -> Path:
    return AGENT_CWD / ".claude" / "skills" / skill_name


def _collect_disk_files(skill_name: str) -> list[dict]:
    """扫描 skill 目录，返回所有文件快照（跳过隐藏文件）。"""
    skill_dir = _skill_dir(skill_name)
    if not skill_dir.exists():
        return []
    files = []
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            content = f.read_bytes().decode("latin-1")
        files.append({
            "filename": f.name,
            "filepath": str(f.relative_to(skill_dir)),
            "content": content,
        })
    return files


def _write_to_disk(skill_name: str, files: list[dict]) -> None:
    """将版本文件写回磁盘，保持目录结构。"""
    skill_dir = _skill_dir(skill_name)
    for f in files:
        target = skill_dir / f["filepath"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
    logger.info("[SkillService] written %d files to disk: %s", len(files), skill_name)


def _fmt(skill_name: str, version_num: int) -> str:
    return format_version_key(skill_name, version_num)


async def import_skills_from_disk() -> None:
    """启动时：对每个受管理 skill，若无 published 版本则从磁盘导入为 V1。"""
    from api.db import skill_get_published, skill_next_version, skill_create_version

    for skill_name in get_managed_skills():
        try:
            existing = await skill_get_published(skill_name)
            if existing:
                logger.info("[SkillService] %s already has published %s, skip import",
                            skill_name, _fmt(skill_name, existing["version"]))
                continue
            files = _collect_disk_files(skill_name)
            if not files:
                logger.warning("[SkillService] %s: no files on disk, skip import", skill_name)
                continue
            version = await skill_next_version(skill_name)
            await skill_create_version(
                skill_name=skill_name, version=version, status="published",
                files=files, operator="system", reason="初始化导入（磁盘快照）",
            )
            logger.info("[SkillService] imported %s as %s (%d files)",
                        skill_name, _fmt(skill_name, version), len(files))
        except Exception:
            logger.exception("[SkillService] import failed for %s", skill_name)


async def create_draft(
    skill_name: str,
    files: list[dict] | None,
    operator: str | None,
    reason: str | None,
) -> dict:
    """
    创建新 draft。files 为空时继承当前 published 全量文件。
    返回 {version: "customer-service:V2"}。
    """
    from api.db import (
        skill_get_published, skill_get_files,
        skill_next_version, skill_create_version,
    )

    base_files: list[dict] = []
    published = await skill_get_published(skill_name)
    if published:
        base_files = await skill_get_files(published["id"])

    if files:
        base_map = {f["filepath"]: f for f in base_files}
        for f in files:
            base_map[f["filepath"]] = f
        merged = list(base_map.values())
    else:
        merged = base_files

    version_num = await skill_next_version(skill_name)
    await skill_create_version(
        skill_name=skill_name, version=version_num, status="draft",
        files=merged, operator=operator, reason=reason,
    )
    return {"version": _fmt(skill_name, version_num)}


async def update_draft(
    skill_name: str,
    version_num: int,
    files: list[dict],
    operator: str | None,
    reason: str | None,
) -> None:
    """更新已有 draft 的文件内容（upsert）。"""
    from api.db import skill_get_version_by_key, skill_update_draft

    ver = await skill_get_version_by_key(skill_name, version_num)
    if not ver:
        raise ValueError(f"版本 {_fmt(skill_name, version_num)} 不存在")
    if ver["status"] != "draft":
        raise ValueError(f"版本 {_fmt(skill_name, version_num)} 状态为 {ver['status']}，只有 draft 可以编辑")
    await skill_update_draft(ver["id"], files, operator, reason)


async def publish_draft(skill_name: str, version_num: int) -> None:
    """发布 draft：更新数据库状态，将文件写回磁盘，异步通知云之家。"""
    from api.db import skill_get_version_by_key, skill_get_files, skill_publish

    ver = await skill_get_version_by_key(skill_name, version_num)
    if not ver:
        raise ValueError(f"版本 {_fmt(skill_name, version_num)} 不存在")
    if ver["status"] != "draft":
        raise ValueError(f"版本 {_fmt(skill_name, version_num)} 状态为 {ver['status']}，只有 draft 可以发布")

    files = await skill_get_files(ver["id"])
    await skill_publish(skill_name, ver["id"])
    _write_to_disk(skill_name, files)
    logger.info("[SkillService] published %s (%d files)", _fmt(skill_name, version_num), len(files))

    # 异步通知云之家，不阻塞发布流程
    import asyncio
    asyncio.create_task(_notify_publish(skill_name, version_num, ver.get("operator"), ver.get("reason")))


async def _notify_publish(skill_name: str, version_num: int, operator: str | None, reason: str | None) -> None:
    """发布后异步通知云之家群机器人。不配置 SKILL_PUBLISH_WEBHOOK_URL 则静默跳过。"""
    webhook_url = os.getenv("SKILL_PUBLISH_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    from datetime import datetime
    skill_dir = str(_skill_dir(skill_name)).replace(str(Path.home()), "~")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    version_key = _fmt(skill_name, version_num)

    text = (
        f"[Skill 发布通知]\n"
        f"skill: {skill_name}\n"
        f"版本: {version_key}\n"
        f"操作人: {operator or '未知'}\n"
        f"原因: {reason or '—'}\n"
        f"时间: {now}\n\n"
        f"请及时 git pull 并提交最新 skill 文件：\n"
        f"agent_cwd/.claude/skills/{skill_name}/"
    )

    try:
        import httpx
        payload = {"content": text}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            logger.info("[SkillService] publish notify sent: status=%d version=%s", resp.status_code, version_key)
    except Exception as e:
        logger.warning("[SkillService] publish notify failed: %s", e)


async def rollback_to_version(
    skill_name: str,
    target_version_num: int,
    operator: str | None,
    reason: str | None,
) -> dict:
    """将历史版本内容复制为新 draft，返回 {version: "customer-service:V3"}。"""
    from api.db import skill_get_version_by_key, skill_get_files

    ver = await skill_get_version_by_key(skill_name, target_version_num)
    if not ver:
        raise ValueError(f"版本 {_fmt(skill_name, target_version_num)} 不存在")

    files = await skill_get_files(ver["id"])
    return await create_draft(
        skill_name=skill_name,
        files=files,
        operator=operator,
        reason=reason or f"回滚自 {_fmt(skill_name, target_version_num)}",
    )
