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
    """ClawHermes - 融合 Hermes 与 OpenClaw 的 AI Agent 框架"""
    pass


# ====== gateway 命令组（类似 OpenClaw 的 openclaw gateway *）======

@main.group()
def gateway():
    """管理 Gateway 服务"""
    pass


@gateway.command()
@click.option("--port", default=18789, help="Gateway 端口")
@click.option("--host", default="127.0.0.1", help="绑定地址")
@click.option("--api-key", default=None, help="API Key")
@click.option("--model", default=None, help="模型名称")
def start(port: int, host: str, api_key: str | None, model: str | None):
    """启动 Gateway 常驻服务（自动连接已配置的渠道）"""
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        console.print("❌ 请设置 DEEPSEEK_API_KEY 环境变量或 --api-key", style="red")
        return

    import uvicorn
    from clawhermes.gateway.app import app

    os.environ["CH_GW_API_KEY"] = api_key
    if model:
        os.environ["CH_GW_MODEL"] = model

    console.print(f"🚀 Gateway 启动: [bold]{host}:{port}[/bold]")
    console.print(f"📋 渠道配置: [bold]{_channel_summary()}[/bold]")
    uvicorn.run(app, host=host, port=port, log_level="info")


def _channel_summary() -> str:
    """读取渠道配置并返回摘要"""
    from clawhermes.gateway.setup import load_channels
    channels = load_channels()
    if not cfg:
        return "未配置（运行 clawhermes gateway setup）"
    return ", ".join(channels.keys())


@gateway.command()
def setup():
    """交互式配置消息渠道"""
    from clawhermes.gateway.setup import interactive_setup
    interactive_setup()


@gateway.command()
def status():
    """查看渠道配置状态"""
    from clawhermes.gateway.setup import show_status
    show_status()


# ====== 其他命令 ======

# ====== agent 命令组（多 Agent + 人格设定）======

@main.group()
def agent():
    """管理 Agent（多 Agent + 身份设定）"""
    pass


@agent.command("list")
def agent_list():
    """列出所有 Agent"""
    from clawhermes.agent.SOUL.manager import cmd_list
    cmd_list()


@agent.command()
@click.argument("name")
@click.option("--clone", default=None, help="从已有 Agent 克隆")
def create(name: str, clone: str | None):
    """创建新 Agent"""
    from clawhermes.agent.SOUL.manager import cmd_create
    cmd_create(name, clone)


@agent.command()
@click.argument("name", required=False)
def delete(name: str | None):
    """删除 Agent"""
    from clawhermes.agent.SOUL.manager import delete_agent
    delete_agent(name)


@agent.command()
@click.argument("name", required=False)
@click.option("--persona", default=None, help="直接指定身份内容")
@click.option("--instructions", default=None, help="直接指定行为指令")
def set_persona(name: str | None, SOUL: str | None, instructions: str | None):
    """设定 Agent 身份（交互式或 --persona/--instructions）"""
    from clawhermes.agent.SOUL.manager import cmd_set_persona, cmd_set_instructions, write_SOUL, write_instructions, get_default_agent
    if name is None:
        name = get_default_agent()
    if SOUL:
        write_SOUL(name, SOUL)
    if instructions:
        write_instructions(name, instructions)
    if not SOUL and not instructions:
        cmd_set_persona(name)


@agent.command()
@click.argument("name", required=False)
def show(name: str | None):
    """查看 Agent 详情"""
    from clawhermes.agent.SOUL.manager import cmd_show
    cmd_show(name)


@agent.command()
@click.argument("name")
def switch(name: str):
    """切换默认 Agent"""
    from clawhermes.agent.SOUL.manager import set_default_agent, agent_exists
    if agent_exists(name):
        set_default_agent(name)
        console.print(f"[green]✅ 已切换到 Agent '{name}'[/green]")
    else:
        console.print(f"[red]❌ Agent '{name}' 不存在[/red]")


# ====== setup 命令 ======

# ====== config 命令 ======

@main.group()
def config():
    """管理配置文件 (config.yaml)"""
    pass


@config.command("show")
def config_show():
    """查看当前配置"""
    from clawhermes.config import load_yaml
    from rich.syntax import Syntax
    cfg = load_yaml()
    if channels:
        import yaml
        text = yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
        console.print(Syntax(text, "yaml", theme="monokai"))
    else:
        console.print("⚠️  config.yaml 不存在，运行 clawhermes setup 生成")


@config.command("init")
def config_init():
    """生成默认配置文件"""
    from clawhermes.config import default_yaml, save_yaml
    cfg = default_yaml()
    save_yaml(cfg)
    console.print("💡 编辑 config.yaml 后运行 clawhermes gateway start 生效")


@config.command("path")
def config_path():
    """显示配置文件路径"""
    from clawhermes.config import get_yaml_path
    console.print(f"📄 {get_yaml_path()}")



