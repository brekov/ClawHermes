"""
ClawHermes - System Prompt 三层架构（来自 Hermes）
stable / context / volatile 分层，缓存友好
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StableLayer:
    """稳定层 - Agent 身份、工具指导，几乎不变"""
    agent_name: str = "ClawHermes"
    identity: str = ""
    persona: str = ""     # 从 agent persona 加载的身份设定
    instructions: str = "" # 从 agent persona 加载的行为指令
    user_info: str = ""    # 从 agent persona 加载的用户信息
    tool_guide: str = (
        "你有可用的工具来完成各种任务。"
        "当需要调用工具时，在响应中返回 tool_calls。"
        "工具执行结果会在下一轮返回给你。"
    )
    skill_prompt: str = (
        "你有技能库可以调用，技能是预先编写的能力模块。"
        "当前对话结束后，系统会自动评估是否需要更新技能和记忆。"
    )

    def load_from_agent(self, agent_name: str):
        """从 Agent 配置加载身份设定"""
        try:
            from clawhermes.agent.agent_mgr import (
                build_persona_prompt,
                get_agent_config,
            )
            self.agent_name = agent_name
            self.identity = build_persona_prompt(agent_name)
            get_agent_config(agent_name)
        except Exception:
            pass

    def render(self) -> str:
        parts = [
            self.identity or f"你是 {self.agent_name}，一个智能 AI 助手。",
            self.tool_guide,
            self.skill_prompt,
        ]
        return "\n\n".join(p for p in parts if p)


@dataclass
class ContextLayer:
    """上下文层 - 项目级配置、AGENTS.md 等，按场景切换"""
    project_context: str = ""
    extra_instructions: str = ""
    user_profile: str = ""

    def render(self) -> str:
        parts = []
        if self.user_profile:
            parts.append(f"## 用户档案\n{self.user_profile}")
        if self.project_context:
            parts.append(f"## 项目上下文\n{self.project_context}")
        if self.extra_instructions:
            parts.append(f"## 额外指令\n{self.extra_instructions}")
        return "\n\n".join(parts)


@dataclass
class VolatileLayer:
    """易变层 - 记忆快照、时间戳等，每轮都可能不同"""
    memory_snapshot: str = ""
    session_info: str = ""
    timestamp: str = ""

    def render(self) -> str:
        parts = []
        if self.timestamp:
            parts.append(f"当前时间: {self.timestamp}")
        if self.session_info:
            parts.append(self.session_info)
        if self.memory_snapshot:
            parts.append(f"## 相关记忆\n{self.memory_snapshot}")
        return "\n\n".join(parts)


class SystemPrompt:
    """三层 System Prompt 组装器"""

    def __init__(self):
        self.stable = StableLayer()
        self.context = ContextLayer()
        self.volatile = VolatileLayer()
        self._cached_stable: str | None = None

    def build(self) -> str:
        """组装完整 system prompt，stable 层缓存"""
        if self._cached_stable is None:
            self._cached_stable = self.stable.render()
            self._cached_stable += "\n\n"

        parts = [
            self._cached_stable,
            self.context.render(),
            self.volatile.render(),
        ]
        return "\n\n".join(p for p in parts if p)

    def invalidate_cache(self):
        """使 stable 缓存失效（身份变更时调用）"""
        self._cached_stable = None
