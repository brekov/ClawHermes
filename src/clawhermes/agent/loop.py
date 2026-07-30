"""
ClawHermes - Agent 核心循环（思考-行动）
融合 Hermes 的三层 Prompt 和 OpenClaw 的钩子体系
"""
from __future__ import annotations

import logging
import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from clawhermes.agent.exceptions import LLMConnectionError, LLMError

# 向后兼容 re-export：以下符号已迁移至新模块。
# 新代码应直接 from clawhermes.agent.hook_manager import ...
# 或 from clawhermes.tools.registry import ...
from clawhermes.agent.hook_manager import (
    HookManager,
    HookPoint,
    _is_in_running_loop,  # noqa: F401
)
from clawhermes.agent.prompt import SystemPrompt
from clawhermes.llm.provider import LLMProvider, LLMResponse
from clawhermes.tools.registry import (
    ToolDef,  # noqa: F401
    ToolDispatcher,
    ToolRegistry,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    max_iterations: int = 50


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
            # 精确 token 计数：优先使用 litellm.token_counter，失败时折中估算
            try:
                import litellm
                prompt_tokens = litellm.token_counter(
                    model=getattr(self.llm, "model", "gpt-4"),
                    messages=messages,
                )
            except Exception:
                # 降级：折中估算（中文 ~1.5 字符/token，英文 ~4 字符/token，取 3 作折中）
                prompt_tokens = sum(len(m.get("content", "")) // 3 for m in messages)
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
