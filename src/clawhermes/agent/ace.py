"""
ClawHermes - 自适应上下文引擎 (ACE)
根据对话类型自动选择最优压缩策略
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ConversationType(str, Enum):
    CODE = "code"
    QA = "qa"
    CREATIVE = "creative"
    MIXED = "mixed"


@dataclass
class CompressionStrategy:
    name: str
    keep_code_blocks: bool = True
    keep_references: bool = False
    keep_style: bool = False
    max_summary_tokens: int = 4000
    summary_focus: str = "general"
    block_protect_patterns: list[str] = field(default_factory=list)


STRATEGIES: dict[ConversationType, CompressionStrategy] = {
    ConversationType.CODE: CompressionStrategy(
        name="code",
        keep_code_blocks=True,
        keep_references=False,
        keep_style=False,
        max_summary_tokens=6000,
        summary_focus="code and technical decisions",
        block_protect_patterns=[
            r"```[\s\S]*?```",
            r"def \w+.*?:",
            r"class \w+.*?:",
            r"import .*",
            r"from .* import",
        ],
    ),
    ConversationType.QA: CompressionStrategy(
        name="qa",
        keep_code_blocks=False,
        keep_references=True,
        keep_style=False,
        max_summary_tokens=4000,
        summary_focus="facts, references, and conclusions",
        block_protect_patterns=[
            r"> .*",
            r"\[.*?\]\(.*?\)",
            r"(?:https?://\S+)",
        ],
    ),
    ConversationType.CREATIVE: CompressionStrategy(
        name="creative",
        keep_code_blocks=False,
        keep_references=False,
        keep_style=True,
        max_summary_tokens=3000,
        summary_focus="narrative, style, and creative direction",
        block_protect_patterns=[
            r"#+ .*",
            r"\*\*.*?\*\*",
        ],
    ),
    ConversationType.MIXED: CompressionStrategy(
        name="mixed",
        keep_code_blocks=True,
        keep_references=True,
        keep_style=False,
        max_summary_tokens=5000,
        summary_focus="all important information",
        block_protect_patterns=[],
    ),
}


class ConversationClassifier:
    """对话类型分类器"""

    CODE_KEYWORDS = {
        "def ", "class ", "import ", "from ", "async def ",
        "function", "variable", "error", "exception", "traceback",
        "git ", "commit", "branch", "merge", "pull request",
        "pip ", "npm ", "install", "package", "dependency",
        "api", "endpoint", "route", "middleware",
    }

    CODE_PATTERNS = [
        re.compile(r"```[\s\S]*?```"),
        re.compile(r"\bdef \w+\s*\("),
        re.compile(r"\bclass \w+\s*[(:]"),
        re.compile(r"\bimport \w+"),
        re.compile(r"\bTraceback \(most recent"),
    ]

    QA_KEYWORDS = {
        "what is", "how does", "why ", "explain", "definition",
        "difference between", "compare", "versus", "vs ",
        "reference", "citation", "source", "according to",
        "pros and cons", "advantages", "disadvantages",
    }

    CREATIVE_KEYWORDS = {
        "write a story", "creative writing", "poem", "narrative",
        "brainstorm", "idea", "design", "imagine", "role play",
        "character", "plot", "style", "tone",
    }

    @classmethod
    def classify(cls, messages: list[dict]) -> ConversationType:
        text = cls._extract_text(messages).lower()
        code_score = cls._score_code(text)
        qa_score = cls._score_qa(text)
        creative_score = cls._score_creative(text)

        scores = {
            ConversationType.CODE: code_score,
            ConversationType.QA: qa_score,
            ConversationType.CREATIVE: creative_score,
        }

        max_score = max(scores.values())
        if max_score == 0:
            return ConversationType.MIXED

        best = max(scores, key=lambda k: scores[k])
        return best

    @classmethod
    def _extract_text(cls, messages: list[dict]) -> str:
        parts = []
        for m in messages[-20:]:
            content = str(m.get("content", ""))
            parts.append(content)
        return " ".join(parts)

    @classmethod
    def _score_code(cls, text: str) -> int:
        score = 0
        for kw in cls.CODE_KEYWORDS:
            if kw in text:
                score += 1
        for pattern in cls.CODE_PATTERNS:
            if pattern.search(text):
                score += 3
        code_blocks = re.findall(r"```", text)
        if len(code_blocks) >= 2:
            score += 2
        if text.count("```") >= 4:
            score += 2
        lines = text.count("\n")
        if lines > 10:
            score += 1
        return score

    @classmethod
    def _score_qa(cls, text: str) -> int:
        score = 0
        for kw in cls.QA_KEYWORDS:
            if kw in text:
                score += 1
        if "?" in text:
            score += min(text.count("?"), 3)
        return score

    @classmethod
    def _score_creative(cls, text: str) -> int:
        score = 0
        for kw in cls.CREATIVE_KEYWORDS:
            if kw in text:
                score += 1
        return score


class AdaptiveContextEngine:
    """自适应上下文引擎 — 根据对话类型选择压缩策略"""

    def __init__(self, base_compressor):
        self._compressor = base_compressor
        self._classifier = ConversationClassifier()
        self._last_strategy: CompressionStrategy | None = None

    def should_compress(self, prompt_tokens: int | None = None) -> bool:
        return bool(self._compressor.should_compress(prompt_tokens))

    def compress(
        self,
        messages: list[dict],
        current_tokens: int,
        focus_topic: str | None = None,
    ) -> list[dict]:
        conv_type = self._classifier.classify(messages)
        strategy = STRATEGIES[conv_type]
        self._last_strategy = strategy

        logger.info("ACE: detected conversation type=%s, strategy=%s", conv_type.value, strategy.name)

        if not self._compressor.should_compress(current_tokens):
            return messages

        if len(messages) <= self._compressor.protect_first_n + self._compressor.protect_last_n:
            return messages

        head = messages[:self._compressor.protect_first_n]
        tail = messages[-self._compressor.protect_last_n:]
        compressible = messages[self._compressor.protect_first_n:-self._compressor.protect_last_n]

        if not compressible:
            return messages

        if strategy.block_protect_patterns:
            compressible = self._protect_blocks(compressible, strategy)

        focus = focus_topic or strategy.summary_focus
        summary = self._compressor._summarize(compressible, focus)

        compressed = head + [
            {"role": "system", "content": f"[ACE:{strategy.name}] Context compressed. Summary:\n{summary}"}
        ] + tail

        logger.info(
            "ACE压缩: %d条→%d条 (type=%s, strategy=%s)",
            len(messages), len(compressed), conv_type.value, strategy.name,
        )
        return compressed

    @classmethod
    def _protect_blocks(cls, messages: list[dict], strategy: CompressionStrategy) -> list[dict]:
        result = []
        for m in messages:
            content = str(m.get("content", ""))
            for pattern in strategy.block_protect_patterns:
                content = re.sub(pattern, " [PROTECTED_BLOCK]", content)
            result.append({**m, "content": content})
        return result

    @property
    def last_strategy(self) -> CompressionStrategy | None:
        return self._last_strategy

    @classmethod
    def get_strategy(cls, conv_type: ConversationType) -> CompressionStrategy:
        return STRATEGIES[conv_type]
