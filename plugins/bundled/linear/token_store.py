"""SQLite-backed Linear OAuth token 存储。"""

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_REFRESH_BUFFER_SECONDS = 300  # 过期前 5 分钟触发刷新
_GRACE_PERIOD_SECONDS = 1800  # 刷新失败宽限期 30 分钟


class TokenStore:
    """管理 Linear OAuth token 的 SQLite 存储。

    单 workspace 场景下只有一行记录，按 workspace_id 主键查询。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """返回自动提交/回滚的 SQLite 连接。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """初始化数据库表结构。"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS linear_installations (
                    workspace_id   TEXT PRIMARY KEY,
                    workspace_name TEXT,
                    app_user_id    TEXT,
                    access_token   TEXT NOT NULL,
                    refresh_token  TEXT,
                    expires_at     INTEGER,
                    scopes         TEXT,
                    created_at     INTEGER NOT NULL,
                    updated_at     INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS linear_session_map (
                    issue_id         TEXT PRIMARY KEY,
                    claude_session_id TEXT NOT NULL,
                    updated_at       INTEGER NOT NULL
                )
            """)

    def save_installation(
        self,
        workspace_id: str,
        workspace_name: str,
        app_user_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: Optional[int],
        scopes: Optional[str],
    ) -> None:
        """保存或更新 workspace 安装信息。

        Args:
            workspace_id: Linear workspace ID
            workspace_name: workspace 名称
            app_user_id: App bot 用户 ID
            access_token: OAuth access token
            refresh_token: OAuth refresh token（可选）
            expires_in: token 有效期（秒，可选）
            scopes: 授权范围字符串
        """
        now = int(time.time())
        expires_at = now + expires_in if expires_in else None
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO linear_installations
                    (workspace_id, workspace_name, app_user_id, access_token,
                     refresh_token, expires_at, scopes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    workspace_name = excluded.workspace_name,
                    app_user_id    = excluded.app_user_id,
                    access_token   = excluded.access_token,
                    refresh_token  = excluded.refresh_token,
                    expires_at     = excluded.expires_at,
                    scopes         = excluded.scopes,
                    updated_at     = excluded.updated_at
            """,
                (
                    workspace_id,
                    workspace_name,
                    app_user_id,
                    access_token,
                    refresh_token,
                    expires_at,
                    scopes,
                    now,
                    now,
                ),
            )
        logger.info(
            f"[Linear] Installation saved: workspace={workspace_id}, user={app_user_id}"
        )

    def get_installation(self, workspace_id: str) -> Optional[sqlite3.Row]:
        """按 workspace_id 查询安装记录。

        Args:
            workspace_id: Linear workspace ID

        Returns:
            sqlite3.Row 或 None
        """
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM linear_installations WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()

    def get_token(self, workspace_id: str) -> Optional[str]:
        """返回有效 access_token，临近过期时自动刷新。

        Args:
            workspace_id: Linear workspace ID

        Returns:
            有效的 access_token，或 None（已过期且刷新失败）
        """
        row = self.get_installation(workspace_id)
        if not row:
            return None

        now = int(time.time())
        expires_at = row["expires_at"]

        if expires_at is None or (expires_at - now) > _REFRESH_BUFFER_SECONDS:
            return row["access_token"]

        if row["refresh_token"]:
            new_token = self._do_refresh(workspace_id, row["refresh_token"])
            if new_token:
                return new_token

        if expires_at and (now - expires_at) < _GRACE_PERIOD_SECONDS:
            logger.warning(
                f"[Linear] Using expired token within grace period: workspace={workspace_id}"
            )
            return row["access_token"]

        logger.error(
            f"[Linear] Token expired and refresh failed: workspace={workspace_id}"
        )
        return None

    def get_app_user_id(self, workspace_id: str) -> Optional[str]:
        """获取 App bot 用户 ID。

        Args:
            workspace_id: Linear workspace ID

        Returns:
            app_user_id 或 None
        """
        row = self.get_installation(workspace_id)
        return row["app_user_id"] if row else None

    def save_session(self, issue_id: str, claude_session_id: str) -> None:
        """持久化 issue_id -> claude_session_id 映射。"""
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO linear_session_map (issue_id, claude_session_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET
                    claude_session_id = excluded.claude_session_id,
                    updated_at = excluded.updated_at
                """,
                (issue_id, claude_session_id, now),
            )

    def get_session(self, issue_id: str) -> Optional[str]:
        """按 issue_id 查询 claude_session_id，不存在返回 None。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT claude_session_id FROM linear_session_map WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            return row["claude_session_id"] if row else None

    def get_first_workspace_id(self) -> Optional[str]:
        """单 workspace 场景：返回唯一安装的 workspace_id。

        Returns:
            workspace_id 或 None
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT workspace_id FROM linear_installations LIMIT 1"
            ).fetchone()
            return row["workspace_id"] if row else None

    def _do_refresh(self, workspace_id: str, refresh_token: str) -> Optional[str]:
        """使用 refresh_token 换取新 access_token 并持久化。

        Args:
            workspace_id: Linear workspace ID
            refresh_token: 当前 refresh token

        Returns:
            新 access_token，刷新失败返回 None
        """
        client_id = os.environ.get("LINEAR_CLIENT_ID", "")
        client_secret = os.environ.get("LINEAR_CLIENT_SECRET", "")
        try:
            resp = httpx.post(
                "https://api.linear.app/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            new_access = data["access_token"]
            new_refresh = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in")
            now = int(time.time())
            expires_at = now + expires_in if expires_in else None
            with self._conn() as conn:
                conn.execute(
                    """
                    UPDATE linear_installations
                    SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = ?
                    WHERE workspace_id = ?
                """,
                    (new_access, new_refresh, expires_at, now, workspace_id),
                )
            logger.info(f"[Linear] Token refreshed: workspace={workspace_id}")
            return new_access
        except Exception:
            logger.warning(
                f"[Linear] Token refresh failed: workspace={workspace_id}",
                exc_info=True,
            )
            return None
