"""
ClawHermes - 核心类型定义
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class QueueMode(str, Enum):
    """消息队列模式（来自 OpenClaw）"""
    STEER = "steer"          # 注入当前轮次
    FOLLOWUP = "followup"    # 排队等下一轮
    COLLECT = "collect"      # 安静窗口后合并
    INTERRUPT = "interrupt"  # 中止当前执行


class ToolCallStatus(str, Enum):
    """工具调用状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"       # 被钩子/策略阻止


class MemoryScope(str, Enum):
    """记忆作用域"""
    SESSION = "session"       # 仅当前会话
    USER = "user"             # 用户级（跨会话）
    GLOBAL = "global"         # 全局


@dataclass
class Message:
    """一条对话消息"""
    role: MessageRole
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    args: dict[str, Any]
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class SessionContext:
    """会话上下文"""
    session_id: str
    chat_id: str
    platform: str               # "cli" / "weixin" / "telegram" / ...
    messages: list[Message] = field(default_factory=list)
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryItem:
    """一条记忆"""
    content: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    scope: MemoryScope = MemoryScope.USER
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    importance: float = 0.5  # 0-1


@dataclass
class Skill:
    """一条技能"""
    name: str
    content: str                # SKILL.md 内容
    description: str = ""
    category: str = "general"
    version: int = 1
    usage_count: int = 0
    last_used: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "active"      # active / stale / archived


@dataclass
class ProviderConfig:
    """LLM 提供商配置"""
    name: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 64000
    temperature: float = 0.7
    timeout: int = 60000
