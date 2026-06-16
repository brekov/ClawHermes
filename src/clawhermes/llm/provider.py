"""
ClawHermes - LLM Provider 抽象层
封装 litellm，统一调用接口，支持多凭证池
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import litellm

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 调用结果"""
    content: str | None
    tool_calls: list[dict] | None = None
    usage: dict | None = None
    model: str = ""
    duration_ms: float = 0.0
    raw: Any = None


class CredentialPool:
    """多凭证池（来自 Hermes）- 支持故障转移"""

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
        """获取当前可用的 API key"""
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
        """标记 key 失败，设置冷却时间"""
        ttl = {
            401: 300,    # 5 分钟（token 过期）
            429: 3600,   # 1 小时（速率限制）
        }.get(status_code, 600)  # 默认 10 分钟
        with self._lock:
            self._cooldown_until[api_key] = time.time() + ttl


class LLMProvider:
    """LLM 提供商标一接口"""

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

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """调用 LLM，统一返回格式"""
        start = time.time()
        api_key = self.api_key
        if self.credential_pool:
            api_key = self.credential_pool.get_key() or api_key

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
        except Exception as e:
            duration = (time.time() - start) * 1000
            if self.credential_pool and api_key:
                status = getattr(e, "status_code", None)
                self.credential_pool.mark_failed(api_key, status)
            raise

    def chat_async(self, messages, tools=None):
        """异步调用（TODO: 用 litellm.acompletion）"""
        return self.chat(messages, tools)
