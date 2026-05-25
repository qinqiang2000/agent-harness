"""轻量请求链路计时工具（ContextVar 无侵入方案）。"""

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

_current_timer: ContextVar[Optional["PerfTimer"]] = ContextVar("perf_timer", default=None)
_current_session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


def set_session_id(session_id: str) -> None:
    """在当前异步上下文中设置 session_id，供日志 Filter 读取。"""
    _current_session_id.set(session_id)


def get_session_id() -> Optional[str]:
    """获取当前异步上下文的 session_id。"""
    return _current_session_id.get()


class PerfTimer:
    """请求链路计时器，用 [PERF] 前缀 + request_id 串联所有节点日志。

    用法::

        perf = PerfTimer()
        perf.attach()           # 绑定到当前异步上下文
        perf.mark("REQUEST_RECEIVED")

        # 任意深层代码，无需传参：
        PerfTimer.current().mark("PROMPT_BUILT")
    """

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or uuid.uuid4().hex[:8]
        self._start = time.perf_counter()
        self._last = self._start

    def attach(self):
        """绑定到当前异步上下文，后续可通过 PerfTimer.current() 取用。"""
        _current_timer.set(self)

    def mark(self, label: str):
        """打点记录当前节点耗时。"""
        now = time.perf_counter()
        step_ms = (now - self._last) * 1000
        total_ms = (now - self._start) * 1000
        logger.info(
            f"[PERF] rid={self.request_id} {label} step={step_ms:.1f}ms total={total_ms:.1f}ms"
        )
        self._last = now

    def done(self):
        """标记请求结束。"""
        self.mark("DONE")

    @staticmethod
    def current() -> Optional["PerfTimer"]:
        """获取当前异步上下文绑定的 PerfTimer，无则返回 None。"""
        return _current_timer.get()
