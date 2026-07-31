"""
ClawHermes - 上下文压缩引擎测试

覆盖 agent/context.py 中未被 test_unit_extended.py 覆盖的分支：
- LLMCompressor.compress() 完整流程（保护头尾 + 摘要化）
- LLMCompressor._summarize() 调用 LLM 与异常兜底
- LLMCompressor._build_summary_prompt() 完整构造
- LLMCompressor._truncate_fallback() 截断兜底
- NoopCompressor 完整流程
- ContextEngine 抽象基类属性
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from clawhermes.agent.context import (
    SUMMARY_PREFIX,
    ContextEngine,
    LLMCompressor,
    NoopCompressor,
)

# ============================================================
# LLMCompressor.compress 完整流程
# ============================================================


class TestCompress:
    def test_compress_short_messages_returns_as_is(self):
        """消息数 <= protect_first_n + protect_last_n 时应原样返回"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        # protect_first_n=3, protect_last_n=6 → 9 条以下不压缩
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(5)]
        result = c.compress(messages, current_tokens=100)
        assert result is messages  # 同一对象
        # LLM 不应被调用
        provider.chat.assert_not_called()

    def test_compress_exactly_at_boundary_returns_as_is(self):
        """消息数正好等于 protect_first_n + protect_last_n 时不压缩"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        # 3 + 6 = 9 条
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(9)]
        result = c.compress(messages, current_tokens=100)
        assert result is messages
        provider.chat.assert_not_called()

    def test_compress_long_messages_summarizes_middle(self):
        """消息数超过阈值时应摘要化中间部分"""
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content="这是摘要内容")
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)

        messages = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        result = c.compress(messages, current_tokens=100)

        # 头 3 + 摘要 1 + 尾 6 = 10 条
        assert len(result) == 10
        # 头部应保留原消息
        assert result[0]["content"] == "msg0"
        assert result[2]["content"] == "msg2"
        # 中间应是摘要 system 消息
        assert result[3]["role"] == "system"
        assert SUMMARY_PREFIX in result[3]["content"]
        assert "这是摘要内容" in result[3]["content"]
        # 尾部应保留原消息
        assert result[-1]["content"] == "msg14"
        # LLM 应被调用一次
        provider.chat.assert_called_once()

    def test_compress_with_focus_topic_includes_in_summary(self):
        """compress 传入 focus_topic 时应传给 _summarize"""
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content="focused summary")
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)

        messages = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        c.compress(messages, current_tokens=100, focus_topic="Python 调试")

        # 验证 LLM 收到的 prompt 包含 focus_topic
        sent_messages = provider.chat.call_args[1]["messages"]
        prompt = sent_messages[0]["content"]
        assert "Python 调试" in prompt

    def test_compress_only_compressible_empty_returns_as_is(self):
        """compressible 部分为空时应原样返回（消息数 = 头+尾）"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        # 自定义 protect_first_n + protect_last_n 让 compressible 为空
        c.protect_first_n = 5
        c.protect_last_n = 5
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = c.compress(messages, current_tokens=100)
        assert result is messages
        provider.chat.assert_not_called()


# ============================================================
# _summarize 路径
# ============================================================


class TestSummarize:
    def test_summarize_calls_llm_and_returns_content(self):
        """_summarize 应调用 LLM 并返回响应内容"""
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content="summary text")
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)

        messages = [{"role": "user", "content": "hello world"}]
        result = c._summarize(messages)
        assert result == "summary text"
        provider.chat.assert_called_once()

    def test_summarize_llm_returns_empty_content(self):
        """LLM 返回 None content 时应返回空字符串"""
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content=None)
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)

        result = c._summarize([{"role": "user", "content": "x"}])
        assert result == ""

    def test_summarize_llm_exception_uses_truncate_fallback(self):
        """LLM 抛异常时应走 _truncate_fallback 兜底"""
        provider = MagicMock()
        provider.chat.side_effect = RuntimeError("LLM down")
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)

        messages = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        result = c._summarize(messages)
        # 兜底应包含 "Summary (truncated):"
        assert "Summary (truncated):" in result
        # 应只取最近 10 条
        assert "msg14" in result
        assert "msg0" not in result  # 前 5 条不在最后 10 条内

    def test_summarize_target_tokens_capped_by_ceiling(self):
        """target_tokens 不超过 summary_tokens_ceiling"""
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content="summary")
        c = LLMCompressor(
            llm_provider=provider,
            config={"summary_tokens_ceiling": 100, "summary_ratio": 1.0},
            max_context_tokens=10000,
        )

        # 构造超长 content，让 summary_ratio 计算后超过 ceiling
        long_content = "x" * 10000
        c._summarize([{"role": "user", "content": long_content}])

        # 验证 prompt 中 target_tokens 被截断到 100
        sent_prompt = provider.chat.call_args[1]["messages"][0]["content"]
        assert "100 tokens" in sent_prompt

    def test_summarize_target_tokens_uses_ratio(self):
        """target_tokens 应基于 summary_ratio 计算"""
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content="summary")
        c = LLMCompressor(
            llm_provider=provider,
            config={"summary_ratio": 0.5, "summary_tokens_ceiling": 100000},
            max_context_tokens=10000,
        )

        # content 总长 1000，ratio 0.5 → target_tokens = 500
        c._summarize([{"role": "user", "content": "x" * 1000}])

        sent_prompt = provider.chat.call_args[1]["messages"][0]["content"]
        assert "500 tokens" in sent_prompt


