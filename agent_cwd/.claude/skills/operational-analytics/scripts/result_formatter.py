"""Result formatting utilities for query output.

Provides formatting for Markdown tables and error messages.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date


class ResultFormatter:
    """Format query results for display.

    Supports:
    - Markdown table formatting
    - Error message formatting
    - Value type conversion for display
    """

    def __init__(self, max_column_width: int = 50):
        """Initialize formatter.

        Args:
            max_column_width: Maximum width for column values (truncate longer values)
        """
        self.max_column_width = max_column_width

    def to_markdown_table(self, results: List[Dict[str, Any]]) -> str:
        """Convert query results to Markdown table.

        Args:
            results: List of dictionaries from query execution

        Returns:
            Formatted Markdown table string
        """
        if not results:
            return "查询结果为空（0条记录）"

        # Get headers from first row
        headers = list(results[0].keys())

        # Build header row
        header_row = "| " + " | ".join(str(h) for h in headers) + " |"

        # Build separator row
        separator_row = "|" + "|".join(["---"] * len(headers)) + "|"

        # Build data rows
        data_rows = []
        for row in results:
            values = []
            for h in headers:
                value = self._format_value(row.get(h, ''))
                values.append(value)
            data_rows.append("| " + " | ".join(values) + " |")

        # Combine all parts
        table = "\n".join([header_row, separator_row] + data_rows)
        table += f"\n\n（共 {len(results)} 条记录）"

        return table

    def _format_value(self, value: Any) -> str:
        """Format a single value for display.

        Args:
            value: Value to format

        Returns:
            Formatted string value
        """
        if value is None:
            return ""

        # Handle datetime objects
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")

        # Convert to string
        str_value = str(value)

        # Truncate if too long
        if len(str_value) > self.max_column_width:
            str_value = str_value[:self.max_column_width - 3] + "..."

        # Escape pipe characters for Markdown
        str_value = str_value.replace("|", "\\|")

        # Replace newlines
        str_value = str_value.replace("\n", " ")

        return str_value

    def format_error(self, error: Exception) -> str:
        """Format an error message for display.

        Args:
            error: Exception to format

        Returns:
            Formatted error message
        """
        error_type = type(error).__name__
        error_msg = str(error)

        return f"❌ **查询执行失败**\n\n**错误类型**: {error_type}\n**错误信息**: {error_msg}"

    def format_summary(
        self,
        results: List[Dict[str, Any]],
        query_time_ms: Optional[float] = None
    ) -> str:
        """Generate a summary of query results.

        Args:
            results: Query results
            query_time_ms: Query execution time in milliseconds

        Returns:
            Summary string
        """
        summary_parts = [f"返回 {len(results)} 条记录"]

        if query_time_ms is not None:
            summary_parts.append(f"耗时 {query_time_ms:.2f}ms")

        return " | ".join(summary_parts)
