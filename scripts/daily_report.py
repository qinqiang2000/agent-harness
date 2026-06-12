#!/usr/bin/env python
"""
Issue Diagnosis 日报生成器（含智能客服指标）

Usage:
    python scripts/daily_report.py              # 昨天
    python scripts/daily_report.py --date 20260528
    python scripts/daily_report.py --dry-run    # 只打印，不发送
"""

import argparse
import asyncio
import bisect
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LOG_DIR = PROJECT_ROOT / "log"
INTERACTIONS_LOG = LOG_DIR / "interactions.log"
REPORTS_DIR = PROJECT_ROOT / "reports"

WEBHOOK_URL = os.getenv(
    "YZJ_DAILY_REPORT_WEBHOOK_URL",
    "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken=48318e043db147b39b110b66ea58c344",
)
AT_MENTION = os.getenv("YZJ_DAILY_REPORT_AT_MENTION", "@金帆")
MAX_CHARS = 7800  # 留 200 buffer，云之家限制 8000

# ─────────────── 智能客服分析：常量 ───────────────

CS_LOG_DIR = LOG_DIR

_HUMAN_REQUEST_KW = [
    "转人工", "人工客服", "人工服务", "人工座席", "人工坐席",
    "要人工", "找人工", "在线坐席", "在线客服", "联系人工",
    "接人工", "转客服", "找客服", "人工处理", "人工支持",
    "转人工客服", "转在线", "人工回答",
]
_TRANSFER_PHRASES = [
    "已为您转接", "正在为您转接", "转人工请求已提交",
    "转人工已触发", "转人工请求已收到", "转接人工",
    "为您转接专属", "转人工请求已发出", "转接中，请耐心等待",
    "已触发转人工", "为您转接，请稍候",
]
_FALLBACK_PHRASES = [
    "没找到本答案", "知识库没找到", "在发票云知识库没找到",
    "无法在知识库中找到", "暂时无法解答",
]
_DISCONNECT_WINDOW_S = 10
_TIMEOUT_MS = 55_000
_PLACEHOLDER_RID = "pntogryk"


