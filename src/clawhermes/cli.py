"""ClawHermes - CLI"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

import click
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text



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
        console.print("❌ 请设置 DEEPSEEK_API_KEY", style="red")
        return
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
    import yaml
    from rich.syntax import Syntax

    from clawhermes.config import load_yaml
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
    from clawhermes.agent.agent_mgr import agent_exists, set_default_agent
    if agent_exists(name):
        set_default_agent(name)
        console.print(f"✅ 已切换到 '{name}'")
    else:
        console.print(f"❌ Agent '{name}' 不存在")


@agent.command(name="set")
@click.argument("name", required=False)
def cmd_agent_set(name):
    from clawhermes.agent.agent_mgr import cmd_set_persona
    cmd_set_persona(name)


# ====== setup / doctor ======


@main.command()
@click.option("--non-interactive", is_flag=True, help="非交互模式, 使用默认值")
def setup(non_interactive=False):
    """交互式初始化向导 — 一步步配置 LLM、渠道、Gateway"""
    if not non_interactive and not sys.stdin.isatty():
        non_interactive = True
    from rich.prompt import Confirm, IntPrompt

    # ══════════════════════════════════════════
    # 欢迎
    # ══════════════════════════════════════════
    welcome = Panel.fit(
        Text("ClawHermes · 初始化向导", style="bold cyan", justify="center")
        + Text("\n\n一步步完成 LLM 提供商、消息渠道和 Gateway 的配置", style="dim", justify="center"),
        border_style="cyan",
    )
    console.print(welcome)

    env_vars: dict[str, str] = {}
    channels_enabled: list[str] = []

    # ══════════════════════════════════════════
    # Step 1: LLM 提供商
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 1/4[/]  [bold]LLM 提供商[/]\n")

    providers = {
        "1": ("DeepSeek", "deepseek/deepseek-chat", "DEEPSEEK_API_KEY"),
        "2": ("OpenAI", "gpt-4o", "OPENAI_API_KEY"),
        "3": ("Google Gemini", "gemini/gemini-2.5-flash", "GOOGLE_API_KEY"),
        "4": ("Ollama (本地)", "qwen2.5", None),
    }

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("提供商", width=18)
    table.add_column("默认模型", width=28)
    for k, (name, model, _) in providers.items():
        table.add_row(k, name, model)
    console.print(table)

    if non_interactive:
        choice = "1"
    else:
        choice = Prompt.ask("选择 LLM 提供商", choices=["1", "2", "3", "4"], default="1")
    name, model, key_var = providers[choice]
    env_vars["CH_LLM_DEFAULT_MODEL"] = model
    console.print(f"  ✅ 提供商: {name} ({model})")

    if key_var:
        if non_interactive:
            console.print(f"  ⚠️  非交互模式, 请手动设置 {key_var}")
        else:
            api_key = Prompt.ask(f"  {key_var}", password=True)
            if api_key:
                env_vars[key_var] = api_key
                console.print("  ✅ API Key 已设置")
            else:
                console.print(f"  ⚠️  跳过 — 可稍后在 .env 中手动设置 {key_var}")
    else:
        env_vars["OLLAMA_BASE_URL"] = Prompt.ask("  Ollama 地址", default="http://localhost:11434") if not non_interactive else "http://localhost:11434"

    # ══════════════════════════════════════════
    # Step 2: 消息渠道
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 2/4[/]  [bold]消息渠道[/]\n")

    channel_defs = {
        "lark": {
            "name": "飞书 (Feishu/Lark)",
            "vars": [("FEISHU_APP_ID", "App ID"), ("FEISHU_APP_SECRET", "App Secret"),
                     ("FEISHU_VERIFY_TOKEN", "Verify Token"), ("FEISHU_ENCRYPT_KEY", "Encrypt Key")],
            "example_yaml": "config/channels/feishu.yaml.example",
        },
        "weixin": {
            "name": "微信 (WeChat)",
            "vars": [("WECHAT_APP_ID", "App ID"), ("WECHAT_APP_SECRET", "App Secret"),
                     ("WECHAT_TOKEN", "Token"), ("WECHAT_ENCODING_AES_KEY", "Encoding AES Key")],
            "example_yaml": "config/channels/wechat.yaml.example",
        },
        "qq": {
            "name": "QQ Bot",
            "vars": [("QQ_APP_ID", "Bot App ID"), ("QQ_TOKEN", "Bot Token"),
                     ("QQ_SECRET", "Bot Secret")],
            "example_yaml": "config/channels/qq.yaml.example",
        },
    }

    if non_interactive:
        console.print("  ⚠️  非交互模式, 跳过渠道配置")
    else:
        for ch_id, ch_def in channel_defs.items():
            console.print(f"\n  [bold]{ch_def['name']}[/]")
            if Confirm.ask(f"  启用 {ch_def['name']}?", default=False):
                channels_enabled.append(ch_id)
                console.print(f"  📋 {ch_def['name']} 需要以下凭证:")
                for var_name, desc in ch_def["vars"]:
                    val = Prompt.ask(f"    {desc} ({var_name})", password=False)
                    if val:
                        env_vars[var_name] = val
                console.print(f"  ✅ {ch_def['name']} 已配置")

    # ══════════════════════════════════════════
    # Step 3: Gateway
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 3/4[/]  [bold]Gateway 服务[/]\n")

    if non_interactive:
        gw_host, gw_port, gw_secret = "127.0.0.1", 18789, None
    else:
        gw_host = Prompt.ask("  监听地址", default="127.0.0.1")
        gw_port = IntPrompt.ask("  监听端口", default=18789)
        gw_secret = Prompt.ask("  Gateway Secret (可选, 非 127.0.0.1 监听时必须)", password=True, default="")

    env_vars["CH_GATEWAY_HOST"] = gw_host
    env_vars["CH_GATEWAY_PORT"] = str(gw_port)
    if gw_secret:
        env_vars["CH_GATEWAY_SECRET"] = gw_secret
    console.print(f"  ✅ Gateway: {gw_host}:{gw_port}")

    # ══════════════════════════════════════════
    # Step 4: 确认 + 生成
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 4/4[/]  [bold]确认配置[/]\n")

    summary = Table(box=box.SIMPLE, show_header=False)
    summary.add_column("项", style="bold", width=16)
    summary.add_column("值")
    summary.add_row("LLM 模型", model)
    summary.add_row("渠道", ", ".join(str(channel_defs[c]["name"]) for c in channels_enabled) if channels_enabled else "(无)")
    summary.add_row("Gateway", f"{gw_host}:{gw_port}")
    summary.add_row("数据目录", os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    console.print(summary)

    if not non_interactive and not Confirm.ask("\n确认生成配置?", default=True):
        console.print("  ⚠️  已取消")
        return

    # 生成 .env
    _write_env(env_vars)
    console.print("  ✅ .env 已生成")

    # 生成 config.yaml
    from clawhermes.config import default_yaml, save_yaml
    cfg = default_yaml()
    cfg["llm"]["model"] = model
    cfg["gateway"]["host"] = gw_host
    cfg["gateway"]["port"] = gw_port
    save_yaml(cfg)
    console.print("  ✅ config.yaml 已生成")

    # 生成渠道 YAML
    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    channels_dir = data_dir / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)
    for ch_id in channels_enabled:
        ch_def = channel_defs[ch_id]
        _copy_channel_example(str(ch_def["example_yaml"]), channels_dir, ch_id)
        console.print(f"  ✅ channels/{ch_id}.yaml 已生成")

    # 初始化 Agent
    from clawhermes.agent.agent_mgr import create_agent
    create_agent("default")
    console.print("  ✅ Agent 已初始化")

    # 创建子目录
    for sub in ["skills", "providers"]:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    # ══════════════════════════════════════════
    # 自检
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ 自检[/]\n")
    ok = True
    console.print(f"  ✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    for pkg in ["litellm", "fastapi", "rich", "yaml"]:
        try:
            __import__(pkg)
            console.print(f"  ✅ {pkg}")
        except ImportError:
            console.print(f"  ❌ {pkg}")
            ok = False
    for ch_id in channels_enabled:
        try:
            __import__(f"clawhermes_{ch_id}")
            console.print(f"  ✅ clawhermes-{ch_id}")
        except ImportError:
            console.print(f"  ⚠️  clawhermes-{ch_id} 未安装 (pip install -e ./clawhermes-{ch_id})")

    if ok:
        console.print("\n[bold green]🎉 ClawHermes 初始化完成![/]")
        console.print(f"  📁 配置文件: {data_dir}")
        console.print("  🚀 启动: clawhermes gateway start")
    else:
        console.print("\n[bold yellow]⚠️  部分依赖缺失, 请运行 pip install -e . 后重试[/]")


def _write_env(vars_dict: dict[str, str]):
    """写入 .env 文件（不覆盖已有密钥）"""
    env_path = Path(".env")
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    lines = [
        "# ============================================================",
        "# ClawHermes · 环境变量配置",
        "# 由 clawhermes setup 生成",
        "# ============================================================",
        "",
    ]
    for k, v in vars_dict.items():
        if k in existing and existing[k] and ("KEY" in k or "SECRET" in k or "TOKEN" in k):
            lines.append(f"{k}={existing[k]}  # (保留已有)")
        else:
            lines.append(f"{k}={v}")

    env_path.write_text("\n".join(lines) + "\n")


def _copy_channel_example(example_path: str, dest_dir: Path, ch_id: str):
    """复制渠道 YAML 示例到配置目录"""
    import shutil
    repo_root = Path(__file__).resolve().parent.parent.parent  # src/clawhermes → repo root
    src = repo_root / example_path
    dst = dest_dir / f"{ch_id}.yaml"
    if src.exists():
        if not dst.exists():
            shutil.copy(src, dst)

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


if __name__ == "__main__":
    main()
