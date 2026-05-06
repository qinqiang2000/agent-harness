import pytest
from dotenv import load_dotenv
load_dotenv()
from api.db import get_faq_pool

@pytest.mark.asyncio
async def test_pool_connects():
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    assert result == 1