def load_interactions(date_str: str) -> list[dict]:
    """读取指定日期的 interactions.log，只返回 skill=issue-diagnosis 的记录。"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    target_date = dt.strftime("%Y-%m-%d")

    archived = INTERACTIONS_LOG.with_suffix(f".log.{target_date}")

    if date_str == today_str:
        path = INTERACTIONS_LOG
        filter_by_date = False
    elif archived.exists():
        path = archived
        filter_by_date = False
    else:
        # 归档文件不存在说明轮转尚未发生，数据仍在当前日志中
        path = INTERACTIONS_LOG
        filter_by_date = True

    if not path.exists():
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("skill") != "issue-diagnosis":
                    continue
                if filter_by_date and not (r.get("timestamp") or "").startswith(target_date):
                    continue
                records.append(r)
            except json.JSONDecodeError:
                pass
    return records


def aggregate(records: list[dict]) -> dict:
    """从记录列表中提取统计指标。"""
    total = len(records)
    if total == 0:
        return {"total": 0}

    status_counts: dict[str, int] = {"success": 0, "error": 0, "timeout": 0}
    duration_list: list[int] = []
    unresolved: list[dict] = []   # asked_user_question=True 且 status=success
    high_turns: list[dict] = []   # num_turns > 10
    errors: list[dict] = []       # status != success

    for r in records:
        status = r.get("status", "success")
        status_counts[status] = status_counts.get(status, 0) + 1

        ms = r.get("duration_ms")
        if ms:
            duration_list.append(ms)

        if status != "success":
            errors.append({
                "question": (r.get("question") or "")[:80],
                "status": status,
                "session_id": r.get("session_id"),
                "timestamp": r.get("timestamp"),
            })

        if r.get("asked_user_question") and status == "success":
            unresolved.append({
                "question": (r.get("question") or "")[:80],
                "answer_excerpt": (r.get("answer") or "")[:120],
                "session_id": r.get("session_id"),
                "timestamp": r.get("timestamp"),
            })

        turns = r.get("num_turns", 0) or 0
        if turns > 10:
            high_turns.append({
                "question": (r.get("question") or "")[:80],
                "num_turns": turns,
                "session_id": r.get("session_id"),
            })

    # 高频问题 Top5：按完整 question 聚类，保留代表性记录（问题+回复）
    question_counter = Counter(
        (r.get("question") or "") for r in records if r.get("question")
    )
    top_questions_detail: list[dict] = []
    for q_text, cnt in question_counter.most_common(5):
        rep = next((r for r in records if r.get("question") == q_text), {})
        top_questions_detail.append({
            "question": q_text,
            "count": cnt,
            "answer": (rep.get("answer") or "")[:300],
            "status": rep.get("status", "success"),
        })
    top_questions = top_questions_detail

    # 耗时统计
    duration_stats: dict = {}
    if duration_list:
        duration_list.sort()
        n = len(duration_list)
        duration_stats = {
            "avg_ms": int(sum(duration_list) / n),
            "p95_ms": duration_list[int(n * 0.95)],
            "max_ms": duration_list[-1],
        }

    return {
        "total": total,
        "status_counts": status_counts,
        "duration_stats": duration_stats,
        "unresolved": unresolved[:10],
        "errors": errors[:10],
        "high_turns": high_turns[:5],
        "top_questions": top_questions,
    }


async def llm_summarize(stats: dict, records: list[dict], date_str: str) -> str:
    """调用当前 DEFAULT_MODEL_CONFIG 对应的模型生成总结，失败时返回空字符串。"""
    try:
        import anthropic
    except ImportError:
        return ""

    # 直接读 ConfigService 已写入的环境变量
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    model = (
        os.getenv("ANTHROPIC_SMALL_FAST_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or "claude-haiku-4-5-20251001"
    )

    if not api_key and not base_url:
        return ""

    client_kwargs: dict = {}
    if os.getenv("ANTHROPIC_API_KEY"):
        client_kwargs["api_key"] = os.getenv("ANTHROPIC_API_KEY")
    elif os.getenv("ANTHROPIC_AUTH_TOKEN"):
        client_kwargs["auth_token"] = os.getenv("ANTHROPIC_AUTH_TOKEN")
    if base_url:
        client_kwargs["base_url"] = base_url

    sc = stats.get("status_counts", {})
    ds = stats.get("duration_stats", {})

    top_qs_text = ""
    for item in stats.get("top_questions", []):
        top_qs_text += f"\n问题（×{item['count']}）：{item['question']}\nAI回复：{item['answer']}\n"

    unresolved_text = "\n".join(
        f"· {item.get('question', '')}" for item in stats.get("unresolved", [])
    )

    prompt = f"""你是技术支持质量分析师，请根据以下数据生成 issue-diagnosis AI 诊断服务日报总结。

日期：{date_str}

【关键指标】
总对话：{stats.get('total', 0)} | 成功：{sc.get('success', 0)} | 错误：{sc.get('error', 0)} | 超时：{sc.get('timeout', 0)}
响应时间：均值 {ds.get('avg_ms', 0) / 1000:.1f}s | P95 {ds.get('p95_ms', 0) / 1000:.1f}s | 最慢 {ds.get('max_ms', 0) / 1000:.1f}s
可能未解决（AI反问用户）：{len(stats.get('unresolved', []))} 条
诊断轮次过多（>10轮）：{len(stats.get('high_turns', []))} 条

【高频问题及AI回复】
{top_qs_text or "无"}

【可能未解决的问题】
{unresolved_text or "无"}

请分析：
1. 今日整体服务质量（成功率、响应速度是否正常）
2. 高频问题的 AI 回复质量，有无需要补充到知识库的内容
3. 未解决问题的规律和跟进建议
4. 超时或错误的可能原因（如有）