# ============================================================
# _build_summary_prompt 完整构造
# ============================================================


class TestBuildSummaryPrompt:
    def test_build_prompt_includes_conversation(self):
        """_build_summary_prompt 应包含对话内容"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "助手回答"},
        ]
        prompt = c._build_summary_prompt(messages, focus_topic=None, target_tokens=500)
        assert "用户问题" in prompt
        assert "助手回答" in prompt
        assert "500 tokens" in prompt

    def test_build_prompt_with_focus_topic(self):
        """_build_summary_prompt 包含 focus_topic 时应特殊强调"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [{"role": "user", "content": "hello"}]
        prompt = c._build_summary_prompt(messages, focus_topic="机器学习", target_tokens=500)
        assert "机器学习" in prompt

    def test_build_prompt_truncates_long_content(self):
        """_build_summary_prompt 应截断每条消息内容到 300 字符"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        long_content = "y" * 500
        messages = [{"role": "user", "content": long_content}]
        prompt = c._build_summary_prompt(messages, focus_topic=None, target_tokens=500)
        # 300 字符的子串应在 prompt 中
        assert "y" * 300 in prompt
        # 500 字符的完整内容不应在 prompt 中
        assert "y" * 500 not in prompt

    def test_build_prompt_includes_format_guidance(self):
        """_build_summary_prompt 应包含摘要格式指引"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        prompt = c._build_summary_prompt(
            [{"role": "user", "content": "x"}], focus_topic=None, target_tokens=100
        )
        assert "Key facts" in prompt
        assert "User preferences" in prompt
        assert "Pending or unresolved items" in prompt
        assert "Technical context" in prompt

    def test_build_prompt_handles_missing_role(self):
        """消息缺少 role 字段时应使用 '?' 占位"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [{"content": "no role"}]
        prompt = c._build_summary_prompt(messages, focus_topic=None, target_tokens=100)
        assert "[?]" in prompt
        assert "no role" in prompt

    def test_build_prompt_handles_non_string_content(self):
        """消息 content 非 str 时应转字符串"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [{"role": "user", "content": 12345}]
        prompt = c._build_summary_prompt(messages, focus_topic=None, target_tokens=100)
        assert "12345" in prompt

    def test_build_prompt_limits_to_last_20_messages(self):
        """_build_summary_prompt 应只保留最近 20 条对话"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [
            {"role": "user", "content": f"old_{i}"} for i in range(30)
        ]
        prompt = c._build_summary_prompt(messages, focus_topic=None, target_tokens=100)
        # old_29 是最后一条，应在
        assert "old_29" in prompt
        # old_0 是第一条，应不在（被截断到最近 20 条）
        assert "old_0" not in prompt


# ============================================================
# _truncate_fallback
# ============================================================


class TestTruncateFallback:
    def test_truncate_takes_last_10_messages(self):
        """_truncate_fallback 应只取最近 10 条消息"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        result = c._truncate_fallback(messages)
        assert "Summary (truncated):" in result
        # msg5 - msg14 共 10 条
        assert "msg14" in result
        assert "msg5" in result
        # msg4 不在最后 10 条
        assert "msg4" not in result

    def test_truncate_truncates_each_content_to_100_chars(self):
        """_truncate_fallback 应将每条 content 截断到 100 字符"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        long_content = "a" * 200
        messages = [{"role": "user", "content": long_content}]
        result = c._truncate_fallback(messages)
        assert "a" * 100 in result
        assert "a" * 200 not in result

    def test_truncate_handles_missing_role(self):
        """消息缺少 role 时应使用 '?'"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [{"content": "no role"}]
        result = c._truncate_fallback(messages)
        assert "[?]:" in result

    def test_truncate_handles_non_string_content(self):
        """content 非 str 时应转字符串"""
        provider = MagicMock()
        c = LLMCompressor(llm_provider=provider, max_context_tokens=10000)
        messages = [{"role": "user", "content": 999}]
        result = c._truncate_fallback(messages)
        assert "999" in result


