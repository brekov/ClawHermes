"""ClawHermes - CLI"""
from __future__ import annotations

import logging
import os
import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from clawhermes.config import get_data_dir, load_env

console = Console()
logging.basicConfig(level=logging.WARNING)


def _load_dotenv():
    """加载 $CH_DATA_DIR/.env 到 os.environ（不覆盖已有环境变量）"""
    load_env()


def _create_agent(api_key=None, model=None):
    from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
    from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
    from clawhermes.llm.provider import LLMProvider
    from clawhermes.tools.builtin import register_builtin_tools
    provider = LLMProvider(
        model=model or os.getenv("CH_DEFAULT_MODEL", "deepseek/deepseek-chat"),
        api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry)
    data_dir = get_data_dir()
    memory = MemoryManager()
    memory.add_provider(JSONMemoryProvider(data_dir))
    agent = Agent(llm_provider=provider, tool_registry=registry,
                  config=AgentConfig(max_iterations=20))
    return agent, memory


@click.group()
def main():
    """ClawHermes AI Agent 框架"""
    pass


# ====== chat ======

@main.command()
@click.option("--model", default=None)
@click.option("--api-key", default=None)
@click.option("--one-shot", default=None)
def chat(model, api_key, one_shot):
    """CLI 对话"""
    from clawhermes.agent.memory import MemoryScope
    try:
        agent, memory = _create_agent(api_key, model)
    except Exception as e:
        console.print(f"❌ {e}", style="red")
        return
    console.print(f"🚀 已就绪 | 工具: {len(agent.tools.list())} 个 | 模型: {agent.llm.model}")
    if one_shot:
        with console.status("思考中..."):
            try:
                console.print(Markdown(agent.chat(one_shot)))
            except Exception as e:
                console.print(f"❌ {e}", style="red")
        return
    while True:
        user = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        if user in ("/exit", "/quit"):
            break
        if user.startswith("/save "):
            memory.save(user[6:], MemoryScope.USER)
            console.print("✅ 已保存", style="green")
            continue
        if user == "/tools":
            for t in agent.tools.list():
                console.print(f"  • {t.name}: {t.description}")
            continue
        with console.status("思考中..."):
            try:
                console.print(Markdown(agent.chat(user)))
            except Exception as e:
                console.print(f"❌ {e}", style="red")


# ====== doctor ======

@main.command()
def doctor():
    """诊断"""
    console.print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    for pkg, role in [("litellm", "llm"), ("fastapi", "web"), ("chromadb", "vector"), ("rich", "cli")]:
        try:
            __import__(pkg.replace("-", "_"))
            console.print(f"  ✅ {pkg}")
        except ImportError:
            console.print(f"  ❌ {pkg}")
    found = [k for k in os.environ if k.endswith("_API_KEY") and os.environ[k]]
    for k in found[:3]:
        console.print(f"  ✅ {k}")
    if not found:
        console.print("  ⚠️  未设置 API Key")


def _register_subcommands() -> None:
    """从子模块导入子命令组并注册到 main，同时 re-export 保持向后兼容。"""
    from clawhermes.cli import agent_cmd, gateway_cmd
    from clawhermes.cli import setup as setup_mod

    main.add_command(gateway_cmd.gateway)
    main.add_command(agent_cmd.agent)
    main.add_command(setup_mod.setup)
    main.add_command(setup_mod.config)

    # re-export: 保持 `from clawhermes.cli import gateway/agent/setup/config` 兼容
    g = globals()
    g["gateway"] = gateway_cmd.gateway
    g["agent"] = agent_cmd.agent
    g["setup"] = setup_mod.setup
    g["config"] = setup_mod.config


_register_subcommands()


__all__ = ["main", "console", "_create_agent", "_load_dotenv",
           "chat", "doctor", "gateway", "agent", "setup", "config"]
