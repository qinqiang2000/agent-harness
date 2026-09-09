"""
Token 用量存储与归因聚合。

数据落 SQLite（默认 data/token_usage.db），三张表：
  - session_usage      一行 = 一次 process_query 请求（永久保留，量小）
  - tool_volume        一行 = 一次工具返回，记录内容体积与轮次（归因用，默认保留 14 天）
  - issue_sessions     issue identifier ↔ session 映射，解决"一个 issue 多次对话"的聚合
  - channel_issue_map  渠道会话 ↔ issue 绑定，让后续轮次归到同一 issue

数据库路径优先级：
  1. 环境变量 TOKEN_USAGE_DATA_DIR
  2. 环境变量 AGENT_DATA_DIR
  3. 项目根目录 data/
"""

import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 单价表（美元 / 每 100 万 token）。走 litellm 代理时 SDK 的 total_cost_usd
# 可能为 None 或按错误的模型定价，因此始终自算一份作为兜底与交叉验证。
# 可用环境变量 TOKEN_PRICE_INPUT / OUTPUT / CACHE_WRITE / CACHE_READ 覆盖。
_DEFAULT_PRICES = {
    "input": 3.0,
    "output": 15.0,
    "cache_write": 3.75,
    "cache_read": 0.30,
}

# 工具名 → 归因桶。用于把上下文增量归到"是什么内容撑大了 context"。
_TOOL_BUCKETS = [
    ("mcp__elastic", "ELK日志"),
    ("mcp__gitlab", "GitLab"),
    ("Task", "子agent"),
    ("Read", "源码读取"),
    ("Glob", "源码读取"),
    ("Grep", "源码读取"),
    ("Skill", "skill加载"),
    ("Bash", "命令执行"),
    ("WebFetch", "网络检索"),
    ("WebSearch", "网络检索"),
    ("Write", "文件写入"),
    ("Edit", "文件写入"),
    ("TodoWrite", "其他"),
    ("AskUserQuestion", "其他"),
]

RETENTION_DAYS_TURNS = int(os.getenv("TOKEN_USAGE_TURN_RETENTION_DAYS", "14"))


def bucket_of(tool_name: str) -> str:
    """把工具名归一化成归因桶名称。

    Args:
        tool_name: SDK 上报的工具名，如 Read / mcp__elastic__search / Task

    Returns:
        归因桶名称，未匹配到时返回"其他"
    """
    for prefix, bucket in _TOOL_BUCKETS:
        if tool_name.startswith(prefix):
            return bucket
    return "其他"


def _prices() -> Dict[str, float]:
    """读取当前生效的单价表，环境变量可逐项覆盖默认值。

    Returns:
        含 input / output / cache_write / cache_read 四个键的单价字典（美元每百万 token）
    """
    env_map = {
        "input": "TOKEN_PRICE_INPUT",
        "output": "TOKEN_PRICE_OUTPUT",
        "cache_write": "TOKEN_PRICE_CACHE_WRITE",
        "cache_read": "TOKEN_PRICE_CACHE_READ",
    }
    out = dict(_DEFAULT_PRICES)
    for key, env in env_map.items():
        raw = os.getenv(env)
        if raw:
            try:
                out[key] = float(raw)
            except ValueError:
                logger.warning("[TokenUsage] %s 不是合法数字，忽略：%r", env, raw)
    return out


def calc_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
) -> float:
    """按单价表自算成本，用于 SDK 未返回 total_cost_usd 时兜底。

    Args:
        input_tokens: 非缓存输入 token 数
        output_tokens: 输出 token 数
        cache_creation_tokens: 缓存写入 token 数
        cache_read_tokens: 缓存命中读取 token 数

    Returns:
        估算成本（美元）
    """
    p = _prices()
    return round(
        input_tokens / 1e6 * p["input"]
        + output_tokens / 1e6 * p["output"]
        + cache_creation_tokens / 1e6 * p["cache_write"]
        + cache_read_tokens / 1e6 * p["cache_read"],
        6,
    )


def _chars_per_token() -> float:
    """工具返回内容的字符数换算 token 的系数。

    中文文本约 1.5 字符/token，英文与代码约 3.5，日志与源码混合场景取 3.0。
    可用环境变量 TOKEN_CHARS_PER_TOKEN 覆盖以校准。

    Returns:
        每 token 对应的字符数，最小 0.5 防止除零
    """
    try:
        return max(float(os.getenv("TOKEN_CHARS_PER_TOKEN", "3.0")), 0.5)
    except ValueError:
        return 3.0


