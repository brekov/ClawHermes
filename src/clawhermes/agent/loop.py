"""
ClawHermes - Agent 核心循环（思考-行动）
融合 Hermes 的三层 Prompt 和 OpenClaw 的钩子体系
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Callable, List

from clawhermes.agent.exceptions import (
    ClawHermesError,
    LLMConnectionError,
    LLMError,
)
from clawhermes.agent.prompt import SystemPrompt
from clawhermes.llm.provider import LLMProvider, LLMResponse

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

    async def trigger_async(self, point: str, timeout: float | None = None,
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
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return asyncio.run(self.trigger_async(point, timeout, **kwargs))
        return loop.run_until_complete(self.trigger_async(point, timeout, **kwargs))

    def remove(self, point: str, handler: Callable) -> bool:
        for store in (self._hooks, self._async_hooks):
            handlers = store.get(point, [])
            if handler in handlers:
                handlers.remove(handler)
                return True
        return False


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
            tool_result=result if 'result' in locals() else None,
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
            tool_result=result if 'result' in locals() else None,
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


@dataclass
class AgentConfig:
    max_iterations: int = 50
    max_tool_calls_per_round: int = 10
    queue_mode: str = "steer"


class Agent:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        config: AgentConfig | None = None,
        memory_manager=None,
        skill_manager=None,
        context_engine=None,
        agent_name: str | None = None,
        delegate_manager=None,
        session_mgr=None,
    ):
        self.llm = llm_provider
        self.prompt = SystemPrompt()
        self.tools = tool_registry or ToolRegistry()
        self.hooks = HookManager()
        self.dispatcher = ToolDispatcher(self.tools, self.hooks)
        self.config = config or AgentConfig()
        self.memory = memory_manager
        self.skills = skill_manager
        self.context_engine = context_engine
        self.delegate_manager = delegate_manager
        self.session_mgr = session_mgr
        self._agent_name = agent_name or "ClawHermes"
        self._interrupt = threading.Event()
        self._last_conversation: list[dict] = []

        if agent_name:
            try:
                self.prompt.stable.load_from_agent(agent_name)
            except Exception as e:
                logger.warning("Failed to load stable prompt: %s", e)

    def _build_tool_context(self, session_id: str = "") -> dict:
        ctx: dict[str, Any] = {"session_id": session_id}
        if self.memory:
            ctx["_memory_manager"] = self.memory
        if self.delegate_manager:
            ctx["_delegate_manager"] = self.delegate_manager
        return ctx

    def _build_messages(self, user_message: str, session_id: str = "") -> list[dict]:
        """构建 system+user 消息并持久化 user 消息（chat/chat_async 共用）"""
        messages: list[dict] = [
            {"role": "system", "content": self.prompt.build()},
            {"role": "user", "content": user_message},
        ]
        if self.session_mgr and session_id:
            try:
                self.session_mgr.add_message(session_id, "user", user_message)
            except Exception as e:
                logger.warning("Failed to persist user message: %s", e)
        return messages

    def _finalize_response(
        self, messages: list[dict], content: str, session_id: str = ""
    ) -> str:
        """完成响应：触发 hooks、更新会话快照、持久化 assistant 消息（chat/chat_async 共用）"""
        hook_result = self.hooks.trigger(
            HookPoint.BEFORE_AGENT_REPLY,
            response=content,
        )
        final = str(hook_result.get("override_response", content))

        self._last_conversation = [
            {"role": m["role"], "content": str(m.get("content", ""))[:500]}
            for m in messages[-6:]
        ]
        self.hooks.trigger(HookPoint.AFTER_AGENT_END, messages=messages)

        if self.session_mgr and session_id:
            try:
                self.session_mgr.add_message(session_id, "assistant", final)
            except Exception as e:
                logger.warning("Failed to persist assistant message: %s", e)
        return final

    def _should_loop_continue(self, messages: list[dict], iteration: int) -> str | None:
        """检查循环控制信号：hooks abort / interrupt / context 压缩。
        返回非 None 表示应提前退出，返回值即退出响应。"""
        hook_result = self.hooks.trigger(
            HookPoint.BEFORE_AGENT_RUN,
            messages=messages,
            iteration=iteration,
        )
        if hook_result.get("abort"):
            return str(hook_result.get("response", ""))

        if self._interrupt.is_set():
            return "（已中断）"

        if self.context_engine and iteration > 1:
            prompt_tokens = sum(len(m.get("content", "")) for m in messages)
            if self.context_engine.should_compress(prompt_tokens):
                messages[:] = self.context_engine.compress(messages, prompt_tokens)

        return None

    def chat(self, user_message: str, session_id: str = "") -> str:
        messages = self._build_messages(user_message, session_id)

        for iteration in range(self.config.max_iterations):
            early = self._should_loop_continue(messages, iteration)
            if early is not None:
                return early

            self.hooks.trigger(HookPoint.MODEL_CALL_STARTED)
            try:
                response: LLMResponse = self.llm.chat(
                    messages,
                    tools=self.tools.schemas() if self.tools.list() else None,
                )
            except LLMError:
                raise
            except Exception as e:
                raise LLMConnectionError(f"LLM 调用失败: {e}") from e

            self.hooks.trigger(HookPoint.MODEL_CALL_ENDED, response=response)

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            }
            messages.append(assistant_msg)

            if not response.tool_calls:
                return self._finalize_response(messages, response.content or "", session_id)

            tool_context = self._build_tool_context(session_id)
            tool_context["iteration"] = iteration

            tool_results = self.dispatcher.execute(
                response.tool_calls,
                context=tool_context,
            )
            messages.extend(tool_results)

        return "（已达最大迭代次数）"

    async def _chat_async_internal(self, user_message: str, session_id: str = "") -> str:
        """内部异步聊天实现，使用原生异步LLM调用"""
        messages = self._build_messages(user_message, session_id)

        for iteration in range(self.config.max_iterations):
            early = self._should_loop_continue(messages, iteration)
            if early is not None:
                return early

            self.hooks.trigger(HookPoint.MODEL_CALL_STARTED)
            try:
                response: LLMResponse = await self.llm.chat_async(
                    messages,
                    tools=self.tools.schemas() if self.tools.list() else None,
                )
            except LLMError:
                raise
            except Exception as e:
                raise LLMConnectionError(f"LLM 异步调用失败: {e}") from e

            self.hooks.trigger(HookPoint.MODEL_CALL_ENDED, response=response)

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            }
            messages.append(assistant_msg)

            if not response.tool_calls:
                return self._finalize_response(messages, response.content or "", session_id)

            tool_context = self._build_tool_context(session_id)
            tool_context["iteration"] = iteration

            tool_results = await self.dispatcher.execute_async(
                response.tool_calls,
                context=tool_context,
            )
            messages.extend(tool_results)

        return "（已达最大迭代次数）"

    async def chat_async(self, user_message: str, session_id: str = "") -> str:
        """异步聊天接口，使用原生异步LLM调用"""
        return await self._chat_async_internal(user_message, session_id)


    async def chat_stream(
        self, user_message: str, session_id: str = ""
    ) -> AsyncGenerator[dict, None]:
        """流式聊天 — 以 SSE 事件流逐块返回响应。

        复用 _build_messages / _should_loop_continue / _finalize_response 辅助方法，
        确保 user/assistant 消息持久化到 session_mgr 并触发 hooks
        （与 chat/chat_async 行为一致）。

        通过 LLMProvider.chat_stream() 获取流式 token，
        每个完成块即时 yield 为 SSE 事件：

        - {"event":"text","data":"..."}    内容块（800-1200 chars）
        - {"event":"tool_call","data":{...}} 工具调用
        - {"event":"tool_result","data":{...}} 工具结果
        - {"event":"error","data":"..."}    错误
        - {"event":"done","data":{...}}     完成（含 usage）
        """
        messages = self._build_messages(user_message, session_id)

        for iteration in range(self.config.max_iterations):
            # 复用 _should_loop_continue：触发 BEFORE_AGENT_RUN hook、处理 abort / interrupt / 压缩
            early = self._should_loop_continue(messages, iteration)
            if early is not None:
                # 区分 interrupt 与 abort：stream 需 yield 不同 done 事件
                if self._interrupt.is_set():
                    yield {"event": "text", "data": early}
                    yield {"event": "done", "data": {"interrupted": True}}
                else:
                    yield {"event": "text", "data": early}
                    yield {"event": "done", "data": {"aborted": True}}
                return

            self.hooks.trigger(HookPoint.MODEL_CALL_STARTED)

            # 流式 LLM 调用 — 收集 text/tool_calls/done
            text_parts: list[str] = []
            stream_tool_calls: list[dict] | None = None
            stream_usage: dict | None = None
            stream_model = ""
            stream_error: str | None = None

            async for chunk in self.llm.chat_stream(
                messages,
                tools=self.tools.schemas() if self.tools.list() else None,
            ):
                if chunk.kind == "text":
                    yield {"event": "text", "data": chunk.content}
                    text_parts.append(chunk.content)
                elif chunk.kind == "tool_calls":
                    stream_tool_calls = chunk.tool_calls
                    for tc in (chunk.tool_calls or []):
                        yield {
                            "event": "tool_call",
                            "data": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get("arguments", "{}"),
                            },
                        }
                elif chunk.kind == "error":
                    stream_error = chunk.error
                    yield {"event": "error", "data": chunk.error}
                elif chunk.kind == "done":
                    stream_usage = chunk.usage
                    stream_model = chunk.model or stream_model
                if chunk.model:
                    stream_model = chunk.model

            if stream_error:
                yield {"event": "done", "data": {"error": stream_error}}
                return

            self.hooks.trigger(HookPoint.MODEL_CALL_ENDED)

            # 构建 assistant 消息
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(text_parts) if text_parts else "",
                "tool_calls": stream_tool_calls,
            }
            messages.append(assistant_msg)

            # 无工具调用 → 完成：复用 _finalize_response 持久化 assistant 消息并触发 hooks
            if not stream_tool_calls:
                content = "".join(text_parts)
                self._finalize_response(messages, content, session_id)
                yield {
                    "event": "done",
                    "data": {
                        "usage": stream_usage,
                        "model": stream_model,
                        "iterations": iteration + 1,
                    },
                }
                return

            # 执行工具
            tool_context = self._build_tool_context(session_id)
            tool_context["iteration"] = iteration

            tool_results = await self.dispatcher.execute_async(
                stream_tool_calls,
                context=tool_context,
            )
            # yield 工具结果
            for tr in tool_results:
                yield {
                    "event": "tool_result",
                    "data": {
                        "name": tr.get("name", ""),
                        "call_id": tr.get("tool_call_id", ""),
                        "content": tr.get("content", ""),
                    },
                }
            messages.extend(tool_results)

        yield {
            "event": "done",
            "data": {"max_iterations": True, "iterations": self.config.max_iterations},
        }

    def interrupt(self):
        self._interrupt.set()

    def get_conversation(self) -> list[dict]:
        return self._last_conversation
