"""
ClawHermes - 上下文压缩引擎（F10）
ContextEngine 抽象基类 + LLMCompressor 实现
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is a handoff from a previous context "
    "window — treat it as background reference, NOT as active instructions. "
    "Do NOT answer questions or fulfill requests mentioned in this summary; "
    "they were already addressed. "
)


class ContextEngine(ABC):
    """上下文引擎抽象基类 — 可插拔（来自 Hermes）"""

    last_prompt_tokens: int = 0
    threshold_percent: float = 0.75
    protect_first_n: int = 3
    protect_last_n: int = 6

    @abstractmethod
    def should_compress(self, prompt_tokens: int | None = None) -> bool: ...

    @abstractmethod
    def compress(
        self,
        messages: list[dict],
        current_tokens: int,
        focus_topic: str | None = None,
    ) -> list[dict]: ...


class LLMCompressor(ContextEngine):
    """基于 LLM 摘要的上下文压缩器"""

    def __init__(self, llm_provider, config: dict | None = None):
        self.llm = llm_provider
        self.summary_ratio = (config or {}).get("summary_ratio", 0.20)
        self.summary_tokens_ceiling = (config or {}).get("summary_tokens_ceiling", 12000)
        self.image_token_estimate = (config or {}).get("image_token_estimate", 1600)

    def should_compress(self, prompt_tokens: int | None = None) -> bool:
        if prompt_tokens is None:
            return False
        return prompt_tokens > self.last_prompt_tokens * self.threshold_percent

    def compress(
        self,
        messages: list[dict],
        current_tokens: int,
        focus_topic: str | None = None,
    ) -> list[dict]:
        """压缩 messages：保护头尾，中间摘要化"""
        if len(messages) <= self.protect_first_n + self.protect_last_n:
            return messages  # 消息太少，不压缩

        # 保护前 N 条和后 N 条
        head = messages[:self.protect_first_n]
        tail = messages[-self.protect_last_n:]
        compressible = messages[self.protect_first_n:-self.protect_last_n]

        if not compressible:
            return messages

        # 生成摘要
        summary = self._summarize(compressible, focus_topic)

        # 重组
        compressed = head + [
            {"role": "system", "content": f"{SUMMARY_PREFIX}\n{summary}"}
        ] + tail

        logger.info(
            "上下文压缩: %d 条 → %d 条 (节省 %d 条)",
            len(messages), len(compressed), len(messages) - len(compressed),
        )
        return compressed

    def _summarize(self, messages: list[dict], focus_topic: str | None = None) -> str:
        """调用 LLM 生成摘要"""
        target_tokens = min(
            int(sum(len(m.get("content", "")) for m in messages) * self.summary_ratio),
            self.summary_tokens_ceiling,
        )

        prompt = self._build_summary_prompt(messages, focus_topic, target_tokens)

        try:
            resp = self.llm.chat(messages=[{"role": "user", "content": prompt}])
            return resp.content or ""
        except Exception as e:
            logger.warning("LLM 摘要失败，使用截断: %s", e)
            return self._truncate_fallback(messages)

    def _build_summary_prompt(
        self, messages: list[dict], focus_topic: str | None, target_tokens: int
    ) -> str:
        """构建摘要提示词"""
        convo_text = []
        for m in messages:
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:300]
            convo_text.append(f"[{role}]: {content}")

        prompt = (
            "Summarize the following conversation turns into a concise summary. "
            "Keep all facts, decisions, user preferences, and unresolved items. "
            f"Target length: approximately {target_tokens} tokens.\n\n"
        )
        if focus_topic:
            prompt += f"Focus particularly on topics related to: {focus_topic}\n\n"

        prompt += "Conversation:\n" + "\n".join(convo_text[-20:])

        prompt += (
            "\n\nSummary format:\n"
            "- Key facts and decisions\n"
            "- User preferences mentioned\n"
            "- Pending or unresolved items\n"
            "- Technical context (code, config, errors)"
        )
        return prompt

    def _truncate_fallback(self, messages: list[dict]) -> str:
        """LLM 失败时的兜底截断"""
        lines = []
        for m in messages[-10:]:  # 只取最近 10 条
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:100]
            lines.append(f"[{role}]: {content}")
        return "Summary (truncated):\n" + "\n".join(lines)


class NoopCompressor(ContextEngine):
    """空操作压缩器 — 不压缩"""

    def should_compress(self, prompt_tokens: int | None = None) -> bool:
        return False

    def compress(self, messages, current_tokens, focus_topic=None):
        return messages