def _db_path() -> Path:
    """确定数据库文件路径。

    Returns:
        token_usage.db 的绝对路径
    """
    data_dir = os.environ.get("TOKEN_USAGE_DATA_DIR") or os.environ.get(
        "AGENT_DATA_DIR"
    )
    if data_dir:
        return Path(data_dir) / "token_usage.db"
    return Path(__file__).resolve().parents[2] / "data" / "token_usage.db"


def _connect() -> sqlite3.Connection:
    """建立连接并初始化表结构与索引。

    Returns:
        已初始化的 SQLite 连接
    """
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_usage (
            request_id            TEXT PRIMARY KEY,
            session_id            TEXT,
            issue_key             TEXT,
            issue_id              TEXT,
            skill                 TEXT,
            tenant_id             TEXT,
            channel               TEXT,
            model                 TEXT,
            input_tokens          INTEGER NOT NULL DEFAULT 0,
            output_tokens         INTEGER NOT NULL DEFAULT 0,
            cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
            cost_usd              REAL    NOT NULL DEFAULT 0,
            cost_sdk_usd          REAL,
            num_turns             INTEGER,
            total_turns           INTEGER NOT NULL DEFAULT 0,
            duration_ms           INTEGER,
            status                TEXT,
            created_at            TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_session_usage_issue
            ON session_usage(issue_key);
        CREATE INDEX IF NOT EXISTS idx_session_usage_created
            ON session_usage(created_at);

        CREATE TABLE IF NOT EXISTS tool_volume (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id    TEXT NOT NULL,
            tool_name     TEXT NOT NULL,
            bucket        TEXT NOT NULL,
            target        TEXT,
            result_chars  INTEGER NOT NULL DEFAULT 0,
            call_count    INTEGER NOT NULL DEFAULT 1,
            turn_idx      INTEGER NOT NULL DEFAULT 0,
            is_subagent   INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_tool_volume_request
            ON tool_volume(request_id);
        CREATE INDEX IF NOT EXISTS idx_tool_volume_created
            ON tool_volume(created_at);

        CREATE TABLE IF NOT EXISTS channel_issue_map (
            channel              TEXT NOT NULL,
            external_session_id  TEXT NOT NULL,
            issue_key            TEXT NOT NULL,
            issue_id             TEXT,
            created_at           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (channel, external_session_id)
        );

        CREATE TABLE IF NOT EXISTS issue_sessions (
            issue_key   TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            issue_id    TEXT,
            skill       TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (issue_key, session_id)
        );
    """)
    conn.commit()
    return conn


def new_request_id() -> str:
    """生成一次请求的唯一标识，用于串联 session/turn/tool 三张表。

    Returns:
        32 位十六进制字符串
    """
    return uuid.uuid4().hex


def record_session(
    request_id: str,
    session_id: Optional[str],
    issue_key: Optional[str],
    issue_id: Optional[str],
    skill: Optional[str],
    tenant_id: Optional[str],
    channel: Optional[str],
    model: Optional[str],
    usage: Optional[Dict[str, Any]],
    cost_sdk_usd: Optional[float],
    num_turns: Optional[int],
    total_turns: int,
    duration_ms: Optional[int],
    status: str,
) -> None:
    """写入一次请求的 session 级用量汇总，并顺带登记 issue ↔ session 映射。

    Args:
        request_id: 本次请求唯一标识
        session_id: SDK 返回的真实 session_id
        issue_key: Linear issue identifier，如 CNPRD-1276；无 issue 场景为 None
        issue_id: Linear issue UUID，identifier 被改名时的兜底
        skill: 使用的 skill 名
        tenant_id: 租户 ID
        channel: 来源渠道，如 linear / yunzhijia / api
        model: 主模型名
        usage: SDK ResultMessage.usage 原始字典
        cost_sdk_usd: SDK 返回的 total_cost_usd，可能为 None
        num_turns: SDK 上报的请求轮次
        total_turns: 实际观测到的主 agent 轮次，归因加权时用于估算内容被重放次数
        duration_ms: 本次请求耗时
        status: success / error / interrupted

    Returns:
        None。写库失败只记日志，绝不影响主流程。
    """
    u = usage or {}
    inp = int(u.get("input_tokens") or 0)
    out = int(u.get("output_tokens") or 0)
    cw = int(u.get("cache_creation_input_tokens") or 0)
    cr = int(u.get("cache_read_input_tokens") or 0)
    cost = calc_cost(inp, out, cw, cr)

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO session_usage (
                    request_id, session_id, issue_key, issue_id, skill, tenant_id,
                    channel, model, input_tokens, output_tokens,
                    cache_creation_tokens, cache_read_tokens,
                    cost_usd, cost_sdk_usd, num_turns, total_turns,
                    duration_ms, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    request_id, session_id, issue_key, issue_id, skill, tenant_id,
                    channel, model, inp, out, cw, cr,
                    cost, cost_sdk_usd, num_turns, total_turns,
                    duration_ms, status,
                ),
            )
            if issue_key and session_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO issue_sessions
                        (issue_key, session_id, issue_id, skill)
                    VALUES (?,?,?,?)
                    """,
                    (issue_key, session_id, issue_id, skill),
                )
    except Exception:
        logger.exception("[TokenUsage] record_session 写库失败 request_id=%s", request_id)


def record_tool_volume(request_id: str, items: List[Dict[str, Any]]) -> None:
    """批量写入工具返回内容体积，用于体积归因（口径 B）。

    Args:
        request_id: 本次请求唯一标识
        items: 每项含 tool_name / target / result_chars / turn_idx / is_subagent

    Returns:
        None。写库失败只记日志。
    """
    if not items:
        return
    try:
        with _connect() as conn:
            conn.executemany(
                """
                INSERT INTO tool_volume
                    (request_id, tool_name, bucket, target, result_chars,
                     call_count, turn_idx, is_subagent)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        request_id,
                        it.get("tool_name", "unknown"),
                        bucket_of(it.get("tool_name", "")),
                        it.get("target"),
                        it.get("result_chars", 0),
                        it.get("call_count", 1),
                        it.get("turn_idx", 0),
                        1 if it.get("is_subagent") else 0,
                    )
                    for it in items
                ],
            )
    except Exception:
        logger.exception("[TokenUsage] record_tool_volume 写库失败 request_id=%s", request_id)


def purge_old_turns(days: int = RETENTION_DAYS_TURNS) -> int:
    """清理超期的工具体积明细，session 级汇总永久保留。

    Args:
        days: 保留天数，默认取环境变量 TOKEN_USAGE_TURN_RETENTION_DAYS

    Returns:
        被删除的明细行数
    """
    try:
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM tool_volume WHERE created_at < datetime('now','localtime',?)",
                (f"-{days} days",),
            )
            deleted = cur.rowcount or 0
        return deleted
    except Exception:
        logger.exception("[TokenUsage] purge_old_turns 失败")
        return 0


def _fmt_tokens(n: int) -> str:
    """把 token 数格式化为易读字符串（K / M）。

    Args:
        n: token 数量

    Returns:
        如 1.84M / 520K / 831
    """
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def summarize_day(date_str: str) -> Dict[str, Any]:
    """聚合某一天的 token 用量，供日报与报表接口使用。

    Args:
        date_str: 日期，格式 YYYYMMDD

    Returns:
        字典，含：
          totals       当天总 token / 各类 token / 成本 / 请求数
          by_issue     按 issue_key 聚合并按成本降序的列表（无 issue 归入 _adhoc）
          by_skill     按 skill 聚合的列表
          buckets      口径 A 增量归因，桶名 → token 数
          top_tools    口径 B 体积归因，工具返回内容最大的 target 排行
    """
    day = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    like = f"{day}%"
    empty = {
        "date": day,
        "totals": {},
        "by_issue": [],
        "by_skill": [],
        "buckets": {},
        "top_tools": [],
    }
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS requests,
                       COALESCE(SUM(input_tokens),0)          AS input_tokens,
                       COALESCE(SUM(output_tokens),0)         AS output_tokens,
                       COALESCE(SUM(cache_creation_tokens),0) AS cache_creation_tokens,
                       COALESCE(SUM(cache_read_tokens),0)     AS cache_read_tokens,
                       COALESCE(SUM(cost_usd),0)              AS cost_usd,
                       COALESCE(SUM(cost_sdk_usd),0)          AS cost_sdk_usd
                FROM session_usage WHERE created_at LIKE ?
                """,
                (like,),
            ).fetchone()
            totals = dict(row) if row else {}
            if not totals.get("requests"):
                return empty
            totals["total_tokens"] = (
                totals["input_tokens"]
                + totals["output_tokens"]
                + totals["cache_creation_tokens"]
                + totals["cache_read_tokens"]
            )

            by_issue = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT COALESCE(NULLIF(issue_key,''), '_adhoc') AS issue_key,
                           COUNT(*) AS sessions,
                           SUM(input_tokens + output_tokens
                               + cache_creation_tokens + cache_read_tokens) AS tokens,
                           SUM(cost_usd)  AS cost_usd,
                           SUM(num_turns) AS turns,
                           GROUP_CONCAT(DISTINCT skill) AS skills
                    FROM session_usage WHERE created_at LIKE ?
                    GROUP BY 1 ORDER BY cost_usd DESC
                    """,
                    (like,),
                ).fetchall()
            ]

            by_skill = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT COALESCE(NULLIF(skill,''), '(无)') AS skill,
                           COUNT(*) AS sessions,
                           SUM(input_tokens + output_tokens
                               + cache_creation_tokens + cache_read_tokens) AS tokens,
                           SUM(cost_usd) AS cost_usd
                    FROM session_usage WHERE created_at LIKE ?
                    GROUP BY 1 ORDER BY cost_usd DESC
                    """,
                    (like,),
                ).fetchall()
            ]

            attr_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT v.bucket, v.result_chars, v.turn_idx, v.is_subagent,
                           s.total_turns
                    FROM tool_volume v
                    JOIN session_usage s ON s.request_id = v.request_id
                    WHERE v.created_at LIKE ?
                    """,
                    (like,),
                ).fetchall()
            ]

            top_tools = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT bucket, tool_name, target,
                           SUM(result_chars) AS chars,
                           SUM(call_count)   AS calls
                    FROM tool_volume WHERE created_at LIKE ?
                    GROUP BY bucket, tool_name, target
                    ORDER BY chars DESC LIMIT 15
                    """,
                    (like,),
                ).fetchall()
            ]
    except Exception:
        logger.exception("[TokenUsage] summarize_day 失败 date=%s", date_str)
        return empty

    return {
        "date": day,
        "totals": totals,
        "by_issue": by_issue,
        "by_skill": by_skill,
        "buckets": attribute_buckets(
            attr_rows,
            totals["input_tokens"]
            + totals["cache_creation_tokens"]
            + totals["cache_read_tokens"],
            totals["output_tokens"],
        ),
        "top_tools": top_tools,
    }


