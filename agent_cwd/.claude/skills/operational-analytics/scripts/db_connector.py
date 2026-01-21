"""Database connection management for PostgreSQL.

Provides async connection pooling using asyncpg with lazy initialization.
"""

import asyncpg
import asyncio
import os
from typing import Optional


class DBConnector:
    """Manage PostgreSQL database connections.

    Features:
    - Lazy connection pool initialization
    - Thread-safe pool management
    - Configuration from environment variables
    """

    def __init__(self):
        """Initialize connector with configuration from environment."""
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()

        # Load configuration from environment
        self.host = os.getenv('POSTGRES_HOST', '')
        self.port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.database = os.getenv('POSTGRES_DATABASE', '')
        self.user = os.getenv('POSTGRES_USER', '')
        self.password = os.getenv('POSTGRES_PASSWORD', '')
        self.query_timeout = int(os.getenv('POSTGRES_QUERY_TIMEOUT', '60'))

    async def get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool.

        Returns:
            asyncpg.Pool: Database connection pool

        Raises:
            ValueError: If configuration is missing
            Exception: If connection fails
        """
        if self._pool is not None:
            return self._pool

        async with self._lock:
            # Double-check after acquiring lock
            if self._pool is None:
                # Validate configuration
                if not all([self.host, self.database, self.user, self.password]):
                    raise ValueError(
                        "Missing database configuration. "
                        "Set POSTGRES_HOST, POSTGRES_DATABASE, POSTGRES_USER, POSTGRES_PASSWORD"
                    )

                self._pool = await asyncpg.create_pool(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    min_size=1,
                    max_size=5,
                    timeout=30,
                    command_timeout=self.query_timeout
                )

        return self._pool

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
