"""Open API Token 管理器."""

import hashlib
import logging
import time
import uuid
from typing import Dict

logger = logging.getLogger(__name__)

TOKEN_EXPIRE_SECONDS = 86400


class TokenManager:
    def __init__(self, app_id: str, app_key: str):
        self.app_id = app_id
        self.app_key = app_key
        self._tokens: Dict[str, float] = {}  # token -> expires_at

    def _sign(self, create_time: str) -> str:
        raw = self.app_id + create_time + self.app_key
        return hashlib.md5(raw.encode()).hexdigest()

    def verify_sign(self, appid: str, create_time: str, sign: str) -> bool:
        if appid != self.app_id:
            return False
        return self._sign(create_time) == sign

    def generate_token(self) -> tuple[str, int]:
        """生成新 token，返回 (token, expires_in)."""
        self._cleanup_expired()
        raw = self.app_id + str(time.time()) + self.app_key + str(uuid.uuid4())
        token = hashlib.md5(raw.encode()).hexdigest()
        self._tokens[token] = time.time() + TOKEN_EXPIRE_SECONDS
        return token, TOKEN_EXPIRE_SECONDS

    def is_valid(self, token: str) -> bool:
        expires_at = self._tokens.get(token)
        if not expires_at:
            return False
        if time.time() > expires_at:
            del self._tokens[token]
            return False
        return True

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [t for t, exp in self._tokens.items() if now > exp]
        for t in expired:
            del self._tokens[t]
