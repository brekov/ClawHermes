"""
ClawHermes - 工具系统核心抽象
ToolDef / ToolRegistry / ToolDispatcher：工具定义、注册与分派。
从 agent/loop.py 拆出，修复依赖倒置（工具系统不应驻留 agent 模块）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, List

from clawhermes.agent.exceptions import ClawHermesError
from clawhermes.agent.hook_manager import HookManager, HookPoint, _is_in_running_loop

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    handler: Callable
    group: str = "core"
    parallel_safe: bool = False
    timeout_ms: int = 30000
    require_confirm: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list(self) -> List[ToolDef]:
        return list(self._tools.values())

    def schemas(self) -> List[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]


class ToolDispatcher:
    NEVER_PARALLEL = frozenset({"clarify", "confirm"})
    PATH_SCOPED = frozenset({"write_file", "patch", "read_file"})

    def __init__(self, registry: ToolRegistry, hook_manager: HookManager):
        self.registry = registry
        self.hooks = hook_manager

    def _is_parallel_safe(self, tool_name: str) -> bool:
        tool_def = self.registry.get(tool_name)
        if not tool_def:
            return False
        return tool_def.parallel_safe

    def _execute_single_tool(self, tc: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """同步执行单个工具调用。

        .. note::
           仅用于无事件循环的上下文（如 CLI 或 asyncio.to_thread 包装的线程）。
           若工具 handler 返回协程且检测到运行中的事件循环（如 FastAPI 误用同步
           execute），将抛 RuntimeError 提示改用 execute_async。
        """
        name = tc.get("function", {}).get("name", "")
        args_str = tc.get("function", {}).get("arguments", "{}")
        tool_id = tc.get("id", "")

        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {}

        tool_def = self.registry.get(name)
        if not tool_def:
            return self._error_result(tool_id, name, f"未知工具: {name}")

        hook_result = self.hooks.trigger(
            HookPoint.BEFORE_TOOL_CALL,
            tool_name=name,
            tool_args=args,
            context=context,
        )
        if hook_result.get("blocked"):
            return self._error_result(
                tool_id, name, hook_result.get("reason", "被钩子阻止")
            )
        if hook_result.get("override_args"):
            args = hook_result["override_args"]

        tool_context = dict(context)
        if context.get("_memory_manager"):
            tool_context["_memory_manager"] = context["_memory_manager"]
        if context.get("_delegate_manager"):
            tool_context["_delegate_manager"] = context["_delegate_manager"]

        start_ms = time.monotonic() * 1000
        result = None
        try:
            raw = tool_def.handler(**args, **tool_context)
            # 同步路径中工具可能返回协程 — chat() 被 asyncio.to_thread 包装在独立线程，
            # 无运行中的事件循环时可安全 asyncio.run；若检测到运行中的循环
            # （如 FastAPI 误用同步 execute），抛明确异常提示改用 execute_async
            if asyncio.iscoroutine(raw):
                if _is_in_running_loop():
                    raise RuntimeError(
                        "同步 execute() 不能在运行中的事件循环内调用；请改用 execute_async() "
                        "或通过 asyncio.to_thread() 包装"
                    )
                result = asyncio.run(raw)
            else:
                result = raw
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = {
                "role": "tool",
                "tool_call_id": tool_id,
                "name": name,
                "content": json.dumps(result, ensure_ascii=False),
            }
        except ClawHermesError as e:
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = self._error_result(tool_id, name, str(e))
        except RuntimeError as e:
            # C8: 事件循环检测的 RuntimeError 透传给调用者，不被吞为 error_result
            if "execute_async" in str(e):
                raise
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = self._error_result(tool_id, name, str(e))
        except Exception as e:
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = self._error_result(tool_id, name, str(e))

        self.hooks.trigger(
            HookPoint.AFTER_TOOL_CALL,
            tool_name=name,
            tool_args=args,
            tool_result=result,
            duration_ms=duration_ms,
        )

        return result_data

    async def _execute_single_tool_async(
        self, tc: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        name = tc.get("function", {}).get("name", "")
        args_str = tc.get("function", {}).get("arguments", "{}")
        tool_id = tc.get("id", "")

        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {}

        tool_def = self.registry.get(name)
        if not tool_def:
            return self._error_result(tool_id, name, f"未知工具: {name}")

        hook_result = await self.hooks.trigger_async(
            HookPoint.BEFORE_TOOL_CALL,
            tool_name=name,
            tool_args=args,
            context=context,
        )
        if hook_result.get("blocked"):
            return self._error_result(
                tool_id, name, hook_result.get("reason", "被钩子阻止")
            )
        if hook_result.get("override_args"):
            args = hook_result["override_args"]

        tool_context = dict(context)
        if context.get("_memory_manager"):
            tool_context["_memory_manager"] = context["_memory_manager"]
        if context.get("_delegate_manager"):
            tool_context["_delegate_manager"] = context["_delegate_manager"]

        start_ms = time.monotonic() * 1000
        result = None
        try:
            if asyncio.iscoroutinefunction(tool_def.handler):
                result = await tool_def.handler(**args, **tool_context)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: tool_def.handler(**args, **tool_context)
                )
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = {
                "role": "tool",
                "tool_call_id": tool_id,
                "name": name,
                "content": json.dumps(result, ensure_ascii=False),
            }
        except ClawHermesError as e:
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = self._error_result(tool_id, name, str(e))
        except Exception as e:
            duration_ms = time.monotonic() * 1000 - start_ms
            result_data = self._error_result(tool_id, name, str(e))

        await self.hooks.trigger_async(
            HookPoint.AFTER_TOOL_CALL,
            tool_name=name,
            tool_args=args,
            tool_result=result,
            duration_ms=duration_ms,
        )

        return result_data

    def execute(self, tool_calls: list[dict], context: dict) -> list[dict]:
        """同步执行工具调用。

        .. note::
           仅用于无事件循环的上下文（如 CLI）。FastAPI/asyncio 上下文必须用
           ``execute_async()``，否则并行工具路径会因检测到运行中的事件循环而抛
           RuntimeError。
        """
        parallel_safe_calls = []
        serial_calls = []

        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if name in self.NEVER_PARALLEL:
                serial_calls.append(tc)
            elif self._is_parallel_safe(name):
                parallel_safe_calls.append(tc)
            else:
                serial_calls.append(tc)

        results = []
        for tc in serial_calls:
            result = self._execute_single_tool(tc, context)
            results.append(result)

        if len(parallel_safe_calls) > 1:
            # C7: 同步 execute 不能在运行中的事件循环内调用 — asyncio.run 会崩溃，
            # 且 new_event_loop 会阻塞外层循环。检测到运行循环时抛明确异常
            if _is_in_running_loop():
                raise RuntimeError(
                    "同步 execute() 不能在运行中的事件循环内调用；请改用 execute_async()"
                )

            async def _run_parallel():
                return await asyncio.gather(*[
                    self._execute_single_tool_async(tc, context)
                    for tc in parallel_safe_calls
                ])

            # 无运行循环时 asyncio.run 自建临时循环并清理
            parallel_results = asyncio.run(_run_parallel())
            results.extend(parallel_results)
        else:
            for tc in parallel_safe_calls:
                result = self._execute_single_tool(tc, context)
                results.append(result)

        return results

    async def execute_async(self, tool_calls: list[dict], context: dict) -> list[dict]:
        parallel_safe_calls = []
        serial_calls = []

        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if name in self.NEVER_PARALLEL:
                serial_calls.append(tc)
            elif self._is_parallel_safe(name):
                parallel_safe_calls.append(tc)
            else:
                serial_calls.append(tc)

        results = []
        for tc in serial_calls:
            result = await self._execute_single_tool_async(tc, context)
            results.append(result)

        if parallel_safe_calls:
            parallel_results = await asyncio.gather(*[
                self._execute_single_tool_async(tc, context)
                for tc in parallel_safe_calls
            ])
            results.extend(parallel_results)

        return results

    def _error_result(self, tool_id: str, name: str, error: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "name": name,
            "content": json.dumps({"error": error}, ensure_ascii=False),
        }
