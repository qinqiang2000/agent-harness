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

# 纠正信号关键词
CORRECTION_KEYWORDS = [
    "不是",
    "不对",
    "应该是",
    "实际上",
    "你理解错了",
    "错了",
    "不准确",
    "重新看",
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
    判断该 session 是否存在用户纠正信号。

    Args:
        entry: 单条 interactions.log 记录

    Returns:
        True 表示存在纠正信号
    """
    question = entry.get("question", "")
    answer = entry.get("answer", "")

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

    Args:
        entries: 当天所有日志条目

    Returns:
        需要复盘的条目列表，附加 reason 字段说明触发原因
    """
    multi_turn_sessions = set(_detect_multi_turn_convergence(entries))
    flagged = []

    seen_sessions = set()
    for entry in entries:
        sid = entry.get("session_id", "")
        if sid in seen_sessions:
            continue

        reasons = []
        if _detect_correction(entry):
            reasons.append("用户纠正")
        if sid in multi_turn_sessions:
            reasons.append("多轮收敛(>=3轮)")

        if reasons:
            entry["_retrospective_reasons"] = reasons
            flagged.append(entry)
            seen_sessions.add(sid)

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

    prompt = f"""你是一个 AI Agent 系统的质量分析师。以下是一次诊断对话，其中 Agent 的回答出现了问题（触发原因：{', '.join(reasons)}）。

【用户问题】
{question[:500]}

【Agent 回答】
{answer[:800]}

请分析：
1. Agent 犯了什么错误？（知识缺失 / 推理路径偏差 / 服务定位错误，三选一）
2. 根因是什么？（一句话描述 Agent 不知道什么或哪里推理错了）
3. 应该补充什么知识？（具体的知识条目内容，50-150字）
4. 应该写入哪个知识库文件？（从以下选择：knowledge-base-input.md / knowledge-base-image.md / knowledge-base-output.md，或填"SKILL.md修改建议"）

请严格按以下 JSON 格式输出，不要有其他内容：
{{
  "error_type": "知识缺失",
  "root_cause": "Agent 不了解 xxx 的业务语义",
  "knowledge_content": "具体知识条目内容",
  "target_file": "knowledge-base-input.md"
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
    draft_paths: list[Path], total_analyzed: int, flagged_count: int
):
    """
    通过云之家 notify 接口发送复盘完成通知给管理员。
    接口：POST {RETROSPECTIVE_NOTIFY_URL}，body: {"name": ..., "type": "text", "text": ...}

    Args:
        draft_paths: 生成的草稿文件路径列表
        total_analyzed: 当天分析的 session 总数
        flagged_count: 需要复盘的 session 数量
    """
    notify_url = os.getenv("RETROSPECTIVE_NOTIFY_URL", "")
    notify_name = os.getenv("RETROSPECTIVE_NOTIFY_NAME", "管理员")

    if not notify_url:
        logger.warning(
            "[Retrospective] 云之家通知配置缺失（RETROSPECTIVE_NOTIFY_URL），跳过通知"
        )
        return

    if flagged_count == 0:
        msg = (
            f"✅ 今日复盘完成\n共分析 {total_analyzed} 个诊断 session，无需复盘的条目。"
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

    draft_paths = []
    for entry in flagged:
        try:
            analysis = await _llm_analyze_session(entry)
            filepath, _ = _generate_draft(entry, date_str, analysis)
            draft_paths.append(filepath)
            logger.info(f"[Retrospective] 生成草稿：{filepath.name}")
        except Exception:
            logger.exception(
                f"[Retrospective] 生成草稿失败：{entry.get('session_id', '')}"
            )

    await _send_yunzhijia_notification(draft_paths, len(entries), len(flagged))
    logger.info(f"[Retrospective] 复盘完成，共生成 {len(draft_paths)} 个草稿")