def attribute_buckets(
    tool_rows: List[Dict[str, Any]],
    input_tokens_total: int,
    output_tokens_total: int,
) -> Dict[str, int]:
    """归因：把真实计费的 input token 分摊到"是什么内容占用的"。

    算法（按轮次加权的体积归因）：
      SDK 在流式模式下不填充 AssistantMessage.usage（实测恒为 0），拿不到逐轮
      token，因此不能用相邻轮次的 input 增量做归因。改用可观测的工具返回体积：
        1. 每次工具返回的字符数按 TOKEN_CHARS_PER_TOKEN 估成 token 数 t
        2. 上下文是累积重放的——第 k 轮产生的内容，会在其后每一轮的 input 里
           重复计费，故权重 w = t × (总轮数 - k)
        3. 各 bucket 按 w 占比，去分摊 ResultMessage 上报的真实 input 总量
      工具无法解释的残差归入"系统底座"（system prompt + skill 定义 + 工具
      定义 + 用户 prompt，它从第 0 轮起每轮都被重放）。

    这样占比是估算的，但**总量恒等于真实计费 token**，不会出现凭空多算。

    已知盲区：子 agent（Task）内部消耗计入总量，但其内部读了什么无法从主
    上下文观测到，只能整体归入"子agent"桶。

    Args:
        tool_rows: tool_volume 行列表，需含 bucket / result_chars / turn_idx /
            is_subagent / total_turns（该次请求的总轮数）
        input_tokens_total: 真实计费的输入 token 总量
            （input + cache_creation + cache_read）
        output_tokens_total: 真实输出 token 总量

    Returns:
        桶名 → token 数的字典，按 token 数降序；各桶之和等于输入+输出总量
    """
    weights: Dict[str, float] = {}
    for r in tool_rows:
        chars = int(r.get("result_chars") or 0)
        if chars <= 0:
            continue
        total_turns = max(int(r.get("total_turns") or 1), 1)
        turn_idx = min(max(int(r.get("turn_idx") or 0), 0), total_turns - 1)
        # 该内容进入上下文后，被后续每一轮重放计费
        replays = total_turns - turn_idx
        tokens = chars / _chars_per_token()
        bucket = r.get("bucket") or "其他"
        weights[bucket] = weights.get(bucket, 0.0) + tokens * replays

    buckets: Dict[str, int] = {}
    weight_sum = sum(weights.values())

    if input_tokens_total > 0:
        if weight_sum <= 0:
            # 没有任何工具调用，输入全部是底座
            buckets["系统底座"] = input_tokens_total
        elif weight_sum >= input_tokens_total:
            # 估算超过真实总量（字符→token 系数偏差），按比例压缩，
            # 并给底座保留一个下限，避免底座显示为 0
            scale = input_tokens_total * 0.9 / weight_sum
            for name, w in weights.items():
                buckets[name] = int(w * scale)
            buckets["系统底座"] = input_tokens_total - sum(buckets.values())
        else:
            for name, w in weights.items():
                buckets[name] = int(w)
            buckets["系统底座"] = input_tokens_total - sum(buckets.values())

    if output_tokens_total > 0:
        buckets["模型输出"] = output_tokens_total

    return dict(
        sorted(
            ((k, v) for k, v in buckets.items() if v > 0),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )


def issue_detail(issue_key: str) -> Dict[str, Any]:
    """查询单个 issue 跨多次对话的完整用量明细。

    Args:
        issue_key: Linear issue identifier，如 CNPRD-1276

    Returns:
        字典，含 issue_key / sessions（每次对话一行）/ totals（累计）/ buckets（归因）
    """
    empty = {"issue_key": issue_key, "sessions": [], "totals": {}, "buckets": {}}
    try:
        with _connect() as conn:
            sessions = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT request_id, session_id, skill, status, num_turns,
                           input_tokens, output_tokens, cache_creation_tokens,
                           cache_read_tokens, cost_usd, duration_ms, created_at
                    FROM session_usage WHERE issue_key = ?
                    ORDER BY created_at
                    """,
                    (issue_key,),
                ).fetchall()
            ]
            if not sessions:
                return empty
            attr_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT v.bucket, v.result_chars, v.turn_idx, v.is_subagent,
                           s.total_turns
                    FROM tool_volume v
                    JOIN session_usage s ON s.request_id = v.request_id
                    WHERE s.issue_key = ?
                    """,
                    (issue_key,),
                ).fetchall()
            ]
    except Exception:
        logger.exception("[TokenUsage] issue_detail 失败 issue=%s", issue_key)
        return empty

    totals = {
        "sessions": len(sessions),
        "tokens": sum(
            s["input_tokens"] + s["output_tokens"]
            + s["cache_creation_tokens"] + s["cache_read_tokens"]
            for s in sessions
        ),
        "cost_usd": round(sum(s["cost_usd"] for s in sessions), 4),
        "turns": sum(s["num_turns"] or 0 for s in sessions),
    }
    return {
        "issue_key": issue_key,
        "sessions": sessions,
        "totals": totals,
        "buckets": attribute_buckets(
            attr_rows,
            sum(
                s["input_tokens"] + s["cache_creation_tokens"] + s["cache_read_tokens"]
                for s in sessions
            ),
            sum(s["output_tokens"] for s in sessions),
        ),
    }


