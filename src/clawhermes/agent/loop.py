"""
ClawHermes - Agent 核心循环（思考-行动）
融合 Hermes 的三层 Prompt 和 OpenClaw 的钩子体系
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
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
    PARALLEL_SAFE = frozenset({
        "web_search", "web_fetch", "read_file",
        "memory_search", "skills_list",
    })
    PATH_SCOPED = frozenset({"write_file", "patch", "read_file"})

    def __init__(self, registry: ToolRegistry, hook_manager: HookManager):
        self.registry = registry
        self.hooks = hook_manager

    def execute(self, tool_calls: list[dict], context: dict) -> list[dict]:
        results = []

        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            args_str = tc.get("function", {}).get("arguments", "{}")
            tool_id = tc.get("id", "")

            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}

            tool_def = self.registry.get(name)
            if not tool_def:
                results.append(self._error_result(tool_id, name, f"未知工具: {name}"))
                continue

            hook_result = self.hooks.trigger(
                HookPoint.BEFORE_TOOL_CALL,
                tool_name=name,
                tool_args=args,
                context=context,
            )
            if hook_result.get("blocked"):
                results.append(self._error_result(
                    tool_id, name, hook_result.get("reason", "被钩子阻止")
                ))
                continue
            if hook_result.get("override_args"):
                args = hook_result["override_args"]

            tool_context = dict(context)
            if context.get("_memory_manager"):
                tool_context["_memory_manager"] = context["_memory_manager"]
            if context.get("_delegate_manager"):
                tool_context["_delegate_manager"] = context["_delegate_manager"]

            try:
                result = tool_def.handler(**args, **tool_context)
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            except ClawHermesError as e:
                results.append(self._error_result(tool_id, name, str(e)))
            except Exception as e:
                results.append(self._error_result(tool_id, name, str(e)))

            self.hooks.trigger(
                HookPoint.AFTER_TOOL_CALL,
                tool_name=name,
                tool_args=args,
                tool_result=result if 'result' in dir() else None,
                duration_ms=0,
            )

        return results

    def _error_result(self, tool_id, name, error):
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "name": name,
            "content": json.dumps({"error": error}, ensure_ascii=False),
        }


@dataclass
class AgentConfig:
    max_iterations: int = 20
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
        self._agent_name = agent_name or "ClawHermes"
        self._interrupt = threading.Event()
        self._last_conversation: list[dict] = []

        if agent_name:
            try:
                self.prompt.stable.load_from_agent(agent_name)
            except Exception:
                pass

    def _build_tool_context(self, session_id: str = "") -> dict:
        ctx: dict[str, Any] = {"session_id": session_id}
        if self.memory:
            ctx["_memory_manager"] = self.memory
        if self.delegate_manager:
            ctx["_delegate_manager"] = self.delegate_manager
        return ctx

    def chat(self, user_message: str, session_id: str = "") -> str:
        messages = []
        messages.append({
            "role": "system",
            "content": self.prompt.build(),
        })
        messages.append({"role": "user", "content": user_message})

        for iteration in range(self.config.max_iterations):
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
                    messages = self.context_engine.compress(messages, prompt_tokens)

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
                hook_result = self.hooks.trigger(
                    HookPoint.BEFORE_AGENT_REPLY,
                    response=response.content or "",
                )
                final = str(hook_result.get("override_response", response.content or ""))

                self._last_conversation = [
                    {"role": m["role"], "content": str(m.get("content", ""))[:500]}
                    for m in messages[-6:]
                ]

                self.hooks.trigger(HookPoint.AFTER_AGENT_END, messages=messages)

                return final

            tool_context = self._build_tool_context(session_id)
            tool_context["iteration"] = iteration

            tool_results = self.dispatcher.execute(
                response.tool_calls,
                context=tool_context,
            )
            messages.extend(tool_results)

        return "（已达最大迭代次数）"

    async def chat_async(self, user_message: str, session_id: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.chat, user_message, session_id,
        )

    def interrupt(self):
        self._interrupt.set()

    def get_conversation(self) -> list[dict]:
        return self._last_conversation