要求：中文，分段落，不超过 500 字，直接给结论和建议，不要重复列数字。"""

    try:
        client = anthropic.AsyncAnthropic(**client_kwargs)
        message = await client.messages.create(
            model=model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text_block = next((b for b in message.content if b.type == "text"), None)
        if text_block is None:
            return "（LLM 总结失败: 响应中无文本内容）"
        return text_block.text.strip()
    except Exception as e:
        return f"（LLM 总结失败: {e}）"


def format_report(stats: dict, date_str: str, llm_summary: str) -> str:
    """将统计数据格式化为云之家纯文本消息，控制在 MAX_CHARS 内。"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    date_label = dt.strftime("%Y-%m-%d")

    if stats.get("total", 0) == 0:
        return f"{AT_MENTION}\n\n📊 Issue Diagnosis 日报 · {date_label}\n\n暂无对话记录。"

    sc = stats.get("status_counts", {})
    total = stats["total"]
    success = sc.get("success", 0)
    error = sc.get("error", 0)
    timeout = sc.get("timeout", 0)
    success_rate = f"{success / total * 100:.1f}%" if total else "N/A"

    ds = stats.get("duration_stats", {})
    avg_s = f"{ds['avg_ms'] / 1000:.1f}s" if ds.get("avg_ms") else "N/A"
    p95_s = f"{ds['p95_ms'] / 1000:.1f}s" if ds.get("p95_ms") else "N/A"
    max_s = f"{ds['max_ms'] / 1000:.1f}s" if ds.get("max_ms") else "N/A"

    lines = [
        AT_MENTION,
        "",
        f"📊 Issue Diagnosis 日报 · {date_label}",
        "",
        "【基础统计】",
        f"总对话：{total} | 成功：{success}（{success_rate}）| 错误：{error} | 超时：{timeout}",
        f"响应时间：均值 {avg_s} | P95 {p95_s} | 最慢 {max_s}",
    ]

    top_qs = stats.get("top_questions", [])
    if top_qs:
        lines += ["", "【高频问题 Top5 · 建议补充知识库】"]
        for i, item in enumerate(top_qs, 1):
            q = item.get("question", "")
            cnt = item.get("count", 1)
            ans = item.get("answer", "")
            lines.append(f"{i}. （×{cnt}）{q}")
            if ans:
                lines.append(f"   AI回复：{ans}")

    unresolved = stats.get("unresolved", [])
    if unresolved:
        lines += ["", f"【可能未解决 · 需跟进】（{len(unresolved)} 条）"]
        for item in unresolved[:5]:
            ts = (item.get("timestamp") or "")[:16]
            lines.append(f"· [{ts}] {item['question']}")

    errors = stats.get("errors", [])
    if errors:
        lines += ["", f"【异常记录】（{len(errors)} 条）"]
        for item in errors[:5]:
            ts = (item.get("timestamp") or "")[:16]
            lines.append(f"· [{ts}] {item['status'].upper()} {item['question']}")

    high_turns = stats.get("high_turns", [])
    if high_turns:
        lines += ["", "【诊断轮次过多 · 疑似兜圈】"]
        for item in high_turns:
            lines.append(f"· {item['num_turns']} 轮 {item['question']}")

    if llm_summary:
        lines += ["", "【AI 总结】", llm_summary]

    text = "\n".join(lines)

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS - 20] + "\n\n（内容已截断）"

    return text


async def send_to_yunzhijia(text: str) -> bool:
    """POST 到云之家 webhook，返回是否成功。"""
    import aiohttp
    payload = {"content": text}
    logger.info("[send] 发送日报，内容长度 %d 字符", len(text))
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                body = await resp.text()
                if resp.status == 200:
                    logger.info("[send] 发送成功，响应: %s", body[:200])
                    return True
                logger.error("[send] HTTP %d: %s", resp.status, body[:500])
                return False
    except Exception as e:
        logger.error("[send] 请求失败: %s", e, exc_info=True)
        return False


# ─────────────── 智能客服分析函数 ───────────────

def _cs_is_human_request(text: str) -> bool:
    return any(kw in text for kw in _HUMAN_REQUEST_KW)

def _cs_is_actual_transfer(answer: str) -> bool:
    return any(p in answer for p in _TRANSFER_PHRASES)

def _cs_answer_is_substantive(record: dict) -> bool:
    answer = record.get("answer", "")
    question = record.get("question", "")
    if _cs_is_human_request(question) and _cs_is_actual_transfer(answer):
        return False
    if record.get("used_fallback_phrase") or any(p in answer for p in _FALLBACK_PHRASES):
        return False
    if record.get("has_doc_url"):
        return True
    if record.get("status") == "success" and "以上回复是否已经解决" in answer:
        return True
    return False

