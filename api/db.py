"""PostgreSQL connection pool for FAQ service."""
import os
import asyncpg

_faq_pool: asyncpg.Pool | None = None


async def get_faq_pool() -> asyncpg.Pool:
    global _faq_pool
    if _faq_pool is None:
        host = os.getenv("FAQ_POSTGRES_HOST")
        user = os.getenv("FAQ_POSTGRES_USER")
        if not host or not user:
            raise RuntimeError(
                "FAQ 数据库未配置，请在环境变量中设置 FAQ_POSTGRES_HOST 和 FAQ_POSTGRES_USER"
            )
        _faq_pool = await asyncpg.create_pool(
            host=host,
            port=int(os.getenv("FAQ_POSTGRES_PORT", "5432")),
            database=os.getenv("FAQ_POSTGRES_DATABASE", "postgres"),
            user=user,
            password=os.getenv("FAQ_POSTGRES_PASSWORD"),
            min_size=1,
            max_size=5,
        )
    return _faq_pool


async def close_faq_pool():
    global _faq_pool
    if _faq_pool:
        await _faq_pool.close()
        _faq_pool = None


async def init_faq_table():
    """Create faq_items table if not exists."""
    from pathlib import Path
    sql = (Path(__file__).parent / "faq_schema.sql").read_text()
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def init_interactions_table():
    """Create cs_interactions table if not exists."""
    from pathlib import Path
    sql = (Path(__file__).parent / "interactions_schema.sql").read_text()
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def init_skill_versions_table():
    """Create skill_versions and skill_version_files tables if not exists."""
    from pathlib import Path
    sql = (Path(__file__).parent / "skill_versions_schema.sql").read_text()
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def skill_get_published(skill_name: str) -> dict | None:
    """返回指定 skill 当前 published 版本的元数据，无则返回 None。"""
    pool = await get_faq_pool()
    row = await pool.fetchrow(
        "SELECT id, skill_name, version, status, operator, reason, created_at "
        "FROM skill_versions WHERE skill_name=$1 AND status='published'",
        skill_name,
    )
    return dict(row) if row else None


async def skill_get_version(version_id: int) -> dict | None:
    """返回指定版本元数据（内部用，按 id 查）。"""
    pool = await get_faq_pool()
    row = await pool.fetchrow(
        "SELECT id, skill_name, version, status, operator, reason, created_at "
        "FROM skill_versions WHERE id=$1",
        version_id,
    )
    return dict(row) if row else None


async def skill_get_version_by_key(skill_name: str, version_num: int) -> dict | None:
    """按 skill_name + version 整数查版本元数据（对外版本号解析后调用）。"""
    pool = await get_faq_pool()
    row = await pool.fetchrow(
        "SELECT id, skill_name, version, status, operator, reason, created_at "
        "FROM skill_versions WHERE skill_name=$1 AND version=$2",
        skill_name, version_num,
    )
    return dict(row) if row else None


async def skill_list_versions(skill_name: str) -> list[dict]:
    """返回指定 skill 的所有版本（按版本号降序）。"""
    pool = await get_faq_pool()
    rows = await pool.fetch(
        "SELECT id, skill_name, version, status, operator, reason, created_at "
        "FROM skill_versions WHERE skill_name=$1 ORDER BY version DESC",
        skill_name,
    )
    return [dict(r) for r in rows]


async def skill_list_drafts(skill_name: str) -> list[dict]:
    """返回指定 skill 的所有 draft 版本。"""
    pool = await get_faq_pool()
    rows = await pool.fetch(
        "SELECT id, skill_name, version, status, operator, reason, created_at "
        "FROM skill_versions WHERE skill_name=$1 AND status='draft' ORDER BY version DESC",
        skill_name,
    )
    return [dict(r) for r in rows]


async def skill_get_files(version_id: int) -> list[dict]:
    """返回指定版本的所有文件。"""
    pool = await get_faq_pool()
    rows = await pool.fetch(
        "SELECT id, version_id, filename, filepath, content "
        "FROM skill_version_files WHERE version_id=$1 ORDER BY filepath",
        version_id,
    )
    return [dict(r) for r in rows]


async def skill_next_version(skill_name: str) -> int:
    """返回下一个可用版本号。"""
    pool = await get_faq_pool()
    row = await pool.fetchrow(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM skill_versions WHERE skill_name=$1",
        skill_name,
    )
    return row["next"]


async def skill_create_version(
    skill_name: str,
    version: int,
    status: str,
    files: list[dict],
    operator: str | None = None,
    reason: str | None = None,
) -> int:
    """创建一条版本记录及其文件快照，返回新版本 id。"""
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            version_id = await conn.fetchval(
                "INSERT INTO skill_versions (skill_name, version, status, operator, reason) "
                "VALUES ($1,$2,$3,$4,$5) RETURNING id",
                skill_name, version, status, operator, reason,
            )
            await conn.executemany(
                "INSERT INTO skill_version_files (version_id, filename, filepath, content) "
                "VALUES ($1,$2,$3,$4)",
                [(version_id, f["filename"], f["filepath"], f["content"]) for f in files],
            )
    return version_id


async def skill_update_draft(
    version_id: int,
    files: list[dict],
    operator: str | None = None,
    reason: str | None = None,
) -> None:
    """更新 draft 版本的文件内容（upsert）及元数据。"""
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE skill_versions SET operator=$1, reason=$2 WHERE id=$3",
                operator, reason, version_id,
            )
            for f in files:
                await conn.execute(
                    """
                    INSERT INTO skill_version_files (version_id, filename, filepath, content)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (version_id, filepath) DO UPDATE
                        SET filename=EXCLUDED.filename, content=EXCLUDED.content
                    """,
                    version_id, f["filename"], f["filepath"], f["content"],
                )


async def skill_publish(skill_name: str, version_id: int) -> None:
    """将指定 draft 发布：旧 published → superseded，目标 draft → published。"""
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE skill_versions SET status='superseded' "
                "WHERE skill_name=$1 AND status='published'",
                skill_name,
            )
            await conn.execute(
                "UPDATE skill_versions SET status='published' WHERE id=$1",
                version_id,
            )


async def insert_interaction(record: dict) -> None:
    """Insert one row into cs_interactions. Silently skips if pool is unavailable."""
    try:
        pool = await get_faq_pool()
    except RuntimeError:
        return
    await pool.execute(
        """
        INSERT INTO cs_interactions
            (session_id, question, answer, skill, tenant_id, status,
             num_turns, duration_ms, cited_urls, skills_used, transferred)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        record.get("session_id", ""),
        record.get("question"),
        record.get("answer"),
        record.get("skill"),
        record.get("tenant_id"),
        record.get("status"),
        record.get("num_turns"),
        record.get("duration_ms"),
        record.get("cited_urls") or [],
        record.get("skills_used") or [],
        record.get("transferred", False),
    )
