"""
ClawHermes - 核心类型测试
"""
from clawhermes.types import (
    MemoryItem,
    MemoryScope,
    Message,
    MessageRole,
    Skill,
    ToolCall,
    ToolCallStatus,
)


def test_message_creation():
    msg = Message(role=MessageRole.USER, content="你好")
    assert msg.role == MessageRole.USER
    assert msg.content == "你好"
    assert msg.id is not None


def test_tool_call_status():
    tc = ToolCall(id="1", name="test", args={})
    assert tc.status == ToolCallStatus.PENDING
    tc.status = ToolCallStatus.SUCCESS
    assert tc.status == ToolCallStatus.SUCCESS


def test_memory_item():
    item = MemoryItem(content="用户喜欢喝美式", scope=MemoryScope.USER)
    assert item.scope == MemoryScope.USER
    assert 0 <= item.importance <= 1


def test_skill_initial_state():
    skill = Skill(name="test-skill", description="测试", content="# 测试技能")
    assert skill.status == "active"
    assert skill.version == 1
    assert skill.usage_count == 0
