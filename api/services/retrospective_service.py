"""
Issue 复盘服务。
每天凌晨由 APScheduler 触发，分析当天诊断日志，识别 Agent 错误，
生成知识库改进草稿，并通过云之家通知管理员 review。
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 纠正信号关键词（需足够明确，避免误匹配正常对话）
CORRECTION_KEYWORDS = [
    "不对",
    "应该是",
    "实际上",
    "你理解错了",
    "错了",
    "不准确",
    "重新看",
    "你搞错了",
    "理解有误",
]

# 目标 skill（只复盘诊断类）
DIAGNOSIS_SKILLS = {
    "issue-diagnosis-billing",
    "issue-diagnosis",
    "issue-diagnosis-external",
}


def _get_interactions_log_path(target_date: "datetime.date") -> Path:
    """
    获取指定日期的 interactions.log 路径。
    优先读归档文件 interactions.log.YYYY-MM-DD，不存在时回退到 interactions.log（按日期过滤）。

    Args:
        target_date: 要读取的日期

    Returns:
        对应的日志文件路径（调用方负责按日期过滤内容）
    """
    log_dir = os.getenv("LOG_DIR", "log")
    log_base = Path(log_dir)
    archived = log_base / f"interactions.log.{target_date.strftime('%Y-%m-%d')}"
    if archived.exists():
        return archived
    # 归档文件不存在（服务未重启导致未归档），回退到当前 interactions.log，_parse_log_entries 会按日期过滤
    return log_base / "interactions.log"


def _parse_log_entries(log_path: Path, target_date: datetime.date) -> list[dict]:
    """
    从 interactions.log 中读取指定日期的诊断类 session 记录。

    Args:
        log_path: interactions.log 文件路径
        target_date: 要分析的日期

    Returns:
        符合条件的日志条目列表
    """
    entries = []
    if not log_path.exists():
        logger.warning(f"[Retrospective] interactions.log not found: {log_path}")
        return entries

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # 过滤日期
            ts = entry.get("timestamp", "")
            if not ts:
                continue
            try:
                entry_date = datetime.fromisoformat(ts).date()
            except ValueError:
                continue
            if entry_date != target_date:
                continue

            entries.append(entry)

    return entries


def _detect_correction(entry: dict) -> bool:
    """
    判断该单条记录是否存在明确的用户纠正信号（关键词匹配）。

    Args:
        entry: 单条 interactions.log 记录

    Returns:
        True 表示存在纠正信号
    """
    question = entry.get("question", "")

    # 用户问题中含纠正关键词
    for kw in CORRECTION_KEYWORDS:
        if kw in question:
            return True

    # 用户回复"2 未解决"
    if "2" in question and "未解决" in question:
        return True
    if question.strip() == "2":
        return True

    return False


def _detect_session_correction(session_entries: list[dict]) -> bool:
    """
    判断同一 session 的多条记录中是否存在纠正信号。
    规则：第一条 Agent 回答含【结论类型】后，后续还有用户继续追问（说明用户对结论不满意）。

    Args:
        session_entries: 同一 session 的所有记录，按时间正序

    Returns:
        True 表示存在纠正信号
    """
    if len(session_entries) <= 1:
        return False

    # 检查是否有单条记录命中关键词
    for entry in session_entries:
        if _detect_correction(entry):
            return True

    # 检查：第一条含结论类型，且后续还有追问（用户对结论不认可继续对话）
    first_answer = session_entries[0].get("answer", "")
    if "【结论类型】" in first_answer and len(session_entries) >= 2:
        return True

    return False


def _detect_multi_turn_convergence(entries: list[dict]) -> list[str]:
    """
    找出同一 session 内超过 3 轮才收敛的 session_id 列表。

    Args:
        entries: 当天所有日志条目

    Returns:
        需要复盘的 session_id 列表
    """
    session_turns: dict[str, int] = {}
    for entry in entries:
        sid = entry.get("session_id", "")
        if not sid:
            continue
        session_turns[sid] = session_turns.get(sid, 0) + entry.get("num_turns", 1)

    return [sid for sid, turns in session_turns.items() if turns >= 3]


def _analyze_entries(entries: list[dict]) -> list[dict]:
    """
    分析当天日志，找出需要复盘的 session。
    触发条件：session 维度存在纠正信号（关键词/未解决/结论后继续追问），纯多轮成功不触发。

    Args:
        entries: 当天所有日志条目

    Returns:
        需要复盘的代表性条目列表（每个 session 取第一条），附加 _retrospective_reasons 和 _session_entries
    """
    # 按 session 分组，保持时间顺序
    session_map: dict[str, list[dict]] = {}
    for entry in entries:
        sid = entry.get("session_id", "")
        if not sid:
            continue
        session_map.setdefault(sid, []).append(entry)

    flagged = []
    for sid, session_entries in session_map.items():
        has_correction = _detect_session_correction(session_entries)
        total_turns = sum(e.get("num_turns", 1) for e in session_entries)
        in_multi_turn = total_turns >= 3
        # 异常中断（600s 超时、流异常）或 error 状态本身就是最强的"需改进"信号，
        # 这类 session 往往只有 1 条记录、无用户纠正关键词，必须单独识别，否则会被漏掉。
        has_abnormal = any(
            e.get("status") in ("interrupted", "error") for e in session_entries
        )

        reasons = []
        if has_correction:
            reasons.append("用户纠正")
        if in_multi_turn and has_correction:
            reasons.append("多轮收敛(>=3轮)")
        if has_abnormal:
            _st = next(
                (
                    e.get("status")
                    for e in session_entries
                    if e.get("status") in ("interrupted", "error")
                ),
                "error",
            )
            reasons.append("异常中断" if _st == "interrupted" else "执行报错")

        # 反问未应答：session 最后一条记录以 AskUserQuestion 收尾，当天再无后续记录，
        # 说明任务悬停在等待用户确认、从未真正闭环（用户回复会续接同一 claude session，
        # 见 plugins/bundled/linear/handler.py 的 _session_map）。这类 session
        # status=success、常仅 1 条记录、无纠正关键词，会被上面三类条件全部漏掉。
        # 实证：20260908 的 code-fix session 95fc911a 反问 4 次无人应答后自行拍板
        # 推送两个生产仓库，当日复盘 flagged=0 完全未捕获。
        pending_reply = (
            bool(session_entries[-1].get("asked_user_question")) and not has_abnormal
        )
        if pending_reply:
            reasons.append("反问未应答")

        if reasons:
            # 取第一条作为代表，附加完整 session 记录供 LLM 分析
            rep = session_entries[0].copy()
            rep["_retrospective_reasons"] = reasons
            rep["_session_entries"] = session_entries
            rep["_pending_reply"] = pending_reply
            flagged.append(rep)

    return flagged


def _generate_draft(entry: dict, date_str: str, analysis: dict) -> tuple[Path, str]:
    """
    为单个需要复盘的 session 生成草稿文件。

    Args:
        entry: 日志条目（含 _retrospective_reasons）
        date_str: 日期字符串，格式 YYYYMMDD
        analysis: LLM 分析结果，含 error_type/root_cause/knowledge_content/target_file

    Returns:
        (草稿文件路径, 草稿内容)
    """
    agent_cwd = os.getenv("AGENT_CWD", "agent_cwd")
    pending_dir = (
        Path(agent_cwd) / ".claude" / "skills" / "issue-retrospective" / "pending"
    )
    pending_dir.mkdir(parents=True, exist_ok=True)

    session_id = entry.get("session_id", "unknown")[:8]
    reasons = entry.get("_retrospective_reasons", [])
    question = entry.get("question", "")[:200]
    answer = entry.get("answer", "")[:500]
    num_turns = entry.get("num_turns", 1)

    # LLM 分析结果
    error_type = analysis.get("error_type", "（待填写）")
    root_cause = analysis.get("root_cause", "（待填写）")
    target_file = analysis.get(
        "target_file",
        "（待填写，如 issue-diagnosis-billing/references/knowledge-base-input.md）",
    )
    knowledge_content = analysis.get("knowledge_content", "（待填写）")

    # 错误类型勾选
    type_checks = {
        "知识缺失": "- [x] 知识缺失：Agent 不了解业务规则/表结构语义\n- [ ] 推理路径偏差：业务知识足够但推理方向走错\n- [ ] 服务定位错误：找错了服务或文件",
        "推理路径偏差": "- [ ] 知识缺失：Agent 不了解业务规则/表结构语义\n- [x] 推理路径偏差：业务知识足够但推理方向走错\n- [ ] 服务定位错误：找错了服务或文件",
        "服务定位错误": "- [ ] 知识缺失：Agent 不了解业务规则/表结构语义\n- [ ] 推理路径偏差：业务知识足够但推理方向走错\n- [x] 服务定位错误：找错了服务或文件",
    }
    type_section = type_checks.get(
        error_type,
        "- [ ] 知识缺失：Agent 不了解业务规则/表结构语义\n- [ ] 推理路径偏差：业务知识足够但推理方向走错\n- [ ] 服务定位错误：找错了服务或文件",
    )

    filename = f"{date_str}_correction_{session_id}.md"
    filepath = pending_dir / filename

    content = f"""# Session {session_id} 复盘 - {date_str}

