"""
ClawHermes - LLM Provider 测试

覆盖 CredentialPool 各策略、冷却机制，LLMProvider 的 chat/chat_async/chat_stream
（通过 mock litellm 避免真实 API 调用）。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from clawhermes.agent.exceptions import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
)
from clawhermes.llm.provider import (
    CredentialPool,
    LLMProvider,
    LLMResponse,
    StreamChunk,
)

# ============================================================
# 辅助：构造 mock litellm 响应对象
# ============================================================

def _make_message(content="hello", tool_calls=None):
    """构造 litellm response.choices[0].message"""
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return msg


def _make_choice(message=None, finish_reason=None):
    """构造 litellm response.choices[0]"""
    if message is None:
        message = _make_message()
    return SimpleNamespace(message=message, finish_reason=finish_reason)


def _make_response(content="hello", tool_calls=None, usage=None, model="test-model"):
    """构造同步 litellm response"""
    if tool_calls:
        tc_objs = [SimpleNamespace(model_dump=lambda tc=tc: tc) for tc in tool_calls]
        message = _make_message(content=None, tool_calls=tc_objs)
    else:
        message = _make_message(content=content)

    choice = _make_choice(message=message, finish_reason="stop" if content else None)
    return SimpleNamespace(
        choices=[choice],
        usage=usage,
        model=model,
    )


def _make_delta(content=None, tool_calls=None):
    """构造 streaming chunk.choices[0].delta"""
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _make_stream_chunk(
    content=None,
    tool_calls=None,
    finish_reason=None,
    usage=None,
    model="stream-model",
    has_choices=True,
):
    """构造单个流式 chunk"""
    if has_choices:
        delta = _make_delta(content=content, tool_calls=tool_calls)
        choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
        choices = [choice]
    else:
        choices = []
    return SimpleNamespace(choices=choices, usage=usage, model=model)


class _AsyncStream:
    """模拟 litellm.acompletion(stream=True) 返回的异步迭代器"""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


# ============================================================
# CredentialPool 策略测试
# ============================================================

class TestCredentialPoolRoundRobin:
    def test_round_robin_cycles_through_keys(self):
        pool = CredentialPool(["a", "b", "c"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        keys = [pool.get_key() for _ in range(3)]
        assert keys == ["a", "b", "c"]

    def test_round_robin_wraps_around(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        keys = [pool.get_key() for _ in range(4)]
        assert keys == ["a", "b", "a", "b"]

    def test_round_robin_increments_used_count(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.get_key()
        pool.get_key()
        assert pool._used_count["a"] == 1
        assert pool._used_count["b"] == 1


class TestCredentialPoolRandom:
    def test_random_returns_valid_key(self):
        pool = CredentialPool(["k1", "k2", "k3"], strategy=CredentialPool.STRATEGY_RANDOM)
        key = pool.get_key()
        assert key in {"k1", "k2", "k3"}

    def test_random_returns_from_available_only(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_RANDOM)
        pool.mark_failed("a", 429)
        # b 仍可用
        for _ in range(5):
            assert pool.get_key() == "b"

    def test_random_distribution_includes_all_keys(self):
        """随机策略在多次调用后应覆盖所有 key（验证修复后的 bug）"""
        pool = CredentialPool(["x", "y", "z"], strategy=CredentialPool.STRATEGY_RANDOM)
        seen = {pool.get_key() for _ in range(50)}
        # 50 次调用后，3 个 key 应该都被选中过
        assert seen == {"x", "y", "z"}

    def test_random_with_single_key(self):
        pool = CredentialPool(["only"], strategy=CredentialPool.STRATEGY_RANDOM)
        assert pool.get_key() == "only"


class TestCredentialPoolLeastUsed:
    def test_least_used_picks_min_count(self):
        pool = CredentialPool(["a", "b", "c"], strategy=CredentialPool.STRATEGY_LEAST_USED)
        # 人为设置使用次数
        pool._used_count = {"a": 5, "b": 1, "c": 10}
        assert pool.get_key() == "b"

    def test_least_used_tie_returns_first_min(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_LEAST_USED)
        # 都是 0，min 返回第一个
        assert pool.get_key() == "a"

    def test_least_used_updates_count(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_LEAST_USED)
        pool._used_count = {"a": 3, "b": 1}
        pool.get_key()  # 选 b，b 计数 +1
        assert pool._used_count["b"] == 2
        pool.get_key()  # b=2 < a=3，还是选 b
        assert pool._used_count["b"] == 3


class TestCredentialPoolFillFirst:
    def test_fill_first_returns_first_available(self):
        pool = CredentialPool(["a", "b", "c"], strategy=CredentialPool.STRATEGY_FILL_FIRST)
        assert pool.get_key() == "a"
        assert pool.get_key() == "a"

    def test_fill_first_skips_cooldown(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_FILL_FIRST)
        pool.mark_failed("a", 429)
        assert pool.get_key() == "b"


class TestCredentialPoolCooldown:
    def test_mark_failed_429_long_cooldown(self):
        pool = CredentialPool(["a"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("a", 429)
        assert pool.get_key() is None  # 全部冷却中

    def test_mark_failed_401_cooldown(self):
        pool = CredentialPool(["a"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("a", 401)
        assert pool.get_key() is None

    def test_mark_failed_other_status(self):
        pool = CredentialPool(["a"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("a", 500)
        assert pool.get_key() is None

    def test_mark_failed_none_status(self):
        pool = CredentialPool(["a"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("a", None)
        assert pool.get_key() is None

    def test_all_keys_cooldown_returns_none(self):
        pool = CredentialPool(["a", "b"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("a", 429)
        pool.mark_failed("b", 401)
        assert pool.get_key() is None

    def test_cooldown_expires(self):
        """冷却到期后 key 恢复可用"""
        import time
        from unittest.mock import patch as _patch

        pool = CredentialPool(["a"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("a", 429)  # 3600s cooldown
        assert pool.get_key() is None

        # 模拟时间前进 3700 秒
        future = time.time() + 3700
        with _patch("time.time", return_value=future):
            assert pool.get_key() == "a"

    def test_partial_cooldown(self):
        """部分 key 冷却时，其余 key 仍可用"""
        pool = CredentialPool(["a", "b", "c"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("b", 429)
        available = set()
        for _ in range(4):
            k = pool.get_key()
            if k:
                available.add(k)
        assert "b" not in available
        assert "a" in available
        assert "c" in available


# ============================================================
# LLMProvider._build_kwargs 测试
# ============================================================

class TestBuildKwargs:
    def test_basic_kwargs(self):
        provider = LLMProvider(model="test/model", api_key="sk-test")
        kwargs, key = provider._build_kwargs([{"role": "user", "content": "hi"}])
        assert kwargs["model"] == "test/model"
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 64000
        assert key == "sk-test"

    def test_kwargs_with_base_url(self):
        provider = LLMProvider(model="m", api_key="k", base_url="https://api.test.com")
        kwargs, _ = provider._build_kwargs([])
        assert kwargs["api_base"] == "https://api.test.com"

    def test_kwargs_with_tools(self):
        provider = LLMProvider(model="m", api_key="k")
        tools = [{"type": "function", "function": {"name": "f"}}]
        kwargs, _ = provider._build_kwargs([], tools=tools)
        assert kwargs["tools"] == tools

    def test_kwargs_with_credential_pool(self):
        pool = CredentialPool(["pool-key"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        provider = LLMProvider(model="m", api_key="fallback", credential_pool=pool)
        kwargs, key = provider._build_kwargs([])
        assert kwargs["api_key"] == "pool-key"
        assert key == "pool-key"

    def test_kwargs_pool_returns_none_falls_back(self):
        """pool 所有 key 冷却时回退到 self.api_key"""
        pool = CredentialPool(["pool-key"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        pool.mark_failed("pool-key", 429)
        provider = LLMProvider(model="m", api_key="fallback", credential_pool=pool)
        kwargs, key = provider._build_kwargs([])
        assert kwargs["api_key"] == "fallback"
        assert key == "fallback"

    def test_kwargs_no_api_key(self):
        provider = LLMProvider(model="m")
        kwargs, key = provider._build_kwargs([])
        assert "api_key" not in kwargs
        assert key is None

    def test_timeout_converted_to_seconds(self):
        provider = LLMProvider(model="m", api_key="k", timeout_ms=30000)
        kwargs, _ = provider._build_kwargs([])
        assert kwargs["timeout"] == 30.0


# ============================================================
# LLMProvider.chat 同步测试
# ============================================================

class TestChatSync:
    def test_chat_success_text(self):
        provider = LLMProvider(model="m", api_key="k")
        mock_resp = _make_response(content="你好")
        with patch("clawhermes.llm.provider.litellm.completion", return_value=mock_resp):
            result = provider.chat([{"role": "user", "content": "hi"}])
        assert isinstance(result, LLMResponse)
        assert result.content == "你好"
        assert result.model == "test-model"
        assert result.duration_ms >= 0

    def test_chat_success_with_tool_calls(self):
        provider = LLMProvider(model="m", api_key="k")
        tcs = [{"id": "tc1", "function": {"name": "f", "arguments": "{}"}}]
        mock_resp = _make_response(content=None, tool_calls=tcs)
        with patch("clawhermes.llm.provider.litellm.completion", return_value=mock_resp):
            result = provider.chat([{"role": "user", "content": "hi"}])
        assert result.content is None
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "tc1"

    def test_chat_success_with_usage(self):
        provider = LLMProvider(model="m", api_key="k")
        mock_resp = _make_response(content="ok", usage={"total_tokens": 42})
        with patch("clawhermes.llm.provider.litellm.completion", return_value=mock_resp):
            result = provider.chat([{"role": "user", "content": "hi"}])
        assert result.usage is not None
        assert result.usage["total_tokens"] == 42

    def test_chat_rate_limit_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.RateLimitError("rate limited", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=err):
            with pytest.raises(LLMRateLimitError) as exc_info:
                provider.chat([{"role": "user", "content": "hi"}])
        assert exc_info.value.retry_after == 60

    def test_chat_rate_limit_marks_pool_failed(self):
        pool = CredentialPool(["pk"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        provider = LLMProvider(model="m", api_key="k", credential_pool=pool)
        err = litellm.RateLimitError("rate limited", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=err):
            with pytest.raises(LLMRateLimitError):
                provider.chat([{"role": "user", "content": "hi"}])
        # pool key 应该被标记失败
        assert pool.get_key() is None

    def test_chat_auth_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.AuthenticationError("bad key", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=err):
            with pytest.raises(LLMConnectionError):
                provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_auth_error_marks_pool_failed(self):
        pool = CredentialPool(["pk"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        provider = LLMProvider(model="m", api_key="k", credential_pool=pool)
        err = litellm.AuthenticationError("bad key", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=err):
            with pytest.raises(LLMConnectionError):
                provider.chat([{"role": "user", "content": "hi"}])
        assert pool.get_key() is None

    def test_chat_connection_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.APIConnectionError("conn fail", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=err):
            with pytest.raises(LLMConnectionError):
                provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_generic_error(self):
        provider = LLMProvider(model="m", api_key="k")
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=RuntimeError("boom")):
            with pytest.raises(LLMError):
                provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_generic_error_marks_pool_failed(self):
        pool = CredentialPool(["pk"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        provider = LLMProvider(model="m", api_key="k", credential_pool=pool)
        err = RuntimeError("boom")
        err.status_code = 500  # type: ignore[attr-defined]
        with patch("clawhermes.llm.provider.litellm.completion", side_effect=err):
            with pytest.raises(LLMError):
                provider.chat([{"role": "user", "content": "hi"}])
        assert pool.get_key() is None


# ============================================================
# LLMProvider.chat_async 异步测试
# ============================================================

class TestChatAsync:
    @pytest.mark.asyncio
    async def test_chat_async_success(self):
        provider = LLMProvider(model="m", api_key="k")
        mock_resp = _make_response(content="异步响应")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            result = await provider.chat_async([{"role": "user", "content": "hi"}])
        assert result.content == "异步响应"

    @pytest.mark.asyncio
    async def test_chat_async_with_tool_calls(self):
        provider = LLMProvider(model="m", api_key="k")
        tcs = [{"id": "tc2", "function": {"name": "g", "arguments": "{}"}}]
        mock_resp = _make_response(content=None, tool_calls=tcs)
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            result = await provider.chat_async([{"role": "user", "content": "hi"}])
        assert result.tool_calls is not None
        assert result.tool_calls[0]["id"] == "tc2"

    @pytest.mark.asyncio
    async def test_chat_async_rate_limit(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.RateLimitError("rl", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            with pytest.raises(LLMRateLimitError):
                await provider.chat_async([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_async_auth_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.AuthenticationError("auth", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            with pytest.raises(LLMConnectionError):
                await provider.chat_async([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_async_connection_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.APIConnectionError("conn", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            with pytest.raises(LLMConnectionError):
                await provider.chat_async([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_async_generic_error(self):
        provider = LLMProvider(model="m", api_key="k")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=RuntimeError("x"))):
            with pytest.raises(LLMError):
                await provider.chat_async([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_async_rate_limit_marks_pool(self):
        pool = CredentialPool(["pk"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        provider = LLMProvider(model="m", api_key="k", credential_pool=pool)
        err = litellm.RateLimitError("rl", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            with pytest.raises(LLMRateLimitError):
                await provider.chat_async([{"role": "user", "content": "hi"}])
        assert pool.get_key() is None


# ============================================================
# LLMProvider.chat_stream 流式测试
# ============================================================

class TestChatStream:
    @pytest.mark.asyncio
    async def test_stream_text_only(self):
        provider = LLMProvider(model="m", api_key="k")
        chunks = [
            _make_stream_chunk(content="Hello ", finish_reason=None),
            _make_stream_chunk(content="World", finish_reason="stop"),
            _make_stream_chunk(usage={"total_tokens": 10}, has_choices=False),
        ]
        mock_resp = _AsyncStream(chunks)
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)

        # 至少有 text + done
        kinds = [c.kind for c in results]
        assert "text" in kinds
        assert kinds[-1] == "done"
        text_chunk = next(c for c in results if c.kind == "text")
        assert "Hello" in text_chunk.content
        assert "World" in text_chunk.content
        done_chunk = results[-1]
        assert done_chunk.usage is not None

    @pytest.mark.asyncio
    async def test_stream_buffer_flush_at_800(self):
        """超过 800 字符的 buffer 应自动 flush"""
        provider = LLMProvider(model="m", api_key="k")
        long_text = "A" * 850
        chunks = [
            _make_stream_chunk(content=long_text, finish_reason=None),
            _make_stream_chunk(content="tail", finish_reason="stop"),
        ]
        mock_resp = _AsyncStream(chunks)
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)

        text_chunks = [c for c in results if c.kind == "text"]
        # 850 字符应触发一次 flush（>= 800），然后 "tail" 在 finish 时 flush
        assert len(text_chunks) >= 2
        assert len(text_chunks[0].content) >= 800

    @pytest.mark.asyncio
    async def test_stream_tool_calls_accumulated(self):
        provider = LLMProvider(model="m", api_key="k")
        tc1 = SimpleNamespace(
            index=0, id="call_1", type="function",
            function=SimpleNamespace(name="get_time", arguments=""),
        )
        tc2 = SimpleNamespace(
            index=0, id=None, type=None,
            function=SimpleNamespace(name=None, arguments='{"tz": "UTC"}'),
        )
        chunks = [
            _make_stream_chunk(tool_calls=[tc1], finish_reason=None),
            _make_stream_chunk(tool_calls=[tc2], finish_reason="tool_calls"),
        ]
        mock_resp = _AsyncStream(chunks)
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "几点了"}]):
                results.append(chunk)

        kinds = [c.kind for c in results]
        assert "tool_calls" in kinds
        tc_chunk = next(c for c in results if c.kind == "tool_calls")
        assert len(tc_chunk.tool_calls) == 1
        assert tc_chunk.tool_calls[0]["id"] == "call_1"
        assert tc_chunk.tool_calls[0]["function"]["name"] == "get_time"
        assert tc_chunk.tool_calls[0]["function"]["arguments"] == '{"tz": "UTC"}'
        assert kinds[-1] == "done"

    @pytest.mark.asyncio
    async def test_stream_rate_limit_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.RateLimitError("rl", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)
        assert len(results) == 1
        assert results[0].kind == "error"
        assert "速率限制" in results[0].error

    @pytest.mark.asyncio
    async def test_stream_auth_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.AuthenticationError("bad", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)
        assert len(results) == 1
        assert results[0].kind == "error"
        assert "认证失败" in results[0].error

    @pytest.mark.asyncio
    async def test_stream_connection_error(self):
        provider = LLMProvider(model="m", api_key="k")
        err = litellm.APIConnectionError("conn", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)
        assert len(results) == 1
        assert results[0].kind == "error"
        assert "连接失败" in results[0].error

    @pytest.mark.asyncio
    async def test_stream_generic_error(self):
        provider = LLMProvider(model="m", api_key="k")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=RuntimeError("oops"))):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)
        assert len(results) == 1
        assert results[0].kind == "error"
        assert "异常" in results[0].error

    @pytest.mark.asyncio
    async def test_stream_rate_error_marks_pool(self):
        pool = CredentialPool(["pk"], strategy=CredentialPool.STRATEGY_ROUND_ROBIN)
        provider = LLMProvider(model="m", api_key="k", credential_pool=pool)
        err = litellm.RateLimitError("rl", "openai", "m")
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(side_effect=err)):
            async for _ in provider.chat_stream([{"role": "user", "content": "hi"}]):
                pass
        assert pool.get_key() is None

    @pytest.mark.asyncio
    async def test_stream_empty_choices_skipped(self):
        """choices 为空的 chunk（如 usage-only chunk）应被跳过"""
        provider = LLMProvider(model="m", api_key="k")
        chunks = [
            _make_stream_chunk(usage={"total_tokens": 5}, has_choices=False),
            _make_stream_chunk(content="text", finish_reason="stop"),
        ]
        mock_resp = _AsyncStream(chunks)
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)
        # usage chunk 不产生 text，只有 content chunk 产生 text
        text_chunks = [c for c in results if c.kind == "text"]
        assert len(text_chunks) == 1
        assert text_chunks[0].content == "text"

    @pytest.mark.asyncio
    async def test_stream_delta_none_skipped(self):
        """delta 为 None 的 choice 应被跳过"""
        provider = LLMProvider(model="m", api_key="k")
        chunk_no_delta = SimpleNamespace(
            choices=[SimpleNamespace(delta=None, finish_reason=None)],
            usage=None,
            model="m",
        )
        chunks = [
            chunk_no_delta,
            _make_stream_chunk(content="real", finish_reason="stop"),
        ]
        mock_resp = _AsyncStream(chunks)
        with patch("clawhermes.llm.provider.litellm.acompletion", new=AsyncMock(return_value=mock_resp)):
            results = []
            async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}]):
                results.append(chunk)
        text_chunks = [c for c in results if c.kind == "text"]
        assert len(text_chunks) == 1


class TestStreamChunkDataclass:
    def test_stream_chunk_defaults(self):
        chunk = StreamChunk(kind="text")
        assert chunk.kind == "text"
        assert chunk.content == ""
        assert chunk.tool_calls is None
        assert chunk.usage is None
        assert chunk.model == ""
        assert chunk.error == ""

    def test_llm_response_defaults(self):
        resp = LLMResponse(content="hi")
        assert resp.content == "hi"
        assert resp.tool_calls is None
        assert resp.usage is None
        assert resp.model == ""
        assert resp.duration_ms == 0.0
        assert resp.raw is None
