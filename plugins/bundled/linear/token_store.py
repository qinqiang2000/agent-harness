"""SQLite-backed Linear OAuth token store."""

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
_GRACE_PERIOD_SECONDS = 1800  # Linear 刷新宽限期 30 分钟


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
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM linear_installations WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()

    def get_token(self, workspace_id: str) -> Optional[str]:
        """返回有效 access_token，临近过期时自动刷新。"""
        row = self.get_installation(workspace_id)
        if not row:
            return None

        now = int(time.time())
        expires_at = row["expires_at"]

        # 未设置过期时间（client_credentials 模式）或距过期 > 5 分钟，直接返回
        if expires_at is None or (expires_at - now) > _REFRESH_BUFFER_SECONDS:
            return row["access_token"]

        # 尝试刷新
        if row["refresh_token"]:
            new_token = self._do_refresh(workspace_id, row["refresh_token"])
            if new_token:
                return new_token

        # 刷新失败，宽限期内仍可用旧 token
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
        row = self.get_installation(workspace_id)
        return row["app_user_id"] if row else None

    def get_first_workspace_id(self) -> Optional[str]:
        """单 workspace 场景：返回唯一安装的 workspace_id。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT workspace_id FROM linear_installations LIMIT 1"
            ).fetchone()
            return row["workspace_id"] if row else None

    def _do_refresh(self, workspace_id: str, refresh_token: str) -> Optional[str]:
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
