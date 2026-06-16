"""
ClawHermes - CLI 入口
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

console = Console()
logging.basicConfig(level=logging.WARNING)


def _create_agent(api_key: str | None = None, model: str | None = None):
    """创建 Agent 实例（连线所有模块）"""
    from clawhermes.agent.loop import Agent, AgentConfig
    from clawhermes.agent.memory import MemoryManager, JSONMemoryProvider
    from clawhermes.llm.provider import LLMProvider
    from clawhermes.tools.builtin import register_builtin_tools
    from clawhermes.agent.loop import ToolRegistry

    # LLM Provider
    provider = LLMProvider(
        model=model or os.getenv("CH_DEFAULT_MODEL", "deepseek/deepseek-chat"),
        api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
    )

    # 工具注册
    registry = ToolRegistry()
    register_builtin_tools(registry)

    # 记忆系统
    data_dir = Path(os.getenv("CH_DATA_DIR", "~/.clawhermes")).expanduser()
    memory = MemoryManager()
    memory.add_provider(JSONMemoryProvider(data_dir))

    # Agent
    agent = Agent(
        llm_provider=provider,
        tool_registry=registry,
        config=AgentConfig(max_iterations=20),
    )

    return agent, memory


@click.group()
def main():
    """ClawHermes - 融合 Hermes 与 OpenClaw 的 AI Agent 框架"""
    pass


@main.command()
@click.option("--env-file", default=None, help="自定义 .env 路径")
def setup(env_file: str | None):
    """一键初始化配置和数据目录"""
    from clawhermes.config import load_config
    load_config(env_file)
    data_dir = Path(os.getenv("CH_DATA_DIR", "~/.clawhermes")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "skills").mkdir(parents=True, exist_ok=True)
    console.print(f"✅ 数据目录已创建: [bold]{data_dir}[/bold]")
    console.print("💡 现在运行 [bold]clawhermes chat[/bold] 开始对话")


@main.command()
@click.option("--model", default=None, help="模型名称，如 deepseek/deepseek-chat")
@click.option("--api-key", default=None, help="API Key")
@click.option("--one-shot", default=None, help="一次性提问，不进入交互模式")
def chat(model, api_key, one_shot):
    """CLI 对话模式"""
    from clawhermes.agent.memory import MemoryScope

    try:
        agent, memory = _create_agent(api_key, model)
    except Exception as e:
        console.print(f"❌ Agent 初始化失败: {e}", style="red")
        console.print("💡 请先设置 DEEPSEEK_API_KEY 环境变量")
        return

    console.print("🚀 [bold]ClawHermes[/bold] 已就绪（输入 /exit 退出，/save <内容> 保存记忆）")
    console.print(f"📋 工具: {len(agent.tools.list())} 个 | 模型: {agent.llm.model}")

    # 一次性模式
    if one_shot:
        with console.status("🤔 思考中..."):
            try:
                response = agent.chat(one_shot)
                console.print(Markdown(response))
            except Exception as e:
                console.print(f"❌ 错误: {e}", style="red")
        return

    # 交互模式
    while True:
        user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

        if user_input.lower() in ("/exit", "/quit", "退出"):
            break
        elif user_input.startswith("/save "):
            content = user_input[6:]
            memory.save(content, MemoryScope.USER)
            console.print("✅ 已保存记忆", style="green")
            continue
        elif user_input == "/tools":
            for t in agent.tools.list():
                console.print(f"  • {t.name}: {t.description}")
            continue

        with console.status("🤔 思考中..."):
            try:
                response = agent.chat(user_input)
                console.print(Markdown(response))
            except Exception as e:
                console.print(f"❌ 错误: {e}", style="red")


@main.command()
def doctor():
    """诊断系统配置"""
    console.print("🔍 [bold]ClawHermes 诊断[/bold]")

    # Python
    import sys
    console.print(f"  ✅ Python {sys.version}")

    # 依赖
    deps = {"litellm": "llm", "fastapi": "web", "chromadb": "vector"}
    for pkg, role in deps.items():
        try:
            __import__(pkg.replace("-", "_"))
            console.print(f"  ✅ {pkg} ({role})")
        except ImportError:
            console.print(f"  ❌ {pkg} ({role}) — 未安装")

    # API Key
    for key_name in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"]:
        if os.getenv(key_name):
            val = os.getenv(key_name, "")
            console.print(f"  ✅ {key_name}={val[:8]}...")
        else:
            console.print(f"  ⚠️  {key_name} 未设置")

    console.print("\n💡 运行 [bold]clawhermes chat[/bold] 开始对话")


if __name__ == "__main__":
    main()
