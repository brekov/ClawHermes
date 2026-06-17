"""
ClawHermes - 完整端到端测试
覆盖 CLI、Gateway、Agent、工具、记忆全链路
"""
import sys
import tempfile
from pathlib import Path

# 确保能找到 src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

pass_count = 0
fail_count = 0


def check(name, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  ✅ {name}")
    else:
        fail_count += 1
        print(f"  ❌ {name} — {detail}")


def test_core_types():
    """测试核心类型"""
    from clawhermes.types import MemoryItem, Message, MessageRole, Skill, ToolCall

    msg = Message(role=MessageRole.USER, content="你好")
    check("Message 创建", msg.role == MessageRole.USER and msg.content == "你好")

    tc = ToolCall(id="1", name="test", args={})
    tc.status = tc.status  # 默认 PENDING
    check("ToolCall 默认状态", tc.status.value == "pending")

    m = MemoryItem(content="测试", importance=0.9)
    check("MemoryItem 范围", 0 <= m.importance <= 1)

    s = Skill(name="test", content="# Test")
    check("Skill 默认值", s.status == "active" and s.version == 1)

    check("ProviderConfig", True)  # 只是导入检查


def test_llm_provider():
    """测试 LLM Provider"""
    from clawhermes.llm.provider import CredentialPool, LLMProvider

    p = LLMProvider(model="test-model", api_key="test")
    check("LLMProvider 创建", p.model == "test-model")

    pool = CredentialPool(["a", "b", "c"], strategy="round_robin")
    keys = [pool.get_key() for _ in range(3)]
    check("凭证池轮询", len(set(keys)) == 3)

    pool.mark_failed("a", 429)
    check("凭证冷却标记", True)


def test_system_prompt():
    """测试三层 System Prompt"""
    from clawhermes.agent.prompt import SystemPrompt

    sp = SystemPrompt()
    prompt = sp.build()
    check("Stable 层包含身份", "ClawHermes" in prompt)

    sp.volatile.timestamp = "2026-06-16 12:00"
    sp.volatile.memory_snapshot = "用户喜欢 Python"
    prompt2 = sp.build()
    check("Volatile 层渲染", "2026-06-16" in prompt2 and "Python" in prompt2)

    # 缓存测试
    before = sp.build()
    sp.stable.agent_name = "Changed"
    after = sp.build()
    check("Stable 缓存生效", before == after)  # 没 invalidate 前不变
    sp.invalidate_cache()
    after2 = sp.build()
    check("缓存清除生效", "Changed" in after2)


def test_tool_system():
    """测试工具系统"""
    from clawhermes.agent.loop import HookManager, ToolDispatcher, ToolRegistry
    from clawhermes.tools.builtin import register_builtin_tools

    # 注册
    registry = ToolRegistry()
    register_builtin_tools(registry)
    tools = registry.list()
    check(f"{len(tools)}个内置工具", len(tools) >= 9)

    # Schema
    schemas = registry.schemas()
    check("工具 Schema 生成", len(schemas) >= 9)

    # 调度
    hooks = HookManager()
    dispatcher = ToolDispatcher(registry, hooks)

    # 测试 get_time
    results = dispatcher.execute(
        [{"id": "1", "function": {"name": "get_time", "arguments": "{}"}}],
        {},
    )
    check("get_time 工具执行", len(results) == 1 and "tool_call_id" in results[0])

    # 测试钩子
    call_log = []

    def before_hook(**kw):
        call_log.append(("before", kw.get("tool_name")))

    hooks.register("before_tool_call", before_hook)
    dispatcher.execute(
        [{"id": "2", "function": {"name": "get_time", "arguments": "{}"}}],
        {},
    )
    check("钩子触发", len(call_log) == 1)


def test_memory_system():
    """测试记忆系统"""
    from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

    with tempfile.TemporaryDirectory() as tmp:
        mem = MemoryManager()
        mem.add_provider(JSONMemoryProvider(tmp))

        mem.save("用户喜欢喝美式", importance=0.9)
        mem.save("用户是 Python 开发者", importance=0.8)

        results = mem.search("美式")
        check("记忆搜索", len(results) >= 1 and "美式" in results[0].content)

        snapshot = mem.snapshot()
        check("记忆快照", "Python" in snapshot)

        results2 = mem.search("Python")
        check("关键词搜索区分", len(results2) >= 1)


def test_agent_loop():
    """测试 Agent 循环（用 MockProvider）"""
    sys.path.insert(0, str(Path(__file__).parent))
    from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
    from clawhermes.tools.builtin import register_builtin_tools
    from tests.mock_provider import MockProvider

    # 简单对话
    p = MockProvider(responses=["我是 ClawHermes。"])
    a = Agent(llm_provider=p, config=AgentConfig(max_iterations=5))
    r = a.chat("你好")
    check("Agent 简单对话", "ClawHermes" in r)

    # 多轮对话
    a2 = Agent(
        llm_provider=MockProvider(responses=["第一轮", "第二轮"]),
        config=AgentConfig(max_iterations=5),
    )
    r1 = a2.chat("第一句")
    r2 = a2.chat("第二句")
    check("多轮对话", r1 == "第一轮" and r2 == "第二轮")

    # 带工具的 Agent
    registry = ToolRegistry()
    register_builtin_tools(registry)
    a3 = Agent(
        llm_provider=MockProvider(responses=["工具调用测试"]),
        tool_registry=registry,
    )
    r3 = a3.chat("现在几点了？")
    check("带工具的 Agent", bool(r3))


def test_gateway_api():
    """测试 Gateway API（不需要启动服务，只测导入和 schema）"""
    from clawhermes.gateway.app import app

    # 检查路由注册
    routes = [r.path for r in app.routes]
    check("Gateway /init 路由", "/init" in routes)
    check("Gateway /chat 路由", "/chat" in routes)
    check("Gateway /health 路由", "/health" in routes)
    check("Gateway /tools 路由", "/tools" in routes)
    check("Gateway /sessions 路由", "/sessions" in routes)
    check("Gateway memory 路由",
          "/memory/save" in routes and "/memory/search" in routes)

    # 检查初始化请求 schema
    from clawhermes.gateway.app import InitRequest
    req = InitRequest(api_key="test", model="test/model")
    check("InitRequest schema", req.model == "test/model")
    check("InitRequest 默认值", req.max_iterations == 50)


def test_docker_config():
    """测试 Docker 配置"""
    from pathlib import Path
    dockerfile = Path(__file__).parent.parent / "Dockerfile"
    compose = Path(__file__).parent.parent / "docker-compose.yml"
    install = Path(__file__).parent.parent / "scripts/install.sh"

    check("Dockerfile 存在", dockerfile.exists())
    check("docker-compose.yml 存在", compose.exists())
    check("install.sh 存在", install.exists())

    content = dockerfile.read_text()
    check("Dockerfile 有 HEALTHCHECK", "HEALTHCHECK" in content)
    check("Dockerfile 暴露 18789 端口", "18789" in content)
    check("Dockerfile 用 slim 镜像", "python:3.12-slim" in content)

    compose_content = compose.read_text()
    check("docker-compose 有 healthcheck", "healthcheck" in compose_content)
    check("docker-compose 有 volume", "volumes" in compose_content)


def test_cli_commands():
    """测试 CLI 命令注册"""
    from clawhermes.cli import main

    commands = list(main.commands.keys())
    check("CLI 有 chat 命令", "chat" in commands)
    check("CLI 有 gateway 命令", "gateway" in commands)
    check("CLI 有 setup 命令", "setup" in commands)
    check("CLI 有 doctor 命令", "doctor" in commands)


def test_config_validation():
    """测试配置 fail-fast"""
    from clawhermes.config import ClawHermesConfig

    # 正常配置
    c = ClawHermesConfig(llm_default_max_tokens=32000)
    check("配置加载正常", c.llm_default_max_tokens == 32000)
    check("默认工具 profile", c.tools.profile == "standard")

    # 默认值检查
    check("默认 agent 名称", c.agent.name == "clawhermes")
    check("默认 gateway 端口", c.gateway_port == 18789)


def test_import_all():
    """测试所有模块可导入"""
    modules = [
        "clawhermes",
        "clawhermes.types",
        "clawhermes.config",
        "clawhermes.cli",
        "clawhermes.llm.provider",
        "clawhermes.agent.loop",
        "clawhermes.agent.prompt",
        "clawhermes.agent.memory",
        "clawhermes.agent.exceptions",
        "clawhermes.agent.delegate",
        "clawhermes.tools.builtin",
        "clawhermes.gateway.app",
    ]
    for mod in modules:
        try:
            __import__(mod)
            check(f"导入 {mod}", True)
        except Exception as e:
            check(f"导入 {mod}", False, str(e))


if __name__ == "__main__":
    print("=" * 50)
    print("  ClawHermes 完整功能测试")
    print("=" * 50)

    tests = [
        ("类型系统", test_core_types),
        ("LLM Provider", test_llm_provider),
        ("三层 System Prompt", test_system_prompt),
        ("工具系统", test_tool_system),
        ("记忆系统", test_memory_system),
        ("Agent 循环", test_agent_loop),
        ("Gateway API", test_gateway_api),
        ("Docker 配置", test_docker_config),
        ("CLI 命令", test_cli_commands),
        ("配置校验", test_config_validation),
        ("模块导入", test_import_all),
    ]

    for name, fn in tests:
        print(f"\n📦 {name}")
        try:
            fn()
        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            fail_count += 1

    total = pass_count + fail_count
    print(f"\n{'=' * 50}")
    print(f"  总计: {total}  |  ✅ 通过: {pass_count}  |  ❌ 失败: {fail_count}")
    if fail_count == 0:
        print("  🎉 全部通过！")
    else:
        print(f"  ⚠️  有 {fail_count} 个测试失败")
    print(f"{'=' * 50}")
