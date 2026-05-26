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