def _cs_percentile(data: list, p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    n = len(s)
    idx = (p / 100) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return s[lo] * (1 - (idx - lo)) + s[hi] * (idx - lo)

def _cs_load_interactions(log_dir: Path, target_date: date) -> list[dict]:
    records = []
    for lf in sorted(log_dir.glob("interactions.log*")):
        name = lf.name
        if name == "interactions.log":
            file_date = date.today()
        else:
            date_str = name.split(".")[-1]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
        if file_date != target_date:
            continue
        with open(lf, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records

def _cs_load_disconnect_events(log_dir: Path) -> set:
    pat_start = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* \[PERF\] rid=(\w+) ZHICHI_SEND_START"
    )
    pat_done = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* \[PERF\] ZHICHI_SEND_DONE"
    )
    starts, dones = [], []
    log_files = sorted(log_dir.glob("app-*.log"))
    app_log = log_dir / "app.log"
    if app_log.exists():
        log_files.append(app_log)
    for lf in log_files:
        try:
            with open(lf, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = pat_start.match(line)
                    if m:
                        dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                        rid = m.group(2)
                        if rid != _PLACEHOLDER_RID:
                            starts.append((dt, rid))
                        continue
                    m = pat_done.match(line)
                    if m:
                        dones.append(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
        except Exception:
            continue
    dones.sort()
    disconnected = set()
    mutable_dones = list(dones)
    for ts, rid in starts:
        idx = bisect.bisect_left(mutable_dones, ts)
        found = False
        for i in range(idx, min(idx + 5, len(mutable_dones))):
            if 0 <= (mutable_dones[i] - ts).total_seconds() <= _DISCONNECT_WINDOW_S:
                mutable_dones.pop(i)
                found = True
                break
        if not found:
            disconnected.add(rid)
    return disconnected

def analyze_smart_cs(target_date: date) -> dict:
    """分析智能客服指标，返回 metrics dict（无数据时 total_sessions=0）。"""
    if not CS_LOG_DIR.exists():
        return {"total_sessions": 0, "error": f"日志目录不存在: {CS_LOG_DIR}"}

    records = _cs_load_interactions(CS_LOG_DIR, target_date)
    disconnected = _cs_load_disconnect_events(CS_LOG_DIR)

    sessions: dict[str, list] = defaultdict(list)
    for r in records:
        sid = r.get("session_id")
        if sid:
            sessions[sid].append(r)
    for sid in sessions:
        sessions[sid].sort(key=lambda r: r.get("timestamp", ""))

    total = len(sessions)
    if total == 0:
        return {"total_sessions": 0}

    immediate_transfer = had_answer = post_answer_transfer = resolved = 0
    all_turn_durations: list[int] = []
    timeout_count = disconnect_count = 0
    slowest_turn = None

    for sid, turns in sessions.items():
        first_q = turns[0].get("question", "")
        durations = [t.get("duration_ms", 0) for t in turns]

        rid_prefix = sid.replace("-", "")[:6]
        session_disconnected = any(rid.startswith(rid_prefix) for rid in disconnected)
        if session_disconnected:
            disconnect_count += 1

        for t, dur in zip(turns, durations):
            if dur > 0:
                all_turn_durations.append(dur)
                if dur >= _TIMEOUT_MS:
                    timeout_count += 1
                if slowest_turn is None or dur > slowest_turn["duration_ms"]:
                    slowest_turn = {"duration_ms": dur, "question": t.get("question", "")[:80]}

        if _cs_is_human_request(first_q):
            immediate_transfer += 1

        session_answered = session_transferred = False
        for turn in turns:
            if _cs_answer_is_substantive(turn):
                session_answered = True
            if _cs_is_actual_transfer(turn.get("answer", "")):
                session_transferred = True

        if session_answered:
            had_answer += 1
            if session_transferred:
                post_answer_transfer += 1
            else:
                resolved += 1

    p50 = round(_cs_percentile(all_turn_durations, 50))
    p95 = round(_cs_percentile(all_turn_durations, 95))
    max_ms = round(max(all_turn_durations)) if all_turn_durations else 0
    avg_ms = round(sum(all_turn_durations) / len(all_turn_durations)) if all_turn_durations else 0
    total_turns = len(all_turn_durations)

    return {
        "total_sessions": total,
        "total_turns": total_turns,
        "avg_resp_ms": avg_ms,
        "p50_ms": p50,
        "p95_ms": p95,
        "max_resp_ms": max_ms,
        "timeout_count": timeout_count,
        "disconnect_count": disconnect_count,
        "problem_turn_count": timeout_count + disconnect_count,
        "immediate_transfer_count": immediate_transfer,
        "immediate_transfer_rate": round(immediate_transfer / total * 100, 1),
        "answered_count": had_answer,
        "answer_rate": round(had_answer / total * 100, 1),
        "post_answer_transfer_count": post_answer_transfer,
        "post_answer_transfer_rate": round(post_answer_transfer / had_answer * 100, 1) if had_answer else 0.0,
        "resolved_count": resolved,
        "resolution_rate": round(resolved / total * 100, 1),
        "slowest_turn_question": (slowest_turn or {}).get("question", "-"),
    }


def generate_cs_html(metrics: dict, target_date: date) -> Path:
    """生成智能客服 HTML 报告，保存到 reports/smart_cs_YYYYMMDD.html，返回路径。"""
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"smart_cs_{target_date.strftime('%Y%m%d')}.html"

    m = metrics
    date_label = target_date.strftime("%Y-%m-%d")

    if m.get("total_sessions", 0) == 0:
        reason = m.get("error", "当日无数据")
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>智能客服日报 {date_label}</title></head>
<body style="font-family:sans-serif;padding:40px;color:#4a5568">
<h2>智能客服日报 · {date_label}</h2><p>{reason}</p>
</body></html>"""
        path.write_text(html, encoding="utf-8")
        return path

    def ms(v): return f"{v / 1000:.2f}s"
    def pct(v, n): return f"{v}%（{n}个）"

    def card(color, label, value, sub=""):
        return f"""
    <div class="card {color}">
      <div class="label">{label}</div>
      <div class="value">{value}</div>
      {"<div class='sub'>" + sub + "</div>" if sub else ""}
    </div>"""

    slowest_q = escape(m.get("slowest_turn_question", "-"))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>智能客服日报 {date_label}</title>
<style>
  body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f7fa;color:#2d3748;margin:0;padding:0}}
  header {{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;padding:28px 40px}}
  header h1 {{margin:0 0 4px;font-size:1.6rem}} header p {{margin:0;opacity:.8;font-size:.9rem}}
  main {{max-width:1100px;margin:28px auto;padding:0 24px}}
  h2 {{font-size:1rem;margin:20px 0 10px;color:#4a5568}}
  .cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:20px}}
  .card {{background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  .card .label {{font-size:.73rem;color:#718096;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px}}
  .card .value {{font-size:1.9rem;font-weight:700}}
  .card .sub {{font-size:.78rem;color:#a0aec0;margin-top:3px}}
  .card.green .value {{color:#38a169}} .card.red .value {{color:#e53e3e}}
  .card.blue .value {{color:#3182ce}} .card.orange .value {{color:#dd6b20}}
  .card.purple .value {{color:#805ad5}}
  .slowest {{background:#fff;border-radius:10px;padding:14px 22px;box-shadow:0 1px 4px rgba(0,0,0,.08);font-size:.875rem;margin-bottom:16px}}
  .slowest .lbl {{font-size:.73rem;color:#718096;text-transform:uppercase;margin-bottom:4px}}
  .slowest .val {{font-weight:700;color:#e53e3e;font-size:1.05rem}}
  footer {{text-align:center;padding:20px;color:#a0aec0;font-size:.78rem}}
</style>
</head>
<body>
<header>
  <h1>智能客服日报</h1>
  <p>{date_label} &nbsp;|&nbsp; {m['total_sessions']} 个会话 / {m['total_turns']} 轮</p>
</header>
<main>
  <h2>业务指标</h2>
  <div class="cards">
    {card("green", "智能客服解决率", pct(m['resolution_rate'], m['resolved_count']), "有答案且未转人工")}
    {card("blue", "回答完成率", pct(m['answer_rate'], m['answered_count']), "给出实质性答案")}
    {card("red", "直接转人工率", pct(m['immediate_transfer_rate'], m['immediate_transfer_count']), "首条消息即转人工")}
    {card("orange", "答后转人工率", pct(m['post_answer_transfer_rate'], m['post_answer_transfer_count']), "给出答案后仍转人工")}
  </div>
  <h2>响应性能（单轮）</h2>
  <div class="cards">
    {card("purple", "P50 中位数", ms(m['p50_ms']), "50% 请求在此内完成")}
    {card("orange", "P95", ms(m['p95_ms']), "95% 请求在此内完成")}
    {card("purple", "平均响应", ms(m['avg_resp_ms']), "所有轮次均值")}
    {card("red", "最慢响应", ms(m['max_resp_ms']), "单轮最长耗时")}
  </div>
  <h2>异常</h2>
  <div class="cards">
    {card("red" if m['timeout_count'] > 0 else "green", f"超时（≥{ms(_TIMEOUT_MS)}）", str(m['timeout_count']), f"共 {m['total_turns']} 轮")}
    {card("red" if m['disconnect_count'] > 0 else "green", "客户端断开", str(m['disconnect_count']), "尽力而为检测")}
    {card("red" if m['problem_turn_count'] > 0 else "green", "问题合计", str(m['problem_turn_count']), "超时 + 断开")}
  </div>
  <div class="slowest">
    <div class="lbl">最慢单轮</div>
    <span class="val">{ms(m['max_resp_ms'])}</span> &nbsp;—&nbsp; 「{slowest_q}」
  </div>
</main>
<footer>Generated by agent-harness daily_report · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</footer>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    return path


def format_cs_section(metrics: dict, html_path: Path) -> str:
    """格式化智能客服章节，追加到日报末尾。"""
    m = metrics
    if m.get("total_sessions", 0) == 0:
        reason = m.get("error", "当日无数据")
        return f"\n\n【智能客服日报】\n暂无数据（{reason}）"

    def ms(v): return f"{v / 1000:.2f}s"
    def pct(v, n): return f"{v}%（{n}个）"

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📱 智能客服 · {m['total_sessions']}个会话 / {m['total_turns']}轮",
        "",
        "【业务指标】",
        f"✅ 解决率：{pct(m['resolution_rate'], m['resolved_count'])}",
        f"📝 回答完成率：{pct(m['answer_rate'], m['answered_count'])}",
        f"👥 直接转人工率：{pct(m['immediate_transfer_rate'], m['immediate_transfer_count'])}",
        f"💬 答后转人工率：{pct(m['post_answer_transfer_rate'], m['post_answer_transfer_count'])}",
        "",
        "【响应性能】",
        f"P50：{ms(m['p50_ms'])}  |  P95：{ms(m['p95_ms'])}  |  最慢：{ms(m['max_resp_ms'])}",
        "",
        "【异常】",
        f"超时（≥{ms(_TIMEOUT_MS)}）：{m['timeout_count']}次  |  客户端断开：{m['disconnect_count']}个",
    ]
    if m["problem_turn_count"] == 0:
        lines.append("🟢 无问题轮次")

    lines.append(f"\n📊 详细报告：{html_path}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────

async def generate_and_send(date_str: str, dry_run: bool = False) -> dict:
    """完整流程：读日志 → 聚合 → LLM → 格式化 → 发送。返回结果摘要。"""
    records = load_interactions(date_str)
    stats = aggregate(records)
    llm_summary = await llm_summarize(stats, records, date_str) if stats.get("total", 0) > 0 else ""
    report_text = format_report(stats, date_str, llm_summary)

    # 智能客服分析
    target_date = datetime.strptime(date_str, "%Y%m%d").date()
    cs_metrics = analyze_smart_cs(target_date)
    cs_html_path = generate_cs_html(cs_metrics, target_date)
    report_text += format_cs_section(cs_metrics, cs_html_path)

    if len(report_text) > MAX_CHARS:
        report_text = report_text[:MAX_CHARS - 20] + "\n\n（内容已截断）"

    if dry_run:
        print(report_text)
        return {"date": date_str, "total": stats.get("total", 0), "sent": False, "dry_run": True}

    sent = await send_to_yunzhijia(report_text)
    return {"date": date_str, "total": stats.get("total", 0), "sent": sent, "dry_run": False}


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [daily_report] %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    parser = argparse.ArgumentParser(description="生成并发送 issue-diagnosis 日报")
    parser.add_argument("--date", help="日期 YYYYMMDD，默认昨天")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    args = parser.parse_args()

    date_str = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    result = asyncio.run(generate_and_send(date_str, dry_run=args.dry_run))
    logger.info("结果: %s", result)


if __name__ == "__main__":
    main()
