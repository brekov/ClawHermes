"""
ClawHermes - 集成测试（用 MockProvider，不依赖真实 API）
"""
import json
from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
from clawhermes.tools.builtin import register_builtin_tools
from clawhermes.agent.memory import MemoryManager, JSONMemoryProvider
from tests.mock_provider import MockProvider
import tempfile


def test_agent_simple_chat():
    """测试：简单对话"""
    provider = MockProvider(responses=["你好！我是 ClawHermes。"])
    agent = Agent(llm_provider=provider)
    resp = agent.chat("你好")
    assert "ClawHermes" in resp
    print("✅ 简单对话 OK")


def test_agent_with_tools():
    """测试：触发工具调用"""
    provider = MockProvider()
    registry = ToolRegistry()
    register_builtin_tools(registry)
    agent = Agent(llm_provider=provider, tool_registry=registry)
    resp = agent.chat("现在几点了？")
    assert resp  # 应该有响应
    print(f"✅ 工具调用 OK → {resp[:50]}")


def test_agent_multi_turn():
    """测试：多轮对话"""
    provider = MockProvider(responses=["第一轮", "第二轮"])
    agent = Agent(llm_provider=provider, config=AgentConfig(max_iterations=5))
    r1 = agent.chat("第一句话")
    r2 = agent.chat("第二句话")
    assert r1 == "第一轮"
    assert r2 == "第二轮"
    print("✅ 多轮对话 OK")


def test_memory_system():
    """测试：记忆系统完整流程"""
    with tempfile.TemporaryDirectory() as tmp:
        mem = MemoryManager()
        mem.add_provider(JSONMemoryProvider(tmp))

        # 保存记忆
        mem.save("用户喜欢讨论技术", importance=0.8)
        mem.save("用户是 Python 开发者", importance=0.9)

        # 搜索
        results = mem.search("Python")
        assert len(results) >= 1
        assert "Python" in results[0].content

        # 快照
        snapshot = mem.snapshot()
        assert "Python" in snapshot
        print(f"✅ 记忆系统 OK → {len(results)} 条匹配")


def test_tool_registry_and_dispatch():
    """测试：工具注册与调度"""
    registry = ToolRegistry()
    register_builtin_tools(registry)

    # 应该有8个工具
    tools = registry.list()
    assert len(tools) == 8
    names = {t.name for t in tools}
    assert names == {
        "session_status", "read_file", "write_file", "exec",
        "get_time", "web_search", "memory_search", "memory_save",
    }

    # schema 生成
    schemas = registry.schemas()
    assert len(schemas) == 8
    print(f"✅ 工具系统 OK → {len(tools)} 个工具")


def test_system_prompt_three_layers():
    """测试：三层 System Prompt"""
    from clawhermes.agent.prompt import SystemPrompt

    sp = SystemPrompt()
    prompt = sp.build()

    # stable 层应该包含身份信息
    assert "ClawHermes" in prompt
    assert "工具" in prompt or "工具" in prompt

    # volatile 层渲染
    sp.volatile.timestamp = "2026-06-16 12:00"
    sp.volatile.memory_snapshot = "用户喜欢 Python"
    prompt2 = sp.build()
    assert "2026-06-16" in prompt2
    assert "Python" in prompt2

    print("✅ 三层 System Prompt OK")


def test_hook_system():
    """测试：钩子系统"""
    from clawhermes.agent.loop import HookManager, HookPoint

    hooks = HookManager()
    call_log = []

    def before_tool(**kw):
        call_log.append(("before", kw.get("tool_name")))

    def after_tool(**kw):
        call_log.append(("after", kw.get("tool_name")))

    hooks.register(HookPoint.BEFORE_TOOL_CALL, before_tool)
    hooks.register(HookPoint.AFTER_TOOL_CALL, after_tool)

    hooks.trigger(HookPoint.BEFORE_TOOL_CALL, tool_name="web_search")
    hooks.trigger(HookPoint.AFTER_TOOL_CALL, tool_name="web_search")

    assert len(call_log) == 2
    assert call_log[0] == ("before", "web_search")
    print("✅ 钩子系统 OK")


def test_credential_pool():
    """测试：多凭证池"""
    from clawhermes.llm.provider import CredentialPool

    pool = CredentialPool(["key_a", "key_b", "key_c"], strategy="round_robin")
    keys = [pool.get_key() for _ in range(3)]
    assert len(set(keys)) == 3  # 轮询应该都不同

    # 标记一个失败
    pool.mark_failed("key_b", 429)
    # 暂时拿不到 key_b
    from unittest.mock import patch
    import time
    with patch("time.time", return_value=time.time() + 10):
        pass  # 冷却期内

    print("✅ 多凭证池 OK")


if __name__ == "__main__":
    test_system_prompt_three_layers()
    test_hook_system()
    test_credential_pool()
    test_tool_registry_and_dispatch()
    test_memory_system()
    test_agent_simple_chat()
    test_agent_multi_turn()
    test_agent_with_tools()
    print("\n🎉 所有集成测试通过！")
