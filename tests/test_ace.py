"""
ClawHermes - ACE 自适应上下文引擎测试
"""
from __future__ import annotations

from clawhermes.agent.ace import (
    STRATEGIES,
    AdaptiveContextEngine,
    CompressionStrategy,
    ConversationClassifier,
    ConversationType,
)
from clawhermes.agent.context import NoopCompressor


class TestConversationClassifier:
    def test_code_detection(self):
        messages = [
            {"role": "user", "content": "帮我写一个 Python 函数处理数据"},
            {"role": "assistant", "content": "好的，代码：\n```python\ndef process(data):\n    return data\n```"},
        ]
        assert ConversationClassifier.classify(messages) == ConversationType.CODE

    def test_qa_detection(self):
        messages = [
            {"role": "user", "content": "What is the difference between REST and GraphQL?"},
            {"role": "assistant", "content": "REST uses multiple endpoints."},
        ]
        assert ConversationClassifier.classify(messages) == ConversationType.QA

    def test_creative_detection(self):
        messages = [
            {"role": "user", "content": "Write a story about a robot learning to paint"},
        ]
        assert ConversationClassifier.classify(messages) == ConversationType.CREATIVE

    def test_empty_messages_returns_mixed(self):
        assert ConversationClassifier.classify([]) == ConversationType.MIXED

    def test_mixed_content(self):
        messages = [{"role": "user", "content": "hello how are you"}]
        assert ConversationClassifier.classify(messages) == ConversationType.MIXED

    def test_code_with_traceback(self):
        messages = [
            {"role": "user", "content": "Error: Traceback (most recent call last): ValueError"},
        ]
        assert ConversationClassifier.classify(messages) == ConversationType.CODE


class TestCompressionStrategy:
    def test_strategies_exist_for_all_types(self):
        for ct in ConversationType:
            assert ct in STRATEGIES

    def test_code_strategy_keeps_code(self):
        s = STRATEGIES[ConversationType.CODE]
        assert s.keep_code_blocks is True
        assert s.keep_references is False

    def test_qa_strategy_keeps_references(self):
        s = STRATEGIES[ConversationType.QA]
        assert s.keep_references is True

    def test_creative_strategy_keeps_style(self):
        s = STRATEGIES[ConversationType.CREATIVE]
        assert s.keep_style is True

    def test_strategy_dataclass_defaults(self):
        s = CompressionStrategy(name="test")
        assert s.name == "test"
        assert s.keep_code_blocks is True
        assert s.max_summary_tokens == 4000


class TestAdaptiveContextEngine:
    def test_create_with_noop(self):
        ace = AdaptiveContextEngine(NoopCompressor())
        assert ace.should_compress() is False
        assert ace.last_strategy is None

    def test_compress_no_need(self):
        ace = AdaptiveContextEngine(NoopCompressor())
        msgs = [{"role": "user", "content": "hi"}]
        result = ace.compress(msgs, current_tokens=10)
        assert result == msgs

    def test_get_strategy(self):
        s = AdaptiveContextEngine.get_strategy(ConversationType.CODE)
        assert s.name == "code"

    def test_protect_blocks(self):
        strategy = STRATEGIES[ConversationType.CODE]
        messages = [{"role": "assistant", "content": "Code:\n```python\nprint(1)\n```"}]
        result = AdaptiveContextEngine._protect_blocks(messages, strategy)
        assert "PROTECTED_BLOCK" in result[0]["content"]

    def test_compress_with_detection(self):
        class FakeCompressor:
            protect_first_n = 1
            protect_last_n = 1
            _summaries: list[str] = []

            def should_compress(self, tokens=None):
                return True

            def _summarize(self, messages, focus):
                self._summaries.append(focus)
                return f"Summary: {focus}"

        fc = FakeCompressor()
        ace = AdaptiveContextEngine(fc)

        msgs = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "def handler(event): return event"},
            {"role": "assistant", "content": "your function..."},
            {"role": "user", "content": "also what about"},
            {"role": "assistant", "content": "edge cases"},
        ]

        result = ace.compress(msgs, current_tokens=5000)
        assert len(result) < len(msgs)
        assert ace.last_strategy is not None
        assert ace.last_strategy.name == "code"
        assert "code" in fc._summaries[0]
