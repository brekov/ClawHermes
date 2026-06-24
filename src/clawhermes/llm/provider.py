"""
ClawHermes - LLM Provider 抽象层
封装 litellm，统一调用接口，支持多凭证池
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from threading import Lock
from typing import Any

import litellm

from clawhermes.agent.exceptions import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict] | None = None
    usage: dict | None = None
    model: str = ""
    duration_ms: float = 0.0
    raw: Any = None


@dataclass
class StreamChunk:
    """流式响应块。

    Attrs:
        kind: 块类型 — "text" | "tool_calls" | "usage" | "error" | "done"
        content: 文本内容（kind="text" 时）
        tool_calls: 累积的工具调用列表（kind="tool_calls" 时）
        usage: token 用量（kind="usage" / "done" 时）
        model: 实际使用的模型名
        error: 错误信息（kind="error" 时）
    """
    kind: str
    content: str = ""
    tool_calls: list[dict] | None = None
    usage: dict | None = None
    model: str = ""
    error: str = ""


class CredentialPool:
    STRATEGY_FILL_FIRST = "fill_first"
    STRATEGY_ROUND_ROBIN = "round_robin"
    STRATEGY_RANDOM = "random"
    STRATEGY_LEAST_USED = "least_used"

    def __init__(self, api_keys: list[str], strategy: str = "round_robin"):
        self.api_keys = api_keys
        self.strategy = strategy
        self._index = 0
        self._used_count: dict[str, int] = {k: 0 for k in api_keys}
        self._cooldown_until: dict[str, float] = {}
        self._lock = Lock()

    def get_key(self) -> str | None:
        with self._lock:
            now = time.time()
            available = [
                k for k in self.api_keys
                if self._cooldown_until.get(k, 0) < now
            ]
            if not available:
                return None

            if self.strategy == self.STRATEGY_ROUND_ROBIN:
                key = available[self._index % len(available)]
                self._index += 1
            elif self.strategy == self.STRATEGY_LEAST_USED:
                key = min(available, key=lambda k: self._used_count[k])
            else:
                key = available[0]

            self._used_count[key] = self._used_count.get(key, 0) + 1
            return key

    def mark_failed(self, api_key: str, status_code: int | None = None):
        ttl = {
            401: 300,
            429: 3600,
        }.get(status_code or 0, 600)
        with self._lock:
            self._cooldown_until[api_key] = time.time() + ttl


class LLMProvider:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 64000,
        temperature: float = 0.7,
        timeout_ms: int = 60000,
        credential_pool: CredentialPool | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout_ms = timeout_ms
        self.credential_pool = credential_pool

    def _build_kwargs(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> tuple[dict, str | None]:
        api_key = self.api_key
        if self.credential_pool:
            pool_key = self.credential_pool.get_key()
            if pool_key:
                api_key = pool_key

        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout_ms / 1000,
        )
        if api_key:
            kwargs["api_key"] = api_key
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if tools:
            kwargs["tools"] = tools

        return kwargs, api_key

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        start = time.time()
        kwargs, used_key = self._build_kwargs(messages, tools)

        try:
            response = litellm.completion(**kwargs)
            choice = response.choices[0]
            duration = (time.time() - start) * 1000

            return LLMResponse(
                content=choice.message.content,
                tool_calls=(
                    [tc.model_dump() for tc in choice.message.tool_calls]
                    if choice.message.tool_calls else None
                ),
                usage=dict(response.usage) if response.usage else None,
                model=response.model,
                duration_ms=duration,
                raw=response,
            )
        except litellm.RateLimitError as e:
            if self.credential_pool and used_key:
                self.credential_pool.mark_failed(used_key, 429)
            raise LLMRateLimitError(
                f"速率限制: {e}", retry_after=60,
            ) from e
        except litellm.AuthenticationError as e:
            if self.credential_pool and used_key:
                self.credential_pool.mark_failed(used_key, 401)
            raise LLMConnectionError(f"认证失败: {e}") from e
        except litellm.APIConnectionError as e:
            raise LLMConnectionError(f"连接失败: {e}") from e
        except Exception as e:
            duration = (time.time() - start) * 1000
            if self.credential_pool and used_key:
                status = getattr(e, "status_code", None)
                self.credential_pool.mark_failed(used_key, status)
            raise LLMError(f"LLM 调用异常: {e}") from e

    async def chat_async(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        start = time.time()
        kwargs, used_key = self._build_kwargs(messages, tools)

        try:
            response = await litellm.acompletion(**kwargs)
            choice = response.choices[0]
            duration = (time.time() - start) * 1000

            return LLMResponse(
                content=choice.message.content,
                tool_calls=(
                    [tc.model_dump() for tc in choice.message.tool_calls]
                    if choice.message.tool_calls else None
                ),
                usage=dict(response.usage) if response.usage else None,
                model=response.model,
                duration_ms=duration,
                raw=response,
            )
        except litellm.RateLimitError as e:
            if self.credential_pool and used_key:
                self.credential_pool.mark_failed(used_key, 429)
            raise LLMRateLimitError(
                f"速率限制: {e}", retry_after=60,
            ) from e
        except litellm.AuthenticationError as e:
            if self.credential_pool and used_key:
                self.credential_pool.mark_failed(used_key, 401)
            raise LLMConnectionError(f"认证失败: {e}") from e
        except litellm.APIConnectionError as e:
            raise LLMConnectionError(f"连接失败: {e}") from e
        except Exception as e:
            if self.credential_pool and used_key:
                status = getattr(e, "status_code", None)
                self.credential_pool.mark_failed(used_key, status)
            raise LLMError(f"LLM 异步调用异常: {e}") from e

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式 LLM 调用。

        使用 litellm.acompletion(stream=True) 获取 token 级流，
        将 token 缓冲至 800-1200 字符块后 yield StreamChunk(kind="text")。
        工具调用在所有 chunk 完成后一次性发出。
        最后 yield StreamChunk(kind="done") 含 usage。
        """
        kwargs, used_key = self._build_kwargs(messages, tools)
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}

        try:
            response = await litellm.acompletion(**kwargs)
        except litellm.RateLimitError as e:
            if self.credential_pool and used_key:
                self.credential_pool.mark_failed(used_key, 429)
            yield StreamChunk(kind="error", error=f"速率限制: {e}")
            return
        except litellm.AuthenticationError as e:
            if self.credential_pool and used_key:
                self.credential_pool.mark_failed(used_key, 401)
            yield StreamChunk(kind="error", error=f"认证失败: {e}")
            return
        except litellm.APIConnectionError as e:
            yield StreamChunk(kind="error", error=f"连接失败: {e}")
            return
        except Exception as e:
            if self.credential_pool and used_key:
                status = getattr(e, "status_code", None)
                self.credential_pool.mark_failed(used_key, status)
            yield StreamChunk(kind="error", error=f"LLM 流式调用异常: {e}")
            return

        # 流式消费 token → 块缓冲（800-1200 字符块）
        buffer: list[str] = []
        buffer_len = 0
        final_usage: dict | None = None
        final_model = ""
        tool_call_acc: dict[int, dict] = {}  # index → partial tool_call

        async for chunk in response:
            # usage chunk（stream_options=include_usage 时单独出现）
            if hasattr(chunk, "usage") and chunk.usage:
                final_usage = dict(chunk.usage)

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            final_model = chunk.model or final_model

            delta = choice.delta if hasattr(choice, "delta") else None
            if delta is None:
                continue

            # 文本内容
            if delta.content:
                buffer.append(delta.content)
                buffer_len += len(delta.content)
                finish = getattr(choice, "finish_reason", None)
                # >= 800 chars 或遇到 finish_reason 时 flush
                if buffer_len >= 800 or finish:
                    yield StreamChunk(
                        kind="text",
                        content="".join(buffer),
                        model=final_model,
                    )
                    buffer.clear()
                    buffer_len = 0

            # 工具调用（累积）
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if hasattr(tc, "index") else 0
                    if idx not in tool_call_acc:
                        tool_call_acc[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if hasattr(tc, "id") and tc.id:
                        tool_call_acc[idx]["id"] = tc.id
                    if hasattr(tc, "function"):
                        if hasattr(tc.function, "name") and tc.function.name:
                            tool_call_acc[idx]["function"]["name"] += tc.function.name
                        if hasattr(tc.function, "arguments") and tc.function.arguments:
                            tool_call_acc[idx]["function"]["arguments"] += tc.function.arguments

        # flush 残留 buffer
        if buffer:
            yield StreamChunk(
                kind="text",
                content="".join(buffer),
                model=final_model,
            )

        # 发出累积的工具调用
        if tool_call_acc:
            accumulated_tool_calls = [
                tool_call_acc[i] for i in sorted(tool_call_acc)
            ]
            yield StreamChunk(
                kind="tool_calls",
                tool_calls=accumulated_tool_calls,
                model=final_model,
            )

        yield StreamChunk(
            kind="done",
            usage=final_usage,
            model=final_model,
        )