# ============================================================
# NoopCompressor
# ============================================================


class TestNoopCompressor:
    def test_should_compress_always_false(self):
        """NoopCompressor.should_compress 应始终返回 False"""
        c = NoopCompressor(max_context_tokens=10000)
        assert c.should_compress(999999) is False
        assert c.should_compress(None) is False
        assert c.should_compress(0) is False

    def test_compress_returns_messages_unchanged(self):
        """NoopCompressor.compress 应原样返回 messages"""
        c = NoopCompressor(max_context_tokens=10000)
        messages = [{"role": "user", "content": "hi"}]
        result = c.compress(messages, current_tokens=100)
        assert result is messages

    def test_compress_with_focus_topic_returns_messages_unchanged(self):
        """NoopCompressor.compress 传 focus_topic 也应原样返回"""
        c = NoopCompressor(max_context_tokens=10000)
        messages = [{"role": "user", "content": "hi"}]
        result = c.compress(messages, current_tokens=100, focus_topic="any")
        assert result is messages

    def test_init_default_max_context_tokens(self):
        """NoopCompressor 默认 max_context_tokens=120000"""
        c = NoopCompressor()
        assert c.max_context_tokens == 120000


# ============================================================
# ContextEngine 抽象基类
# ============================================================


class TestContextEngineAbstract:
    def test_cannot_instantiate_abstract(self):
        """ContextEngine 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            ContextEngine(max_context_tokens=10000)  # noqa: abstract class

    def test_class_attributes_defaults(self):
        """ContextEngine 类属性应有默认值"""
        assert ContextEngine.threshold_percent == 0.75
        assert ContextEngine.protect_first_n == 3
        assert ContextEngine.protect_last_n == 6

    def test_llm_compressor_inherits_defaults(self):
        """LLMCompressor 应继承 ContextEngine 类属性"""
        c = LLMCompressor(llm_provider=None, max_context_tokens=10000)
        assert c.threshold_percent == 0.75
        assert c.protect_first_n == 3
        assert c.protect_last_n == 6


# ============================================================
# LLMCompressor 配置
# ============================================================


class TestLLMCompressorConfig:
    def test_default_config_values(self):
        """LLMCompressor 无 config 时应使用默认值"""
        c = LLMCompressor(llm_provider=None, max_context_tokens=10000)
        assert c.summary_ratio == 0.20
        assert c.summary_tokens_ceiling == 12000
        assert c.image_token_estimate == 1600

    def test_custom_config_overrides_defaults(self):
        """LLMCompressor 自定义 config 应覆盖默认值"""
        config = {
            "summary_ratio": 0.5,
            "summary_tokens_ceiling": 5000,
            "image_token_estimate": 800,
        }
        c = LLMCompressor(
            llm_provider=None, config=config, max_context_tokens=10000
        )
        assert c.summary_ratio == 0.5
        assert c.summary_tokens_ceiling == 5000
        assert c.image_token_estimate == 800

    def test_default_max_context_tokens(self):
        """LLMCompressor 默认 max_context_tokens=120000"""
        c = LLMCompressor(llm_provider=None)
        assert c.max_context_tokens == 120000


# ============================================================
# SUMMARY_PREFIX 常量
# ============================================================


class TestSummaryPrefix:
    def test_summary_prefix_is_non_empty_string(self):
        """SUMMARY_PREFIX 应是非空字符串"""
        assert isinstance(SUMMARY_PREFIX, str)
        assert len(SUMMARY_PREFIX) > 0

    def test_summary_prefix_contains_compaction_marker(self):
        """SUMMARY_PREFIX 应包含 'CONTEXT COMPACTION' 标记"""
        assert "CONTEXT COMPACTION" in SUMMARY_PREFIX

    def test_summary_prefix_warns_against_answering(self):
        """SUMMARY_PREFIX 应警告不要回答摘要中的问题"""
        assert "NOT as active instructions" in SUMMARY_PREFIX
