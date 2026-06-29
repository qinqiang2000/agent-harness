"""Replay 核心逻辑，供 open_api plugin 调用。"""

import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Optional

from api.constants import AGENT_CWD
from api.models.requests import QueryRequest
from api.services.skill_service import get_managed_skills
from api.utils import build_initial_prompt

logger = logging.getLogger(__name__)

_md_url = re.compile(r'\[([^\]]*)\]\((https?://[^)]+)\)')
_bare_url = re.compile(r'(?<!\()https?://[^\s\)\"\'<>，。！？、）]+')


def _build_tmp_cwd(skill_name: str, files: list[dict], trace_id: str) -> Path:
    """构造临时 cwd：draft skill 文件 + data 软链接。"""
    tmp_dir = Path(f"/tmp/skill-replay-{trace_id}")
    skill_dir = tmp_dir / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        target = skill_dir / f["filepath"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
    data_link = tmp_dir / "data"
    if not data_link.exists():
        data_link.symlink_to((AGENT_CWD / "data").resolve())
    logger.info("[Replay] tmp cwd created: %s (%d files)", tmp_dir, len(files))
    return tmp_dir


def _cleanup_tmp_cwd(tmp_dir: Path) -> None:
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("[Replay] tmp cwd cleaned: %s", tmp_dir)
    except Exception as e:
        logger.warning("[Replay] cleanup failed: %s", e)


async def run_replay(body, agent_service) -> dict:
    """
    执行 replay，返回 {answer, cited_knowledge, skills_used, trace_id}。
    body 为 ReplayReq 实例。
    抛出 ValueError 表示业务错误。
    """
    if not body.session_id and not body.question:
        raise ValueError("session_id 和 question 至少传一个")

    question = body.question
    skill = body.skill
    trace_id = uuid.uuid4().hex[:12]

    # 从历史 session 补全 question / skill
    if body.session_id and (not question or not skill):
        try:
            from api.db import get_faq_pool
            pool = await get_faq_pool()
            row = await pool.fetchrow(
                "SELECT question, skill FROM cs_interactions "
                "WHERE session_id=$1 ORDER BY created_at ASC LIMIT 1",
                body.session_id,
            )
            if row:
                if not question:
                    question = row["question"]
                if not skill:
                    skill = row["skill"]
        except Exception as e:
            logger.warning("[Replay] failed to query session history: %s", e)

    if not question:
        raise ValueError("无法确定问题内容，请直接传入 question")

    managed = get_managed_skills()
    if not skill or skill not in managed:
        raise ValueError(f"skill 必须在受管理列表内：{managed}，当前值：{skill!r}")

    # 处理 draft cwd
    tmp_dir: Optional[Path] = None
    if body.skill_draft_version is not None:
        from api.db import skill_get_version_by_key, skill_get_files
        from api.services.skill_service import parse_version_key
        try:
            draft_skill_name, version_num = parse_version_key(body.skill_draft_version)
        except ValueError as e:
            raise ValueError(str(e))
        if draft_skill_name != skill:
            raise ValueError(f"skill_draft_version 中的 skill 名 '{draft_skill_name}' 与 skill '{skill}' 不一致")
        ver = await skill_get_version_by_key(draft_skill_name, version_num)
        if not ver:
            raise ValueError(f"版本 {body.skill_draft_version} 不存在")
        if ver["status"] == "published":
            raise ValueError("请传入 draft 版本，不能传已发布版本")
        files = await skill_get_files(ver["id"])
        tmp_dir = _build_tmp_cwd(skill, files, trace_id)

    # 知识库同步
    kb_sync_script = os.getenv("KB_SYNC_SCRIPT", "").strip()
    if kb_sync_script:
        script_path = Path(kb_sync_script)
        if not script_path.exists():
            logger.warning("[Replay] KB_SYNC_SCRIPT not found: %s, skip", kb_sync_script)
        else:
            logger.info("[Replay] running KB sync: %s", kb_sync_script)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "sh", str(script_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                if proc.returncode != 0:
                    logger.warning("[Replay] KB sync exited %d: %s", proc.returncode,
                                   stderr.decode("utf-8", errors="replace")[:500])
                else:
                    logger.info("[Replay] KB sync done: %s", stdout.decode("utf-8", errors="replace")[:200])
            except asyncio.TimeoutError:
                logger.warning("[Replay] KB sync timed out (300s), proceeding anyway")
            except Exception as e:
                logger.warning("[Replay] KB sync failed: %s, proceeding anyway", e)

    # 构造 prompt 和 options
    prompt = await build_initial_prompt(
        tenant_id="replay",
        user_prompt=question,
        skill=skill,
        language="中文",
        metadata=body.context,
    )
    request = QueryRequest(
        prompt=prompt,
        skill=skill,
        tenant_id="replay",
        language="中文",
        session_id=None,
    )
    options = agent_service.build_default_options()
    if tmp_dir:
        options = dc_replace(options, cwd=str(tmp_dir))

    # 消费完整 SSE 流
    answer_parts: list[str] = []
    skills_used: list[str] = []
    cited_urls: list[str] = []

    try:
        from claude_agent_sdk import ClaudeSDKClient
        from api.core.streaming import StreamProcessor

        client = ClaudeSDKClient(options=options)
        await client.connect()
        await client.query(prompt, session_id="replay")

        processor = StreamProcessor(client=client, request=request, session_service=None, on_session_id=None)
        try:
            async for message in processor.process():
                event = message.get("event")
                if event == "assistant_message":
                    try:
                        content = json.loads(message["data"]).get("content", "")
                        answer_parts.append(content)
                        for _, url in _md_url.findall(content):
                            url = url.strip()
                            if url not in cited_urls:
                                cited_urls.append(url)
                        for url in _bare_url.findall(content):
                            url = url.rstrip(".")
                            if url not in cited_urls:
                                cited_urls.append(url)
                    except Exception:
                        pass
                elif event == "tool_use":
                    try:
                        data = json.loads(message["data"])
                        if data.get("name") == "Skill":
                            sname = (data.get("input") or {}).get("skill")
                            if sname and sname not in skills_used:
                                skills_used.append(sname)
                    except Exception:
                        pass
                elif event == "error":
                    data = json.loads(message.get("data", "{}"))
                    raise ValueError(data.get("message", "Agent 执行错误"))
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    finally:
        if tmp_dir:
            _cleanup_tmp_cwd(tmp_dir)

    return {
        "answer": "".join(answer_parts),
        "cited_knowledge": [{"url": u} for u in cited_urls],
        "skills_used": skills_used,
        "trace_id": trace_id,
    }
