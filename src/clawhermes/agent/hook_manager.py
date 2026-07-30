"""
ClawHermes - 钩子管理器
内部机制：HookPoint 钩子点定义 + HookManager 同步/异步钩子触发。
从 agent/loop.py 拆出，供 Agent 与 ToolDispatcher 共用。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _is_in_running_loop() -> bool:
    """检测当前是否在运行中的事件循环内。

    用于同步路径（execute / _execute_single_tool）的安全检查：若已在运行循环内，
    调用 asyncio.run 会抛 RuntimeError，因此应改用 execute_async。
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class HookPoint:
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    BEFORE_AGENT_RUN = "before_agent_run"
    BEFORE_AGENT_REPLY = "before_agent_reply"
    AFTER_AGENT_END = "after_agent_end"
    MODEL_CALL_STARTED = "model_call_started"
    MODEL_CALL_ENDED = "model_call_ended"


class HookManager:
    def __init__(self, default_timeout: float = 10.0):
        self._hooks: dict[str, list[Callable]] = {}
        self._async_hooks: dict[str, list[Callable]] = {}
        self._default_timeout = default_timeout

    def register(self, point: str, handler: Callable):
        is_async = asyncio.iscoroutinefunction(handler)
        if is_async:
            target = self._async_hooks
        else:
            target = self._hooks
        if point not in target:
            target[point] = []
        target[point].append(handler)

    def trigger(self, point: str, **kwargs) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for handler in self._hooks.get(point, []):
            try:
                result = handler(**kwargs)
                if result:
                    results.update(result)
            except Exception as e:
                logger.warning("Hook %s failed: %s", point, e)
        return results

    async def trigger_async(self, point: str, timeout: float | None = None,  # noqa: ASYNC109  内部用 asyncio.wait_for 实现
                            **kwargs) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for handler in self._hooks.get(point, []):
            try:
                result = handler(**kwargs)
                if result:
                    results.update(result)
            except Exception as e:
                logger.warning("Hook %s failed: %s", point, e)

        for handler in self._async_hooks.get(point, []):
            try:
                effective_timeout = timeout or self._default_timeout
                result = await asyncio.wait_for(handler(**kwargs), timeout=effective_timeout)
                if result:
                    results.update(result)
            except asyncio.TimeoutError:
                logger.warning("Hook %s async handler timed out (%.1fs)", point, effective_timeout)
            except Exception as e:
                logger.warning("Hook %s async failed: %s", point, e)

        return results

    def trigger_sync_with_async(self, point: str, timeout: float | None = None,
                                **kwargs) -> dict[str, Any]:
        if not self._async_hooks.get(point):
            return self.trigger(point, **kwargs)
        try:
            asyncio.get_running_loop()
            # 在运行中的事件循环内 — 不能 run_until_complete（会 raise），回退同步触发
            return self.trigger(point, **kwargs)
        except RuntimeError:
            pass
        # 无运行循环 — 创建新循环执行后关闭
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.trigger_async(point, timeout, **kwargs))
        finally:
            loop.close()

    def remove(self, point: str, handler: Callable) -> bool:
        for store in (self._hooks, self._async_hooks):
            handlers = store.get(point, [])
            if handler in handlers:
                handlers.remove(handler)
                return True
        return False