def bind_channel_issue(
    channel: str,
    external_session_id: str,
    issue_key: str,
    issue_id: Optional[str] = None,
) -> None:
    """登记渠道会话与 issue 的绑定关系，供后续轮次反查 issue。

    Linear 的 prompted / code-fix 事件只带 AgentSession ID，拿不到 issue
    identifier，靠这张表把后续每一轮都归到同一个 issue 上；持久化到 SQLite
    是为了服务重启后归因不断档。

    Args:
        channel: 渠道标识，如 linear
        external_session_id: 渠道侧会话 ID（Linear 为 AgentSession ID）
        issue_key: issue identifier，如 CNPRD-1276
        issue_id: issue UUID，identifier 被改名时的兜底

    Returns:
        None。写库失败只记日志。
    """
    if not issue_key or not external_session_id:
        return
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO channel_issue_map
                    (channel, external_session_id, issue_key, issue_id)
                VALUES (?,?,?,?)
                """,
                (channel, external_session_id, issue_key, issue_id),
            )
    except Exception:
        logger.exception(
            "[TokenUsage] bind_channel_issue 失败 channel=%s session=%s",
            channel, external_session_id,
        )


def lookup_channel_issue(channel: str, external_session_id: str) -> Dict[str, Any]:
    """反查渠道会话绑定的 issue。

    Args:
        channel: 渠道标识，如 linear
        external_session_id: 渠道侧会话 ID

    Returns:
        含 issue_key / issue_id 的字典；未绑定时两个值均为 None
    """
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT issue_key, issue_id FROM channel_issue_map
                WHERE channel = ? AND external_session_id = ?
                """,
                (channel, external_session_id),
            ).fetchone()
        if row:
            return {"issue_key": row["issue_key"], "issue_id": row["issue_id"]}
    except Exception:
        logger.exception(
            "[TokenUsage] lookup_channel_issue 失败 channel=%s session=%s",
            channel, external_session_id,
        )
    return {"issue_key": None, "issue_id": None}
