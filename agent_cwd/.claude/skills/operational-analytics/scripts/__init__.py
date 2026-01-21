"""Operational analytics scripts for SQL query execution.

This package provides:
- DBConnector: Database connection management
- QueryExecutor: SQL validation and execution
- ResultFormatter: Output formatting for Markdown
"""

from .db_connector import DBConnector
from .query_executor import QueryExecutor
from .result_formatter import ResultFormatter

__all__ = ['DBConnector', 'QueryExecutor', 'ResultFormatter']
