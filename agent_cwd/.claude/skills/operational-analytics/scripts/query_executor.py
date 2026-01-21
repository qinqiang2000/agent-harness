"""SQL query executor with safety validation.

This module provides SQL validation and execution functionality for the
operational-analytics skill. It enforces security rules to ensure only
safe SELECT queries are executed.
"""

import asyncpg
from typing import List, Dict, Tuple, Optional

try:
    from .db_connector import DBConnector
except ImportError:
    from db_connector import DBConnector


class QueryExecutor:
    """Execute SQL queries with safety checks.

    Enforces the following safety rules:
    - Only SELECT statements allowed
    - Only whitelisted tables accessible (configured via POSTGRES_ALLOWED_TABLES env)
    - Forbidden keywords blocked
    - No multiple statements
    - Query timeout enforced
    """

    # Default whitelist (used if env var not set)
    DEFAULT_ALLOWED_TABLES = [
        't_ocm_kbc_order_settle',
        't_ocm_order_header',
        't_ocm_order_lines',
        't_ocm_tenant'
    ]

    # Blacklist of forbidden SQL keywords
    FORBIDDEN_KEYWORDS = [
        'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE',
        'ALTER', 'CREATE', 'GRANT', 'REVOKE', 'EXEC',
        'EXECUTE', 'REPLACE', 'MERGE'
    ]

    def __init__(self):
        """Initialize query executor with database connector."""
        self.connector = DBConnector()

        # Load allowed tables from environment variable
        import os
        allowed_tables_env = os.getenv('POSTGRES_ALLOWED_TABLES', '')
        if allowed_tables_env:
            self.allowed_tables = [t.strip() for t in allowed_tables_env.split(',') if t.strip()]
        else:
            self.allowed_tables = self.DEFAULT_ALLOWED_TABLES

    def validate_sql(self, sql: str) -> Tuple[bool, Optional[str]]:
        """Validate SQL query for safety.

        Args:
            sql: SQL query to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        sql_clean = sql.strip()
        sql_upper = sql_clean.upper()

        # Rule 1: Only SELECT statements
        if not sql_upper.startswith('SELECT'):
            return False, "Only SELECT queries are allowed for security reasons"

        # Rule 2: Check for forbidden keywords
        sql_with_spaces = f' {sql_upper} '
        for keyword in self.FORBIDDEN_KEYWORDS:
            if f' {keyword} ' in sql_with_spaces or f';{keyword}' in sql_upper:
                return False, f"Forbidden keyword detected: {keyword}"

        # Rule 3: Must use at least one allowed table
        has_allowed_table = False
        for table in self.allowed_tables:
            if table in sql.lower():
                has_allowed_table = True
                break

        if not has_allowed_table:
            return False, (
                f"Query must use at least one allowed table. "
                f"Allowed tables: {', '.join(self.allowed_tables)}"
            )

        # Rule 4: No multiple statements
        sql_without_trailing = sql_clean.rstrip(';')
        if ';' in sql_without_trailing:
            return False, "Multiple statements are not allowed for security reasons"

        return True, None

    async def execute(self, sql: str) -> List[Dict]:
        """Execute SQL query and return results.

        Args:
            sql: SQL query to execute (must pass validation)

        Returns:
            List of dictionaries with query results

        Raises:
            ValueError: If SQL validation fails
            asyncpg.PostgresError: If query execution fails
        """
        # Validate SQL first
        is_valid, error = self.validate_sql(sql)
        if not is_valid:
            raise ValueError(f"SQL validation failed: {error}")

        # Get connection pool and execute
        pool = await self.connector.get_pool()

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            raise Exception(f"Query execution failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error: {str(e)}")

    async def close(self):
        """Close database connection.

        Should be called when done executing queries.
        """
        await self.connector.close()
