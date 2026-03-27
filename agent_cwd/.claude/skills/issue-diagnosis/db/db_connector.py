"""多数据源连接池管理器（aiomysql / asyncpg）。

支持 MySQL 和 PostgreSQL，每次脚本调用独立创建和关闭连接池。
"""

import json
import os
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).parent / "db_config.json"


def load_config(name: str) -> dict:
    """从 db_config.json 读取指定数据源配置。

    Args:
        name: 数据源名称

    Returns:
        数据源配置字典

    Raises:
        ValueError: 数据源不存在
        FileNotFoundError: 配置文件不存在
    """
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    for ds in config.get("datasources", []):
        if ds["name"] == name:
            return ds

    available = [ds["name"] for ds in config.get("datasources", [])]
    raise ValueError(
        f"数据源 '{name}' 不存在，可用数据源：{', '.join(available)}"
    )


def list_sources() -> list[dict]:
    """列出所有数据源（不含密码）。"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    result = []
    for ds in config.get("datasources", []):
        result.append({
            "name": ds["name"],
            "type": ds["type"],
            "host": ds["host"],
            "port": ds.get("port"),
            "database": ds["database"],
        })
    return result


class DbConnector:
    """多数据源连接池管理器（aiomysql / asyncpg）。"""

    def __init__(self):
        self._pool = None
        self._type: str = ""
        self._config: dict = {}

    async def init(self, source_config: dict) -> None:
        """根据数据源配置初始化连接池。

        Args:
            source_config: 来自 db_config.json 的数据源配置字典
        """
        self._type = source_config["type"].lower()
        self._config = source_config

        if self._type == "mysql":
            import aiomysql
            self._pool = await aiomysql.create_pool(
                host=source_config["host"],
                port=source_config.get("port", 3306),
                db=source_config["database"],
                user=source_config["user"],
                password=source_config["password"],
                minsize=source_config.get("pool_min", 1),
                maxsize=source_config.get("pool_max", 3),
                connect_timeout=source_config.get("timeout", 30),
                autocommit=True,
                charset="utf8mb4",
            )
        elif self._type in ("postgresql", "postgres"):
            import asyncpg
            self._pool = await asyncpg.create_pool(
                host=source_config["host"],
                port=source_config.get("port", 5432),
                database=source_config["database"],
                user=source_config["user"],
                password=source_config["password"],
                min_size=source_config.get("pool_min", 1),
                max_size=source_config.get("pool_max", 3),
                timeout=source_config.get("timeout", 30),
                command_timeout=source_config.get("timeout", 30),
            )
        else:
            raise ValueError(f"不支持的数据库类型：{self._type}，支持 mysql / postgresql")

    async def execute(self, sql: str, timeout: int = 30) -> list[dict]:
        """执行 SQL 并返回结果列表。

        Args:
            sql: 已通过安全校验的 SELECT 语句
            timeout: 查询超时（秒）

        Returns:
            [{col: val}, ...] 格式的行列表
        """
        if self._pool is None:
            raise RuntimeError("连接池未初始化，请先调用 init()")

        if self._type == "mysql":
            import aiomysql
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql)
                    rows = await cur.fetchall()
                    return [dict(row) for row in rows]

        elif self._type in ("postgresql", "postgres"):
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, timeout=timeout)
                return [dict(row) for row in rows]

        raise RuntimeError(f"未知数据库类型：{self._type}")

    async def describe_table(self, table_name: str) -> list[dict]:
        """查询表结构（字段名、类型、可空、注释）。

        Args:
            table_name: 表名

        Returns:
            字段信息列表
        """
        if self._pool is None:
            raise RuntimeError("连接池未初始化，请先调用 init()")

        if self._type == "mysql":
            import aiomysql
            sql = (
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT "
                "FROM information_schema.COLUMNS "
                f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}' "
                "ORDER BY ORDINAL_POSITION"
            )
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql)
                    rows = await cur.fetchall()
                    return [dict(row) for row in rows]

        elif self._type in ("postgresql", "postgres"):
            sql = (
                "SELECT column_name, data_type, is_nullable, "
                "col_description(c.oid, a.attnum) AS column_comment "
                "FROM information_schema.columns ic "
                "JOIN pg_class c ON c.relname = ic.table_name "
                "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = ic.column_name "
                f"WHERE ic.table_name = '{table_name}' "
                "ORDER BY ordinal_position"
            )
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql)
                return [dict(row) for row in rows]

        raise RuntimeError(f"未知数据库类型：{self._type}")

    async def close(self) -> None:
        """关闭连接池。"""
        if self._pool is not None:
            self._pool.close()
            if self._type in ("postgresql", "postgres"):
                import asyncpg
                await self._pool.wait_closed() if hasattr(self._pool, "wait_closed") else None
            self._pool = None
