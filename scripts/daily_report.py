#!/usr/bin/env python
"""
Issue Diagnosis 日报生成器

Usage:
    python scripts/daily_report.py              # 昨天
    python scripts/daily_report.py --date 20260528
    python scripts/daily_report.py --dry-run    # 只打印，不发送
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LOG_DIR = PROJECT_ROOT / "log"
INTERACTIONS_LOG = LOG_DIR / "interactions.log"

WEBHOOK_URL = "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken=48318e043db147b39b110b66ea58c344"
AT_MENTION = "@金帆"
MAX_CHARS = 7800  # 留 200 buffer，云之家限制 8000


def load_interactions(date_str: str) -> list[dict]:
    """读取指定日期的 interactions.log，只返回 skill=issue-diagnosis 的记录。"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    path = INTERACTIONS_LOG if date_str == today_str else \
        INTERACTIONS_LOG.with_suffix(f".log.{dt.strftime('%Y-%m-%d')}")

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
                if r.get("skill") == "issue-diagnosis":
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
        return message.content[0].text.strip()
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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                print(f"[send] HTTP {resp.status}: {body}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"[send] 请求失败: {e}", file=sys.stderr)
        return False


async def generate_and_send(date_str: str, dry_run: bool = False) -> dict:
    """完整流程：读日志 → 聚合 → LLM → 格式化 → 发送。返回结果摘要。"""
    records = load_interactions(date_str)
    stats = aggregate(records)
    llm_summary = await llm_summarize(stats, records, date_str) if stats.get("total", 0) > 0 else ""
    report_text = format_report(stats, date_str, llm_summary)

    if dry_run:
        print(report_text)
        return {"date": date_str, "total": stats.get("total", 0), "sent": False, "dry_run": True}

    sent = await send_to_yunzhijia(report_text)
    return {"date": date_str, "total": stats.get("total", 0), "sent": sent, "dry_run": False}


def main():
    parser = argparse.ArgumentParser(description="生成并发送 issue-diagnosis 日报")
    parser.add_argument("--date", help="日期 YYYYMMDD，默认昨天")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    args = parser.parse_args()

    date_str = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    result = asyncio.run(generate_and_send(date_str, dry_run=args.dry_run))
    print(f"结果: {result}")


if __name__ == "__main__":
    main()