@main.command()
@click.option("--env-file", default=None)
def setup(env_file: str | None):
    """初始化数据目录"""
    data_dir = Path(os.getenv("CH_DATA_DIR", "~/.clawhermes")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "skills").mkdir(parents=True, exist_ok=True)
    # 创建默认 Agent
    from clawhermes.agent.SOUL.manager import create_agent
    create_agent("default")
    console.print(f"✅ 数据目录已创建: [bold]{data_dir}[/bold]")
    console.print("💡 运行 [bold]clawhermes gateway setup[/bold] 配置消息渠道")
    console.print("💡 运行 [bold]clawhermes agent set-SOUL[/bold] 设定 Agent 身份")


# ====== config 命令 ======

@main.group()
def config():
    """管理配置文件 (config.yaml)"""
    pass


@config.command("show")
def config_show():
    """查看当前配置"""
    from clawhermes.config import load_yaml
    from rich.syntax import Syntax
    cfg = load_yaml()
    if channels:
        import yaml
        text = yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
        console.print(Syntax(text, "yaml", theme="monokai"))
    else:
        console.print("⚠️  config.yaml 不存在，运行 clawhermes setup 生成")


@config.command("init")
def config_init():
    """生成默认配置文件"""
    from clawhermes.config import default_yaml, save_yaml
    cfg = default_yaml()
    save_yaml(cfg)
    console.print("💡 编辑 config.yaml 后运行 clawhermes gateway start 生效")


@config.command("path")
def config_path():
    """显示配置文件路径"""
    from clawhermes.config import get_yaml_path
    console.print(f"📄 {get_yaml_path()}")



@main.command()
@click.option("--model", default=None)
@click.option("--api-key", default=None)
@click.option("--one-shot", default=None)
def chat(model, api_key, one_shot):
    """CLI 对话模式"""
    from clawhermes.agent.memory import MemoryScope
    try:
        agent, memory = _create_agent(api_key, model)
    except Exception as e:
        console.print(f"❌ Agent 初始化失败: {e}", style="red")
        return

    console.print("🚀 [bold]ClawHermes[/bold] 已就绪")
    console.print(f"📋 工具: {len(agent.tools.list())} 个 | 模型: {agent.llm.model}")

    if one_shot:
        with console.status("🤔 思考中..."):
            try:
                response = agent.chat(one_shot)
                console.print(Markdown(response))
            except Exception as e:
                console.print(f"❌ 错误: {e}", style="red")
        return

    while True:
        user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        if user_input.lower() in ("/exit", "/quit", "退出"):
            break
        elif user_input.startswith("/save "):
            memory.save(user_input[6:], MemoryScope.USER)
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


# ====== config 命令 ======

@main.group()
def config():
    """管理配置文件 (config.yaml)"""
    pass


@config.command("show")
def config_show():
    """查看当前配置"""
    from clawhermes.config import load_yaml
    from rich.syntax import Syntax
    cfg = load_yaml()
    if channels:
        import yaml
        text = yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
        console.print(Syntax(text, "yaml", theme="monokai"))
    else:
        console.print("⚠️  config.yaml 不存在，运行 clawhermes setup 生成")


@config.command("init")
def config_init():
    """生成默认配置文件"""
    from clawhermes.config import default_yaml, save_yaml
    cfg = default_yaml()
    save_yaml(cfg)
    console.print("💡 编辑 config.yaml 后运行 clawhermes gateway start 生效")


@config.command("path")
def config_path():
    """显示配置文件路径"""
    from clawhermes.config import get_yaml_path
    console.print(f"📄 {get_yaml_path()}")



@main.command()
def doctor():
    """诊断系统配置"""
    console.print("🔍 [bold]ClawHermes 诊断[/bold]")
    import sys
    console.print(f"  ✅ Python {sys.version}")

    deps = {"litellm": "llm", "fastapi": "web", "chromadb": "vector"}
    for pkg, role in deps.items():
        try:
            __import__(pkg.replace("-", "_"))
            console.print(f"  ✅ {pkg} ({role})")
        except ImportError:
            console.print(f"  ❌ {pkg} ({role}) — 未安装")

    llm_keys = ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"]
    found = False
    for key_name in llm_keys:
        if os.getenv(key_name):
            val = os.getenv(key_name, "")
            console.print(f"  ✅ {key_name}={val[:8]}...")
            found = True
    if not found:
        console.print(f"  ⚠️  未设置 LLM API Key（支持: {", ".join(llm_keys)}）")

    # 显示渠道配置状态
    from clawhermes.gateway.setup import load_channels
    channels = load_channels()
    if channels:
        console.print(f"  ✅ 渠道配置: {', '.join(channels.keys())}")
    else:
        console.print("  ⚠️  未配置渠道（运行 clawhermes gateway setup）")


if __name__ == "__main__":
    main()
