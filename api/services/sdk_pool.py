"""Claude SDK 会话级连接缓存 - 按 session_id 复用 ClaudeSDKClient，空闲 60 分钟后自动回收。"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

logger = logging.getLogger(__name__)

TTL_SECONDS = 3600  # 10 分钟


@dataclass
class CachedSession:
    client: ClaudeSDKClient
    last_used: float = field(default_factory=time.monotonic)
    in_use: bool = False


class SDKSessionCache:
    """
    会话级 SDK 连接缓存。

    - 同一 session_id 复用同一个 ClaudeSDKClient 子进程，消除多轮对话冷启动
    - 空闲超过 TTL_SECONDS 的连接由 reaper 自动回收
    - 连接出错时标记 unhealthy，立即丢弃
    """

    def __init__(self):
        self._cache: dict[str, CachedSession] = {}
        self._lock = asyncio.Lock()
        self._reaper_task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动后台 reaper，应用启动时调用。"""
        self._reaper_task = asyncio.create_task(self._reaper())
        logger.info("[SessionCache] 已启动")

    async def stop(self) -> None:
        """关闭所有连接，应用关闭时调用。"""
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            clients = [entry.client for entry in self._cache.values()]
            self._cache.clear()

        for client in clients:
            await self._disconnect(client)

        logger.info("[SessionCache] 所有连接已关闭")

    async def get_or_create(self, session_id: str, options: ClaudeAgentOptions) -> ClaudeSDKClient:
        """
        获取或创建 session_id 对应的连接。

        命中缓存时直接复用；未命中时在锁外 connect，避免阻塞其他请求。
        """
        async with self._lock:
            entry = self._cache.get(session_id)
            if entry:
                entry.last_used = time.monotonic()
                entry.in_use = True
                t = entry.client._transport
                returncode = t._process.returncode if t and t._process else "no_process"
                stdin_alive = t._stdin_stream is not None if t else False
                ready = t._ready if t else False
                logger.info(
                    f"[SessionCache] 复用连接: {session_id} | "
                    f"returncode={returncode} stdin_alive={stdin_alive} ready={ready}"
                )
                return entry.client

        # 锁外创建，避免 connect() 阻塞其他协程
        client = ClaudeSDKClient(options=options)
        await client.connect()

        async with self._lock:
            # double-check：防止并发时重复创建
            if session_id in self._cache:
                await self._disconnect(client)
                entry = self._cache[session_id]
                entry.last_used = time.monotonic()
                entry.in_use = True
                logger.debug(f"[SessionCache] 并发命中，复用已有连接: {session_id}")
                return entry.client

            self._cache[session_id] = CachedSession(client=client, in_use=True)
            logger.info(f"[SessionCache] 新建连接: {session_id} (当前缓存数: {len(self._cache)})")
            return client

    async def release(self, session_id: str, healthy: bool = True) -> None:
        """归还连接。healthy=False 时立即丢弃并异步断开。"""
        async with self._lock:
            entry = self._cache.get(session_id)
            if not entry:
                return
            if healthy:
                entry.in_use = False
                entry.last_used = time.monotonic()
                logger.debug(f"[SessionCache] 连接已归还: {session_id}")
            else:
                self._cache.pop(session_id)
                asyncio.create_task(self._disconnect(entry.client))
                logger.warning(f"[SessionCache] 丢弃不健康连接: {session_id}")

    async def _reaper(self) -> None:
        """每 60 秒扫描一次，回收空闲超过 TTL 的连接。"""
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            async with self._lock:
                expired = [
                    sid for sid, e in self._cache.items()
                    if not e.in_use and (now - e.last_used) > TTL_SECONDS
                ]
                clients_to_close = []
                for sid in expired:
                    entry = self._cache.pop(sid)
                    clients_to_close.append(entry.client)
                    logger.info(f"[SessionCache] TTL 过期，回收连接: {sid}")

            for client in clients_to_close:
                asyncio.create_task(self._disconnect(client))

    @staticmethod
    async def _disconnect(client: ClaudeSDKClient) -> None:
        try:
            await client.disconnect()
        except Exception:
            pass


# 全局缓存实例（延迟初始化）
_cache: SDKSessionCache | None = None


def get_cache() -> SDKSessionCache | None:
    return _cache


def init_cache() -> SDKSessionCache:
    global _cache
    _cache = SDKSessionCache()
    return _cache