## 触发原因
{chr(10).join(f'- {r}' for r in reasons)}

## Session 信息
- session_id: {entry.get('session_id', '')}
- 对话轮次: {num_turns}
- 状态: {entry.get('status', '')}

## 用户问题摘要
{question}

## Agent 回答摘要
{answer}

## 错误类型分析（AI 初判，请确认）
{type_section}

## 根因（AI 分析）
{root_cause}

## 建议写入知识库

**目标文件**：{target_file}

**新增内容**：
{knowledge_content}

## 操作
- [ ] 确认写入知识库
- [ ] 拒绝（在此说明原因）
"""

    filepath.write_text(content, encoding="utf-8")
    return filepath, content


async def _llm_analyze_session(entry: dict) -> dict:
    """
    调用 LLM 分析单个需要复盘的 session，推断知识缺失点并生成知识条目草稿。

    Args:
        entry: 日志条目（含 _retrospective_reasons）

    Returns:
        包含 error_type、root_cause、target_file、knowledge_content 的字典，
        分析失败时返回空字典
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("[Retrospective] anthropic 未安装，跳过 LLM 分析")
        return {}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    model = (
        os.getenv("ANTHROPIC_SMALL_FAST_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or "claude-sonnet-4-6"
    )

    # 兜底：LiteLLM 代理（服务器默认配置）
    if not api_key and not auth_token and not base_url:
        litellm_key = os.getenv("LITELLM_API_KEY")
        litellm_url = os.getenv("LITELLM_BASE_URL")
        if litellm_key and litellm_url:
            auth_token = litellm_key
            base_url = litellm_url
            model = (
                os.getenv("LITELLM_SMALL_FAST_MODEL")
                or os.getenv("LITELLM_MODEL")
                or model
            )

    if not api_key and not auth_token:
        logger.warning("[Retrospective] Anthropic API 未配置，跳过 LLM 分析")
        return {}

    client_kwargs: dict = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    elif auth_token:
        client_kwargs["auth_token"] = auth_token
    if base_url:
        client_kwargs["base_url"] = base_url

    question = entry.get("question", "")
    answer = entry.get("answer", "")
    reasons = entry.get("_retrospective_reasons", [])
    status = entry.get("status", "")
    num_turns = entry.get("num_turns", 1)
    session_entries = entry.get("_session_entries", [entry])

    # 判断 session 是否最终成功完成（含"修复完成"标记）
    all_answers = " ".join(e.get("answer", "") for e in session_entries)
    is_completed = status == "success" and "修复完成" in all_answers

    # 读取项目架构文件，让 LLM 自己理解系统设计，而不是硬编码描述
    agent_cwd = os.getenv("AGENT_CWD", "agent_cwd")
    project_context = ""
    context_files = [
        "CLAUDE.md",
    ]
    # 读取各 skill 的 SKILL.md
    skills_dir = Path(agent_cwd) / ".claude" / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                context_files.append(str(skill_md))

    for fpath in context_files:
        p = Path(fpath)
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8")[:2000]
                project_context += f"\n\n=== {fpath} ===\n{content}"
            except Exception:
                pass

    # 构建完整 session 对话记录
    session_dialogue = ""
    for i, e in enumerate(session_entries, 1):
        session_dialogue += f"\n--- 第{i}轮 ---\n用户：{e.get('question','')[:300]}\nAgent：{e.get('answer','')[:500]}\n"

    prompt = f"""你是一个 AI Agent 系统的质量分析师。请结合以下项目文件，分析一次存在问题的诊断对话。

【项目架构文件】（请仔细阅读，理解各 skill 的职责分工和知识库结构）
{project_context[:4000]}

【Session 信息】
- 触发原因：{', '.join(reasons)}
- 最终状态：{status}
- 对话轮次：{num_turns}
- 是否已完成修复：{"是（含修复完成标记）" if is_completed else "否"}

【完整对话记录】
{session_dialogue[:2000]}

请先判断：该 session 是否真的存在需要改进的问题？
- 如果 session 最终成功完成（状态 success 且含"修复完成"），说明整体流程正常，触发原因可能是误判，请返回 needs_review: false
- 如果 session 因外部服务故障失败（回答中只有 API Error 类报错，如模型网关 504/429、限流、预算耗尽、推理服务超时等，且没有任何诊断分析过程），根因在外部推理网关而非 Agent 的诊断能力，请返回 needs_review: false（其余字段填空字符串）
- 如果存在明确的诊断错误或知识缺失，请返回 needs_review: true 并分析

分析时请注意：
1. 结合项目文件理解各 skill 的职责边界，不要把"符合设计的行为"判断为错误
2. target_file 必须给出完整相对路径（参考 CLAUDE.md 中的知识库路径说明）

请严格按以下 JSON 格式输出，不要有其他内容：
{{
  "needs_review": true,
  "error_type": "知识缺失",
  "root_cause": "Agent 不了解 xxx 的业务语义",
  "knowledge_content": "具体知识条目内容",
  "target_file": "agent_cwd/.claude/skills/issue-diagnosis-billing/references/knowledge-base-input.md"
}}"""

    try:
        client = anthropic.AsyncAnthropic(**client_kwargs)
        message = await client.messages.create(
            model=model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text_block = next((b for b in message.content if b.type == "text"), None)
        if text_block is None:
            return {}
        import json as _json

        text = text_block.text.strip()
        # 提取 JSON（可能有多余文字）
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return {}
        json_str = text[start:end]
        # 替换中文引号为英文引号，清理可能导致解析失败的字符
        json_str = (
            json_str.replace("“", '"')
            .replace("”", '"')
            .replace("‘", "'")
            .replace("’", "'")
        )
        return _json.loads(json_str)
    except Exception as e:
        logger.warning(f"[Retrospective] LLM 分析失败: {e}")
        return {}


async def _send_yunzhijia_notification(
    draft_paths: list[Path],
    total_analyzed: int,
    flagged_count: int,
    pending_reply_entries: Optional[list[dict]] = None,
):
    """
    通过云之家 notify 接口发送复盘完成通知给管理员。
    接口：POST {RETROSPECTIVE_NOTIFY_URL}，body: {"name": ..., "type": "text", "text": ...}

    Args:
        draft_paths: 生成的草稿文件路径列表
        total_analyzed: 当天分析的 session 总数
        flagged_count: 需要复盘的 session 数量
        pending_reply_entries: 反问后无人应答、任务悬停未闭环的 session 条目，
            不生成草稿但需在通知中提醒人工跟进
    """
    notify_url = os.getenv("RETROSPECTIVE_NOTIFY_URL", "")
    notify_name = os.getenv("RETROSPECTIVE_NOTIFY_NAME", "管理员")

    if not notify_url:
        logger.warning(
            "[Retrospective] 云之家通知配置缺失（RETROSPECTIVE_NOTIFY_URL），跳过通知"
        )
        return

    pending_reply_entries = pending_reply_entries or []

    # 反问后无人应答的 session：任务悬停未闭环，需人工回到对话里回复
    pending_text = ""
    if pending_reply_entries:
        lines = []
        for e in pending_reply_entries[:10]:
            sid8 = e.get("session_id", "unknown")[:8]
            skill = e.get("skill", "-")
            lines.append(f"  - {sid8}（{skill}）")
        if len(pending_reply_entries) > 10:
            lines.append(f"  ... 共 {len(pending_reply_entries)} 个")
        pending_text = (
            f"\n\n⏳ {len(pending_reply_entries)} 个会话反问后无人应答，任务未闭环：\n"
            + "\n".join(lines)
            + "\n请回到对话中回复，否则该工单不会被继续处理。"
        )

    if flagged_count == 0:
        msg = (
            f"✅ 今日复盘完成\n共分析 {total_analyzed} 个诊断 session，无需复盘的条目。"
        )
    elif not draft_paths and pending_reply_entries:
        # 全部条目都只是"反问未应答"，没有需要 review 的知识库草稿
        msg = (
            f"📋 今日复盘完成\n"
            f"共分析 {total_analyzed} 个诊断 session，无需 review 的知识库草稿。"
            f"{pending_text}"
        )
    else:
        paths_text = "\n".join(f"  - {p.name}" for p in draft_paths[:10])
        if len(draft_paths) > 10:
            paths_text += f"\n  ... 共 {len(draft_paths)} 个文件"
        msg = (
            f"📋 今日复盘完成\n"
            f"共分析 {total_analyzed} 个诊断 session，发现 {flagged_count} 个需复盘。\n\n"
            f"草稿文件（待 review）：\n{paths_text}\n\n"
            f"路径：agent_cwd/.claude/skills/issue-retrospective/pending/"
            f"{pending_text}"
        )

    import aiohttp

    payload = {"name": notify_name, "type": "text", "text": msg}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                notify_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    logger.info(
                        f"[Retrospective] 云之家通知已发送，flagged={flagged_count}"
                    )
                else:
                    body = await resp.text()
                    logger.error(
                        f"[Retrospective] 云之家通知失败，status={resp.status}, body={body}"
                    )
    except Exception:
        logger.exception("[Retrospective] 云之家通知异常")


async def run_daily_retrospective(target_date: Optional[datetime.date] = None):
    """
    执行每日复盘任务的主入口。
    分析 interactions.log 中指定日期的诊断 session，生成草稿并发云之家通知。

    Args:
        target_date: 要分析的日期，默认为昨天
    """
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).date()

    date_str = target_date.strftime("%Y%m%d")
    logger.info(f"[Retrospective] 开始复盘 {date_str} 的诊断记录")

    log_path = _get_interactions_log_path(target_date)
    entries = _parse_log_entries(log_path, target_date)
    logger.info(f"[Retrospective] 读取到 {len(entries)} 条记录")

    flagged = _analyze_entries(entries)
    logger.info(f"[Retrospective] 需要复盘的 session：{len(flagged)} 个")

    # 已处理的 session 集合（pending + confirmed 目录下的文件名提取）
    agent_cwd = os.getenv("AGENT_CWD", "agent_cwd")
    retro_dir = Path(agent_cwd) / ".claude" / "skills" / "issue-retrospective"
    processed_sessions: set[str] = set()
    for sub in ("pending", "confirmed"):
        d = retro_dir / sub
        if d.exists():
            for f in d.iterdir():
                # 文件名格式：{日期}_correction_{sessionId前8位}.md
                parts = f.stem.split("_correction_")
                if len(parts) == 2:
                    processed_sessions.add(parts[1])

    draft_paths = []
    pending_reply_entries: list[dict] = []
    for entry in flagged:
        try:
            sid8 = entry.get("session_id", "")[:8]
            # 仅因"反问未应答"入选的 session 不是 Agent 错误，生成知识库改进草稿没有意义
            # （LLM 也会判 needs_review=false），直接进通知提醒人工跟进即可。
            # 若同时命中其他信号（用户纠正/异常中断），仍走正常草稿流程。
            if (
                entry.get("_pending_reply")
                and len(entry.get("_retrospective_reasons", [])) == 1
            ):
                pending_reply_entries.append(entry)
                continue
            if sid8 in processed_sessions:
                logger.info(f"[Retrospective] 已有草稿，跳过：{sid8}")
                continue
            analysis = await _llm_analyze_session(entry)
            # LLM 判断不需要复盘时跳过草稿生成
            if not analysis.get("needs_review", True):
                logger.info(f"[Retrospective] LLM 判断无需复盘，跳过：{sid8}")
                continue
            filepath, _ = _generate_draft(entry, date_str, analysis)
            draft_paths.append(filepath)
            logger.info(f"[Retrospective] 生成草稿：{filepath.name}")
        except Exception:
            logger.exception(
                f"[Retrospective] 生成草稿失败：{entry.get('session_id', '')}"
            )

    if pending_reply_entries:
        logger.info(
            f"[Retrospective] 反问未应答的 session：{len(pending_reply_entries)} 个"
        )
    await _send_yunzhijia_notification(
        draft_paths, len(entries), len(flagged), pending_reply_entries
    )
    logger.info(f"[Retrospective] 复盘完成，共生成 {len(draft_paths)} 个草稿")
