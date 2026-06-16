"""ClawHermes - CLI"""
from __future__ import annotations
import logging, os
from pathlib import Path
import click
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

console = Console()
logging.basicConfig(level=logging.WARNING)


def _create_agent(api_key=None, model=None):
    from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
    from clawhermes.agent.memory import MemoryManager, JSONMemoryProvider
    from clawhermes.llm.provider import LLMProvider
    from clawhermes.tools.builtin import register_builtin_tools
    provider = LLMProvider(
        model=model or os.getenv("CH_DEFAULT_MODEL", "deepseek/deepseek-chat"),
        api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry)
    data_dir = Path(os.getenv("CH_DATA_DIR", "~/.clawhermes")).expanduser()
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
        console.print(f"❌ {e}", style="red"); return
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
        if user in ("/exit", "/quit"): break
        if user.startswith("/save "):
            memory.save(user[6:], MemoryScope.USER)
            console.print("✅ 已保存", style="green"); continue
        if user == "/tools":
            for t in agent.tools.list():
                console.print(f"  • {t.name}: {t.description}")
            continue
        with console.status("思考中..."):
            try:
                console.print(Markdown(agent.chat(user)))
            except Exception as e:
                console.print(f"❌ {e}", style="red")


# ====== gateway ======

@main.group()
def gateway():
    """管理 Gateway 服务"""
    pass


@gateway.command()
@click.option("--port", default=18789)
@click.option("--host", default="127.0.0.1")
@click.option("--api-key", default=None)
@click.option("--model", default=None)
def start(port, host, api_key, model):
    """启动 Gateway"""
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        console.print("❌ 请设置 DEEPSEEK_API_KEY", style="red"); return
    import uvicorn
    from clawhermes.gateway.app import app
    os.environ["CH_GW_API_KEY"] = api_key
    if model:
        os.environ["CH_GW_MODEL"] = model
    console.print(f"🚀 Gateway: {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


# ====== config ======

@main.group()
def config():
    """管理配置"""
    pass


@config.command("show")
def config_show():
    """查看 config.yaml"""
    from clawhermes.config import load_yaml
    from rich.syntax import Syntax
    import yaml
    cfg = load_yaml()
    if cfg:
        console.print(Syntax(yaml.dump(cfg, allow_unicode=True), "yaml", theme="monokai"))
    else:
        console.print("⚠️  config.yaml 不存在，运行 clawhermes setup")


@config.command("path")
def config_path():
    """显示配置文件路径"""
    from clawhermes.config import get_yaml_path
    console.print(f"📄 {get_yaml_path()}")


# ====== agent ======

@main.group()
def agent():
    """管理 Agent"""
    pass


@agent.command("list")
def agent_list():
    from clawhermes.agent.agent_mgr import cmd_list
    cmd_list()


@agent.command()
@click.argument("name")
@click.option("--clone", default=None)
def create(name, clone):
    from clawhermes.agent.agent_mgr import cmd_create
    cmd_create(name, clone)


@agent.command()
@click.argument("name", required=False)
def show(name):
    from clawhermes.agent.agent_mgr import cmd_show
    cmd_show(name)


@agent.command()
@click.argument("name")
def switch(name):
    from clawhermes.agent.agent_mgr import set_default_agent, agent_exists
    if agent_exists(name):
        set_default_agent(name)
        console.print(f"✅ 已切换到 '{name}'")
    else:
        console.print(f"❌ Agent '{name}' 不存在")


@agent.command()
@click.argument("name", required=False)
def set_persona(name):
    from clawhermes.agent.agent_mgr import cmd_set_persona
    cmd_set_persona(name)


# ====== setup / doctor ======

@main.command()
def setup():
    """初始化"""
    data_dir = Path(os.getenv("CH_DATA_DIR", "~/.clawhermes")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "skills").mkdir(parents=True, exist_ok=True)
    from clawhermes.agent.agent_mgr import create_agent
    create_agent("default")
    console.print(f"✅ 已初始化: {data_dir}")


@main.command()
def doctor():
    """诊断"""
    import sys
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


if __name__ == "__main__":
    main()
