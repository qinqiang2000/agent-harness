#!/usr/bin/env python3
"""
Token 成本日报：按 issue 统计前一日 token 消耗与归因，推送云之家私聊。

与 scripts/daily_report.py（issue-diagnosis 运营日报，群机器人 webhook）区别：
本报表是内部成本治理数据，走 notify 接口点对点私聊，默认收件人复用
RETROSPECTIVE_NOTIFY_NAME。

手动执行：
    python scripts/token_report.py --date 20260908 --dry-run
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 由 app.py 内的定时任务调用时 .env 已加载；作为 CLI 独立执行时需自行加载，
# 否则拿不到 RETROSPECTIVE_NOTIFY_URL 等推送配置
try:
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from api.constants import NOTIFY_MSG_PREFIX  # noqa: E402
from api.services import token_usage_store  # noqa: E402
from api.services.token_usage_store import _fmt_tokens  # noqa: E402

# 单 issue 成本告警阈值（美元），超过则在日报中单独标记
COST_ALERT_USD = float(os.getenv("TOKEN_REPORT_ALERT_USD", "2.0"))
# 日报中展示的 issue 数量上限
TOP_N_ISSUES = int(os.getenv("TOKEN_REPORT_TOP_N", "8"))


def format_report(summary: dict) -> str:
    """把聚合结果渲染成云之家纯文本消息。

    Args:
        summary: token_usage_store.summarize_day 的返回值

    Returns:
        可直接发送的多行文本；当天无数据时返回简短提示
    """
    totals = summary.get("totals") or {}
    if not totals.get("requests"):
        return (
            f"{NOTIFY_MSG_PREFIX}💰 {summary['date']} Token 成本日报\n"
            "当天无 Agent 请求记录。"
        )

    total_tokens = totals.get("total_tokens", 0)
    cache_read = totals.get("cache_read_tokens", 0)
    cost = totals.get("cost_usd", 0.0)
    cost_sdk = totals.get("cost_sdk_usd") or 0.0

    lines = [
        f"{NOTIFY_MSG_PREFIX}💰 {summary['date']} Token 成本日报",
        f"总计 ${cost:.2f} / {_fmt_tokens(total_tokens)} tokens"
        f"（缓存命中 {_fmt_tokens(cache_read)}，按 1/10 计价）",
        f"请求 {totals.get('requests', 0)} 次",
    ]
    # 始终展示 SDK 自报成本做对照：走 litellm 代理时它按上游模型定价，
    # 与本地单价表可能有较大偏差，两个数并列才能判断该信哪个
    if cost_sdk:
        diff_pct = (cost_sdk - cost) / cost * 100 if cost else 0
        flag = " ⚠️" if abs(diff_pct) > 30 else ""
        lines.append(f"（SDK 自报 ${cost_sdk:.2f}，偏差 {diff_pct:+.0f}%{flag}）")

    by_issue = summary.get("by_issue") or []
    if by_issue:
        lines.append("")
        lines.append(f"📌 Issue 成本排行（Top {TOP_N_ISSUES}）：")
        for item in by_issue[:TOP_N_ISSUES]:
            flag = " ⚠️" if item["cost_usd"] >= COST_ALERT_USD else ""
            skills = (item.get("skills") or "").replace(",", "+")
            lines.append(
                f"  {item['issue_key']}  ${item['cost_usd']:.2f}  "
                f"{_fmt_tokens(item['tokens'] or 0)}  "
                f"({item['sessions']}次对话/{item.get('turns') or 0}轮 {skills}){flag}"
            )

    buckets = summary.get("buckets") or {}
    if buckets:
        bucket_total = sum(buckets.values()) or 1
        lines.append("")
        lines.append("📊 消耗结构（按内容归因，合计等于真实计费量）：")
        for name, tokens in list(buckets.items())[:8]:
            pct = tokens / bucket_total * 100
            lines.append(f"  {name}  {_fmt_tokens(tokens)}  {pct:.1f}%")

    top_tools = summary.get("top_tools") or []
    if top_tools:
        lines.append("")
        lines.append("🔍 最占体积的工具返回（可优化靶子）：")
        for t in top_tools[:5]:
            target = t.get("target") or "-"
            # 路径类目标保留尾部，文件名才是可辨识的部分
            target = target if len(target) <= 46 else "..." + target[-43:]
            lines.append(
                f"  [{t['bucket']}] {target}  "
                f"{_fmt_tokens(t['chars'] or 0)} 字符 / {t['calls']} 次"
            )

    return "\n".join(lines)


async def send_notification(text: str) -> bool:
    """通过云之家 notify 接口把日报私聊发给指定收件人。

    Args:
        text: 已渲染好的日报正文

    Returns:
        发送成功返回 True；未配置 URL 或请求失败返回 False
    """
    notify_url = os.getenv("TOKEN_REPORT_NOTIFY_URL") or os.getenv(
        "RETROSPECTIVE_NOTIFY_URL", ""
    )
    notify_name = os.getenv("TOKEN_REPORT_NOTIFY_NAME") or os.getenv(
        "RETROSPECTIVE_NOTIFY_NAME", "管理员"
    )
    if not notify_url:
        print("[TokenReport] 未配置 TOKEN_REPORT_NOTIFY_URL / RETROSPECTIVE_NOTIFY_URL，跳过发送")
        return False

    import aiohttp

    payload = {"name": notify_name, "type": "text", "text": text}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                notify_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    print(f"[TokenReport] 已发送给 {notify_name}")
                    return True
                body = await resp.text()
                print(f"[TokenReport] 发送失败 status={resp.status} body={body}")
                return False
    except Exception as e:
        print(f"[TokenReport] 发送异常: {e}")
        return False


async def generate_and_send(date_str: str, dry_run: bool = False) -> dict:
    """完整流程：聚合 → 渲染 → 发送 → 清理过期明细。

    Args:
        date_str: 日期 YYYYMMDD
        dry_run: 为 True 时只打印不发送，也不清理明细

    Returns:
        含 date / requests / cost_usd / sent 的结果摘要
    """
    summary = token_usage_store.summarize_day(date_str)
    text = format_report(summary)

    if dry_run:
        print(text)
        return {"date": date_str, "sent": False, "dry_run": True}

    sent = await send_notification(text)
    purged = token_usage_store.purge_old_turns()
    return {
        "date": date_str,
        "requests": (summary.get("totals") or {}).get("requests", 0),
        "cost_usd": (summary.get("totals") or {}).get("cost_usd", 0),
        "sent": sent,
        "purged_rows": purged,
    }


def main():
    """CLI 入口：解析参数并执行日报生成。"""
    parser = argparse.ArgumentParser(description="生成并发送 Token 成本日报")
    parser.add_argument("--date", help="日期 YYYYMMDD，默认昨天")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    parser.add_argument("--issue", help="查询单个 issue 的完整用量明细，如 CNPRD-1276")
    args = parser.parse_args()

    if args.issue:
        detail = token_usage_store.issue_detail(args.issue)
        t = detail["totals"]
        if not t:
            print(f"未找到 issue {args.issue} 的用量记录")
            return
        print(f"\n{args.issue}  ${t['cost_usd']:.2f} / {_fmt_tokens(t['tokens'])} "
              f"（{t['sessions']} 次对话，{t['turns']} 轮）\n")
        for s in detail["sessions"]:
            tok = (s["input_tokens"] + s["output_tokens"]
                   + s["cache_creation_tokens"] + s["cache_read_tokens"])
            print(f"  {s['created_at']}  {s['skill'] or '-':28s} "
                  f"${s['cost_usd']:.3f}  {_fmt_tokens(tok):>7s}  "
                  f"{s['num_turns'] or 0}轮  {s['status']}")
        print("\n消耗结构：")
        bt = sum(detail["buckets"].values()) or 1
        for name, tokens in detail["buckets"].items():
            print(f"  {name:12s} {_fmt_tokens(tokens):>7s}  {tokens / bt * 100:.1f}%")
        return

    date_str = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    result = asyncio.run(generate_and_send(date_str, dry_run=args.dry_run))
    print(f"结果: {result}")


if __name__ == "__main__":
    main()
