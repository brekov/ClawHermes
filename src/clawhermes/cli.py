"""ClawHermes - CLI"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

console = Console()
logging.basicConfig(level=logging.WARNING)



def _load_dotenv():
    """加载 $CH_DATA_DIR/.env 到 os.environ（不覆盖已有环境变量）"""
    env_path = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes"))) / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key not in os.environ:
            os.environ[key] = val.strip()
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
    _load_dotenv()
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



@gateway.command("setup")
@click.option("--host", default="127.0.0.1", help="监听地址")
@click.option("--port", default=18789, help="监听端口")
@click.option("--user", default=None, help="systemd 运行用户")
def setup_gw(host, port, user):
    """安装 Gateway 为系统服务 (systemd/launchd)"""
    from clawhermes.gateway.setup import install_gateway_service
    console.print("\n[bold cyan]Gateway 服务安装[/]\n")
    install_gateway_service(host=host, port=port, user=user)


@gateway.command("uninstall")
def uninstall_gw():
    """卸载 Gateway 系统服务"""
    from clawhermes.gateway.setup import uninstall_gateway_service
    uninstall_gateway_service()


@gateway.command("status")
def gw_status():
    """检查 Gateway 服务状态"""
    import json

    from clawhermes.gateway.setup import check_gateway_service_status

    st = check_gateway_service_status()
    console.print(json.dumps(st, indent=2, ensure_ascii=False))


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
@click.argument("section", required=False, type=click.Choice(["model", "channels", "gateway", "tools", "agent"]))
@click.option("--quick", is_flag=True, help="仅提示缺失/未设置的项目")
@click.option("--reset", is_flag=True, help="重置配置为默认值后重新配置")
def setup(non_interactive: bool = False, section: str | None = None, quick: bool = False, reset: bool = False):
    """初始化 — 支持分 section 运行 (model|channels|gateway|tools|agent)"""
    if not non_interactive and not sys.stdin.isatty():
        non_interactive = True

    # ══════════════════════════════════════════
    # 欢迎
    # ══════════════════════════════════════════
    console.print(Panel.fit(
        Text("ClawHermes · 初始化向导", style="bold cyan", justify="center"),
        border_style="cyan",
    ))

    env_vars: dict[str, str] = {}
    channels_enabled: list[str] = []

    if non_interactive:
        _setup_noninteractive(section=section, reset=reset)
        return

    # --reset: 先写默认配置
    if reset:
        from clawhermes.config import default_yaml, save_yaml
        save_yaml(default_yaml())
        console.print("  🔄 配置已重置为默认值")

    # --quick: 读取已有配置，仅补缺
    existing_config: dict = {}
    if quick:
        from clawhermes.config import load_yaml
        existing_config = load_yaml()
        console.print("  ⚡ 快速模式 — 仅提示缺失/未设置的项目")

    import questionary

    # 加载已有 .env 值（--quick 时跳过已设置项）
    existing_env: dict[str, str] = {}
    if quick:
        existing_env = _load_existing_env()

    model: str | None = existing_config.get("llm", {}).get("model", "") if quick else None
    gw_host: str = existing_config.get("gateway", {}).get("host", "127.0.0.1")
    gw_port: int = existing_config.get("gateway", {}).get("port", 18789)

    # ── 按 section 分发 ──
    if section == "model" or section is None:
        if section is None:
            console.print("\n[bold cyan]▶ Step 1/4[/]  [bold]LLM 提供商[/]\n")
        result = _setup_model_section(existing_config, existing_env, quick)
        if result is None:
            return
        env_vars.update(result.get("env", {}))
        model = result.get("model", model)
        if section == "model":
            _finalize_section(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port)
            return

    if section == "channels" or section is None:
        if section is None:
            console.print("\n[bold cyan]▶ Step 2/4[/]  [bold]消息渠道[/]\n")
        result = _setup_channels_section(channel_defs, existing_env, quick)
        if result is None:
            return
        env_vars.update(result.get("env", {}))
        channels_enabled = result.get("channels", [])
        if section == "channels":
            _finalize_section(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port)
            return

    if section == "gateway" or section is None:
        if section is None:
            console.print("\n[bold cyan]▶ Step 3/4[/]  [bold]Gateway 服务[/]\n")
        result = _setup_gateway_section(existing_config, existing_env, quick)
        if result is None:
            return
        env_vars.update(result.get("env", {}))
        gw_host = result.get("host", gw_host)
        gw_port = result.get("port", gw_port)
        if section == "gateway":
            _finalize_section(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port)
            return

    if section == "tools" or section is None:
        if section is None:
            pass  # tools 内联在完整流程
        result = _setup_tools_section(existing_config, existing_env, quick)
        if result:
            env_vars.update(result.get("env", {}))
        if section == "tools":
            _finalize_section(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port)
            return

    if section == "agent" or section is None:
        if section is None:
            pass
        result = _setup_agent_section(existing_config, existing_env, quick)
        if result:
            env_vars.update(result.get("env", {}))
        if section == "agent":
            _finalize_section(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port)
            return

    # ── 完整流程: 确认 + 生成 ──
    console.print("\n[bold cyan]▶ Step 4/4[/]  [bold]确认配置[/]\n")
    summary = Table(box=box.SIMPLE, show_header=False)
    summary.add_column("项", style="bold", width=16)
    summary.add_column("值")
    summary.add_row("LLM 模型", model or "(未设置)")
    summary.add_row("渠道", ", ".join(str(channel_defs[c]["name"]) for c in channels_enabled) if channels_enabled else "(无)")
    summary.add_row("Gateway", f"{gw_host}:{gw_port}")
    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    summary.add_row("数据目录", str(data_dir))
    console.print(summary)
    if not questionary.confirm("\n确认生成配置?", default=True).ask():
        console.print("  ⚠️  已取消")
        return
    _apply_setup(env_vars, channels_enabled, channel_defs, model or "deepseek/deepseek-chat", gw_host, gw_port)

# ====== Channel definitions (shared across sections) ======

channel_defs: dict[str, dict] = {
    "lark": {
        "name": "飞书 (Feishu/Lark)",
        "bot_url": "https://open.feishu.cn/app",
        "guide": "创建企业自建应用 → 添加「机器人」能力 → 获取 App ID / Secret",
        "vars": [
            ("FEISHU_APP_ID", "App ID"),
            ("FEISHU_APP_SECRET", "App Secret"),
            ("FEISHU_VERIFY_TOKEN", "Verify Token"),
            ("FEISHU_ENCRYPT_KEY", "Encrypt Key"),
        ],
    },
    "weixin": {
        "name": "微信 (WeChat)",
        "bot_url": "https://mp.weixin.qq.com/",
        "guide": "公众号后台 → 开发 → 基本配置 → 获取 AppID / AppSecret",
        "vars": [
            ("WECHAT_APP_ID", "App ID"),
            ("WECHAT_APP_SECRET", "App Secret"),
            ("WECHAT_TOKEN", "Token"),
            ("WECHAT_ENCODING_AES_KEY", "Encoding AES Key"),
        ],
    },
    "qq": {
        "name": "QQ Bot",
        "bot_url": "https://q.qq.com/qqbot/",
        "guide": "QQ 开放平台 → 创建机器人 → 获取 BotAppID / Token / Secret",
        "vars": [
            ("QQ_APP_ID", "Bot App ID"),
            ("QQ_TOKEN", "Bot Token"),
            ("QQ_SECRET", "Bot Secret"),
        ],
    },
}


# ====== Section: Model ======

_providers: list[dict] = [
    {"name": "DeepSeek",        "prefix": "deepseek/deepseek-chat",           "key": "DEEPSEEK_API_KEY",  "url": "https://platform.deepseek.com/api_keys", "api_base": "https://api.deepseek.com/v1"},
    {"name": "OpenAI",          "prefix": "openai/gpt-4o",                     "key": "OPENAI_API_KEY",    "url": "https://platform.openai.com/api-keys"},
    {"name": "Anthropic",       "prefix": "anthropic/claude-sonnet-4-20250514","key": "ANTHROPIC_API_KEY",  "url": "https://console.anthropic.com/keys"},
    {"name": "Google Gemini",   "prefix": "gemini/gemini-2.5-flash",           "key": "GOOGLE_API_KEY",    "url": "https://aistudio.google.com/apikey"},
    {"name": "Groq",            "prefix": "groq/llama-4-scout-17b-16e",        "key": "GROQ_API_KEY",      "url": "https://console.groq.com/keys"},
    {"name": "Together AI",     "prefix": "together_ai/meta-llama/Llama-4",   "key": "TOGETHERAI_API_KEY","url": "https://api.together.xyz/settings/api-keys"},
    {"name": "Fireworks AI",    "prefix": "fireworks_ai/llama-v3p1-405b",      "key": "FIREWORKS_API_KEY", "url": "https://fireworks.ai/account/api-keys"},
    {"name": "Mistral",         "prefix": "mistral/mistral-large-latest",      "key": "MISTRAL_API_KEY",   "url": "https://console.mistral.ai/api-keys/"},
    {"name": "Cohere",          "prefix": "command-r-plus",                    "key": "COHERE_API_KEY",    "url": "https://dashboard.cohere.com/api-keys"},
    {"name": "xAI / Grok",      "prefix": "xai/grok-3",                        "key": "XAI_API_KEY",       "url": "https://x.ai/api"},
    {"name": "Ollama (本地)",    "prefix": "ollama/qwen2.5",                    "key": None,                "url": None},
    {"name": "OpenRouter",      "prefix": "openrouter/openai/gpt-4o",          "key": "OPENROUTER_API_KEY","url": "https://openrouter.ai/keys"},
    {"name": "vLLM (自部署)",    "prefix": "openai/hosted_vllm/MODEL_NAME",     "key": "VLLM_API_KEY",      "url": None},
    {"name": "自定义 (litellm)", "prefix": "",                                  "key": None,                "url": None},
]


_models_by_provider: dict[str, list[tuple[str, str]]] = {
    "deepseek": [("deepseek/deepseek-chat", "旗舰通用"), ("deepseek/deepseek-reasoner", "深度推理 (R1)")],
    "openai": [("openai/gpt-4o", "旗舰多模态"), ("openai/gpt-4o-mini", "轻量快速"), ("openai/o3-mini", "推理")],
    "anthropic": [("anthropic/claude-sonnet-4-20250514", "Sonnet 4"), ("anthropic/claude-3-5-haiku-20241022", "Haiku 3.5")],
    "gemini": [("gemini/gemini-2.5-flash", "Flash 2.5"), ("gemini/gemini-2.5-pro", "Pro 2.5")],
    "groq": [("groq/llama-4-scout-17b-16e", "Llama 4 Scout"), ("groq/llama-3.3-70b-versatile", "Llama 3.3 70B")],
    "together_ai": [("together_ai/meta-llama/Llama-4-Maverick-17B-128E", "Llama 4 Maverick")],
    "fireworks_ai": [("fireworks_ai/llama-v3p1-405b-instruct", "Llama 3.1 405B")],
    "mistral": [("mistral/mistral-large-latest", "Large"), ("mistral/mistral-small-latest", "Small")],
    "cohere": [("command-r-plus", "Command R+")],
    "xai": [("xai/grok-3", "Grok 3")],
    "ollama": [("ollama/qwen2.5", "Qwen 2.5"), ("ollama/llama3.2", "Llama 3.2")],
    "openrouter": [("openrouter/openai/gpt-4o", "GPT-4o"), ("openrouter/anthropic/claude-sonnet-4-20250514", "Claude Sonnet 4")],
}

_prov_to_model_key: dict[str, str | None] = {
    "deepseek": "deepseek", "openai": "openai", "anthropic": "anthropic",
    "google_gemini": "gemini", "groq": "groq", "together_ai": "together_ai",
    "fireworks_ai": "fireworks_ai", "mistral": "mistral", "cohere": "cohere",
    "xai_/_grok": "xai", "ollama_本地": "ollama", "openrouter": "openrouter",
    "vllm_自部署": None, "自定义_litellm": None,
}


# ====== Section helpers ======

def _load_existing_env() -> dict[str, str]:
    """读取已有 .env 中的键值对"""
    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    env_path = data_dir / ".env"
    result: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _quick_skip(key: str, existing: dict, existing_env: dict) -> bool:
    """在 --quick 模式下检查是否可跳过（已设置）"""
    return bool(existing.get(key) or existing_env.get(key))


def _finalize_section(env_vars: dict, channels_enabled: list,
                      channel_defs: dict, model: str | None,
                      gw_host: str, gw_port: int) -> None:
    """单 section 结束后的配置写入 — 委托给 _apply_setup"""
    _apply_setup(env_vars, channels_enabled, channel_defs,
                 model or "deepseek/deepseek-chat", gw_host, gw_port)


def _setup_model_section(existing_config: dict, existing_env: dict, quick: bool) -> dict | None:
    """LLM 提供商 + 模型选择"""
    import questionary
    env_vars: dict[str, str] = {}

    if quick and existing_config.get("llm", {}).get("model"):
        console.print("  ⏭️  LLM 已配置, 跳过")
        return {"env": env_vars, "model": existing_config["llm"]["model"]}

    choices = [f"{p['name']:20s} {p['prefix']}" for p in _providers]
    selection = questionary.select(
        "选择 LLM 提供商 (↑↓ 移动, / 搜索):",
        choices=choices, use_indicator=True,
        style=questionary.Style([('qmark', 'fg:cyan bold'), ('selected', 'fg:green bold')]),
    ).ask()
    if not selection:
        console.print("  ⚠️  已取消")
        return None

    idx = choices.index(selection)
    provider = _providers[idx]
    pfx = provider["prefix"]

    if provider["key"]:
        if quick and _quick_skip(provider["key"], {}, existing_env):
            console.print(f"  ⏭️  {provider['key']} 已设置, 跳过")
        else:
            if provider.get("url"):
                console.print(f"  🔗 获取 Key: [link={provider['url']}]{provider['url']}[/]")
            api_key = questionary.password(f"{provider['key']} (输入隐藏):").ask()
            if api_key:
                env_vars[provider["key"]] = api_key
                console.print("  ✅ API Key 已设置")
    elif provider["name"] == "Ollama (本地)":
        base_url = questionary.text("Ollama 地址:", default="http://localhost:11434").ask()
        if base_url:
            env_vars["OLLAMA_BASE_URL"] = base_url
    elif provider["name"] == "vLLM (自部署)":
        vllm_url = questionary.text("vLLM API Base:", default="http://localhost:8000/v1").ask()
        if vllm_url:
            env_vars["OPENAI_BASE_URL"] = vllm_url
            api_key = questionary.password("vLLM API Key (可选):").ask()
            if api_key:
                env_vars["OPENAI_API_KEY"] = api_key
    elif provider["name"] == "自定义 (litellm)":
        base_url = questionary.text("API Base URL (可选):", default="").ask()
        if base_url:
            env_vars["CUSTOM_LLM_BASE_URL"] = base_url
        custom_key = questionary.password("API Key (可选):").ask()
        if custom_key:
            env_vars["CUSTOM_LLM_API_KEY"] = custom_key

    prov_key = provider["name"].lower().replace(" ", "_").replace("(", "").replace(")", "")
    model_key = _prov_to_model_key.get(prov_key)
    model: str | None = None
    if model_key and model_key in _models_by_provider:
        model_choices = [
            questionary.Choice(title=f"{m[0]:50s} {m[1]}", value=m[0])
            for m in _models_by_provider[model_key]
        ]
        model_choices.append(questionary.Choice(title="🔄 从 API 获取模型列表 (需要已设置 API Key)", value="__fetch__"))
        model_choices.append(questionary.Choice(title="✎ 自定义 litellm 模型标识 ...", value="__custom__"))
        model = questionary.select(
            f"选择 {provider['name']} 模型 (↑↓ 移动, / 搜索):",
            choices=model_choices, use_indicator=True,
        ).ask()
        if model == "__custom__":
            model = questionary.text("自定义 litellm 模型标识:", default=pfx).ask()
        elif model == "__fetch__":
            model = _fetch_models_from_api(provider, pfx)
    else:
        model = questionary.text(f"自定义模型标识 (Enter 确认 = {pfx}):", default=pfx).ask()

    if model:
        env_vars["CH_LLM_DEFAULT_MODEL"] = model.strip()
        console.print(f"  ✅ LLM: {model.strip()}")

    return {"env": env_vars, "model": model.strip() if model else "deepseek/deepseek-chat"}


def _ensure_lark_sdk() -> None:
    """确保 lark_oapi 已安装，若未安装则自动 pip install"""
    try:
        import lark_oapi  # noqa: F401
        return
    except ImportError:
        pass

    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parent.parent.parent
    lark_dir = repo_root / "clawhermes-lark"
    if not (lark_dir / "pyproject.toml").exists():
        console.print("  ⚠️  clawhermes-lark 子仓库未找到")
        console.print("  请手动: git clone <url> clawhermes-lark && pip install -e ./clawhermes-lark")
        return

    console.print("  📦 正在安装 clawhermes-lark ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(lark_dir)],
            capture_output=True, check=True,
        )
        console.print("  ✅ clawhermes-lark 安装完成")
    except subprocess.CalledProcessError as e:
        console.print(f"  ❌ 安装失败: {e}")
        console.print("  手动安装: pip install -e ./clawhermes-lark")

def _setup_channels_section(channel_defs: dict, existing_env: dict, quick: bool) -> dict | None:
    """消息渠道选择"""
    import questionary
    env_vars: dict[str, str] = {}
    channels_enabled: list[str] = []

    ch_choices = [
        questionary.Choice(title=f"{v['name']:25s} {v['guide'][:40]}...", value=k)
        for k, v in channel_defs.items()
    ]
    selected = questionary.checkbox(
        "选择要启用的消息渠道 (Space 选中/取消, ↑↓ 移动):",
        choices=ch_choices,
        style=questionary.Style([('selected', 'fg:green bold')]),
    ).ask()
    if selected is None:
        console.print("  ⚠️  渠道配置已跳过")
        return {"env": env_vars, "channels": []}

    channels_enabled = list(selected)
    for ch_id in channels_enabled:
        ch_def = channel_defs[ch_id]
        if ch_id == "lark":
            _ensure_lark_sdk()
            _onboard_feishu(env_vars, existing_env=existing_env if quick else {})
            continue
        console.print(f"\n  [bold]{ch_def['name']}[/]")
        if ch_def.get("bot_url"):
            console.print(f"  🔗 创建 Bot: [link={ch_def['bot_url']}]{ch_def['bot_url']}[/]")
        console.print(f"  📋 {ch_def['guide']}")
        for var_name, desc in ch_def["vars"]:
            if quick and _quick_skip(var_name, {}, existing_env):
                console.print(f"    ⏭️  {desc} ({var_name}) 已设置")
                continue
            val = questionary.password(f"    {desc} ({var_name}):").ask()
            if val:
                env_vars[var_name] = val
        console.print(f"  ✅ {ch_def['name']} 已配置")

    return {"env": env_vars, "channels": channels_enabled}


def _setup_gateway_section(existing_config: dict, existing_env: dict, quick: bool) -> dict | None:
    """Gateway 服务配置（对齐 openclaw gateway wizard: loopback/lan/custom 模式）"""
    import questionary
    env_vars: dict[str, str] = {}

    default_host = existing_config.get("gateway", {}).get("host", "127.0.0.1")
    default_port = str(existing_config.get("gateway", {}).get("port", 18789))

    bind_mode = questionary.select(
        "Gateway 绑定模式:",
        choices=[
            questionary.Choice(title="loopback — 仅本机访问 (推荐)", value="loopback"),
            questionary.Choice(title="lan — 局域网内可访问", value="lan"),
            questionary.Choice(title="custom — 自定义地址", value="custom"),
        ],
    ).ask()
    if not bind_mode:
        return None

    if bind_mode == "loopback":
        gw_host = "127.0.0.1"
    elif bind_mode == "lan":
        gw_host = "0.0.0.0"
    else:
        gw_host = questionary.text("监听地址:", default=default_host).ask()
        if not gw_host:
            return None

    gw_port_str = questionary.text(
        "监听端口:", default=default_port,
        validate=lambda v: v.isdigit() and 1 <= int(v) <= 65535,
    ).ask()
    if not gw_port_str:
        return None
    gw_port = int(gw_port_str)

    if gw_host not in ("127.0.0.1", "localhost"):
        gw_secret = questionary.password(
            "Gateway Secret (非本地监听必须, >=16 字符):",
            validate=lambda v: len(v) >= 16,
        ).ask()
        if not gw_secret:
            console.print("  ⚠️  非本地监听必须设置 Gateway Secret, 已取消")
            return None
        env_vars["CH_GATEWAY_SECRET"] = gw_secret
    else:
        gw_secret = questionary.password("Gateway Secret (可选, 回车跳过):").ask()
        if gw_secret:
            env_vars["CH_GATEWAY_SECRET"] = gw_secret

    env_vars["CH_GATEWAY_HOST"] = gw_host
    env_vars["CH_GATEWAY_PORT"] = str(gw_port)
    console.print(f"  ✅ Gateway: {gw_host}:{gw_port}")
    return {"env": env_vars, "host": gw_host, "port": gw_port}


def _setup_tools_section(existing_config: dict, existing_env: dict, quick: bool) -> dict | None:
    """工具集配置"""
    import questionary
    env_vars: dict[str, str] = {}

    current = existing_config.get("tools", {}).get("profile", "standard")
    if quick and existing_config.get("tools", {}).get("profile"):
        console.print(f"  ⏭️  工具集已配置: {current}")
        return {"env": env_vars}

    profile = questionary.select(
        "工具集级别:",
        choices=[
            questionary.Choice(title="minimal (5 工具 — 最安全)", value="minimal"),
            questionary.Choice(title="standard (9 工具 — 推荐)", value="standard"),
            questionary.Choice(title="full (35 工具 — 全部开放)", value="full"),
        ],
        default=current or "standard",
    ).ask()
    if profile:
        env_vars["CH_TOOLS_PROFILE"] = profile
    console.print(f"  ✅ 工具集: {profile or 'standard'}")
    return {"env": env_vars}


def _setup_agent_section(existing_config: dict, existing_env: dict, quick: bool) -> dict | None:
    """Agent 设置"""
    import questionary
    env_vars: dict[str, str] = {}

    current_iters = existing_config.get("agent", {}).get("max_iterations", 50)
    if quick and existing_config.get("agent", {}).get("max_iterations"):
        console.print(f"  ⏭️  Agent 已配置: max_iterations={current_iters}")
        return {"env": env_vars}

    max_iter = questionary.text(
        "最大迭代次数:", default=str(current_iters),
        validate=lambda v: v.isdigit() and int(v) > 0,
    ).ask()
    if max_iter:
        env_vars["CH_AGENT_MAX_ITERATIONS"] = str(max_iter)

    compress_threshold = existing_config.get("context", {}).get("compress_threshold", 0.75)
    threshold = questionary.text(
        "上下文压缩阈值 (0.0-1.0):", default=str(compress_threshold),
        validate=lambda v: v.replace(".", "").isdigit() and 0 < float(v) <= 1.0,
    ).ask()
    if threshold:
        env_vars["CH_CONTEXT_COMPRESS_THRESHOLD"] = threshold

    console.print(f"  ✅ Agent: max_iterations={max_iter}, compress_threshold={threshold}")
    return {"env": env_vars}




def _setup_noninteractive(section: str | None = None, reset: bool = False):
    """CI/Docker 静默初始化"""
    env_vars: dict[str, str] = {
        "CH_LLM_DEFAULT_MODEL": "deepseek/deepseek-chat",
        "CH_GATEWAY_HOST": "127.0.0.1",
        "CH_GATEWAY_PORT": "18789",
    }
    if reset:
        from clawhermes.config import default_yaml, save_yaml
        save_yaml(default_yaml())
        console.print("  🔄 配置已重置为默认值")
    console.print("  ⚠️  非交互模式 — 使用默认值")
    if section in (None, "model"):
        console.print("  LLM: deepseek/deepseek-chat (请手动设置 DEEPSEEK_API_KEY)")
    if section in (None, "gateway"):
        console.print("  Gateway: 127.0.0.1:18789")
    _apply_setup(env_vars, [], {}, "deepseek/deepseek-chat", "127.0.0.1", 18789)



def _fetch_models_from_api(provider, default_model):
    """尝试从 API 动态获取模型列表, 失败则回退到自定义输入"""
    import json
    import urllib.error
    import urllib.request

    key_var = provider.get("key")
    api_key = os.environ.get(key_var, "") if key_var else ""

    models: list[tuple[str, str]] = []

    provider_name = provider["name"]
    try:
        if provider_name == "Ollama (本地)":
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            req = urllib.request.Request(f"{base}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if name:
                        models.append((f"ollama/{name}", ""))
        elif provider_name == "OpenAI" and api_key:
            req = urllib.request.Request("https://api.openai.com/v1/models")
            req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    if mid and not mid.startswith(("ft:", "davinci", "babbage", "ada")):
                        models.append((f"openai/{mid}", ""))
        elif provider_name in ("DeepSeek", "OpenRouter") and api_key:
            api_base = provider.get("api_base", "https://api.deepseek.com/v1" if provider_name == "DeepSeek" else "https://openrouter.ai/api/v1")
            req = urllib.request.Request(f"{api_base}/models")
            req.add_header("Authorization", f"Bearer {api_key}")
            prefix = "deepseek/" if provider_name == "DeepSeek" else "openrouter/"
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    if mid:
                        models.append((f"{prefix}{mid}", ""))
    except Exception as e:
        console.print(f"  [yellow]⚠️  动态获取失败: {e}[/]")

    if models:
        import questionary
        models.sort(key=lambda x: x[0])
        model_choices = [
            questionary.Choice(title=f"{m[0]:70s}", value=m[0])
            for m in models[:50]
        ]
        if len(models) > 50:
            model_choices.append(questionary.Choice(
                title=f"... 还有 {len(models)-50} 个模型, 请用自定义输入",
                value=None, disabled="true"))
        model_choices.append(questionary.Choice(title="✎ 自定义 litellm 模型标识 ...", value="__custom__"))
        model = questionary.select(
            f"{provider_name} 在线模型 ({len(models)} 个, ↑↓ 移动, / 搜索):",
            choices=model_choices,
            use_indicator=True,
        ).ask()
        if model == "__custom__":
            return _ask_custom_model(default_model)
        return model

    console.print("  [yellow]⚠️  无法获取模型列表, 请手动输入[/]")
    return _ask_custom_model(default_model)


def _ask_custom_model(default_model):
    import questionary
    return questionary.text(
        "自定义 litellm 模型标识:",
        default=default_model,
    ).ask()

def _apply_setup(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port):
    """执行配置生成"""
    _write_env(env_vars)
    console.print("  ✅ .env 已生成")
    from clawhermes.config import default_yaml, save_yaml
    cfg = default_yaml()
    cfg["llm"]["model"] = model
    cfg["gateway"]["host"] = gw_host
    cfg["gateway"]["port"] = gw_port
    save_yaml(cfg)
    console.print("  ✅ config.yaml 已生成")
    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    channels_dir = data_dir / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)
    for ch_id in channels_enabled:
        example_path = {
            "lark": "config/channels/feishu.yaml.example",
            "weixin": "config/channels/wechat.yaml.example",
            "qq": "config/channels/qq.yaml.example",
        }.get(ch_id, "")
        if example_path:
            _copy_and_populate_channel(example_path, channels_dir, ch_id, env_vars)
            console.print(f"  ✅ channels/{ch_id}.yaml 已生成")
    from clawhermes.agent.agent_mgr import create_agent
    create_agent("default")
    console.print("  ✅ Agent 已初始化")
    for sub in ["skills", "providers"]:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    # 自检
    console.print("\n[bold cyan]▶ 自检[/]\n")
    ok = True
    console.print(f"  ✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    for pkg in ["litellm", "fastapi", "rich", "yaml", "questionary"]:
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
            console.print(f"  ⚠️  clawhermes-{ch_id} 未安装")
    if ok:
        console.print("\n[bold green]🎉 ClawHermes 初始化完成![/]")
        console.print(f"  📁 配置文件: {data_dir}")
        console.print("  🚀 启动: clawhermes gateway start")
    else:
        console.print("\n[bold yellow]⚠️  部分依赖缺失, 请运行 pip install -e . 后重试[/]")




def _onboard_feishu(env_vars: dict[str, str], existing_env: dict | None = None):
    """飞书渠道引导 — 直接调用 clawhermes-lark 的 app_registration 逻辑"""
    import asyncio
    import questionary

    console.print("\n  [bold]飞书 (Feishu/Lark)[/]")

    # ── 选择创建方式 ──
    method = questionary.select(
        "  选择配置方式:",
        choices=[
            questionary.Choice(title="📱 扫码创建 — 飞书 App 扫码自动创建应用 (推荐)", value="scan"),
            questionary.Choice(title="⌨️  手动配置 — 在 open.feishu.cn 手动创建后填入凭证", value="manual"),
        ],
        default="scan",
    ).ask()
    if not method:
        return

    if method == "scan":
        result = _run_scan_to_create(env_vars)
        if result is None:
            return
    else:
        result = _run_manual_feishu_setup(env_vars)
        if result is None:
            return

    console.print("  ✅ 飞书 (Feishu/Lark) 已配置")


def _run_scan_to_create(env_vars: dict) -> dict | None:
    """扫码创建飞书应用 — 调用 clawhermes-lark app_registration"""
    import asyncio
    import questionary

    # 域名选择
    domain = questionary.select(
        "  选择平台:",
        choices=[
            questionary.Choice(title="feishu.cn  (飞书·中国)", value="feishu"),
            questionary.Choice(title="larksuite.com  (Lark·国际)", value="lark"),
        ],
        default="feishu",
    ).ask()
    if not domain:
        return None

    try:
        from clawhermes_lark.openclaw_lark.core.app_registration import (
            app_registration_begin,
            render_qr_terminal,
            run_qr_code_app_creation,
        )
    except ImportError:
        console.print("  ⚠️  clawhermes-lark 未安装，回退到手动配置")
        return _run_manual_feishu_setup(env_vars)

    # Step 1: begin → 获取 QR URL
    with console.status("  🔍 正在初始化..."):
        begin_result = asyncio.run(app_registration_begin(domain))
    if not begin_result.ok:
        console.print(f"  ⚠️  初始化失败: {begin_result.error}")
        console.print("  回退到手动配置...")
        return _run_manual_feishu_setup(env_vars)

    # Step 2: 展示 QR 码 + 引导
    try:
        qr_text = render_qr_terminal(begin_result.verification_uri_complete)
    except Exception:
        qr_text = f"[QR Code]\n{begin_result.verification_uri_complete}"

    console.print(f"\n{qr_text}\n")
    console.print(f"  📱 请使用飞书 App 扫描上方二维码")
    console.print(f"  🔑 授权码: {begin_result.user_code}")
    console.print(f"  ⏰ 有效期: {begin_result.expire_in // 60} 分钟")
    console.print()

    # Step 3: 轮询授权结果
    console.print("  ⏳ 等待扫码授权 (可 Ctrl+C 取消)...")
    try:
        poll_result = asyncio.run(run_qr_code_app_creation(domain))
    except KeyboardInterrupt:
        console.print("\n  ⚠️  已取消")
        return None

    if not poll_result.ok:
        console.print(f"  ⚠️  扫码创建失败: {poll_result.error}")
        console.print("  回退到手动配置...")
        return _run_manual_feishu_setup(env_vars)

    # 拿到凭证
    app_id = poll_result.client_id
    app_secret = poll_result.client_secret
    owner_open_id = poll_result.open_id

    console.print(f"  ✅ 应用已创建: {app_id[:12]}***")
    env_vars["FEISHU_APP_ID"] = app_id
    env_vars["FEISHU_APP_SECRET"] = app_secret
    if domain != "feishu":
        env_vars["FEISHU_DOMAIN"] = domain

    # 连接测试
    _probe_feishu(app_id, app_secret, domain, env_vars)

    # 安全策略
    _setup_feishu_security(env_vars, owner_open_id)

    return {"app_id": app_id, "app_secret": app_secret, "domain": domain}


def _run_manual_feishu_setup(env_vars: dict) -> dict | None:
    """手动配置飞书 — 用户在 open.feishu.cn 手动创建后填入凭证"""
    import questionary

    console.print("  🔗 创建应用: [link=https://open.feishu.cn/app]https://open.feishu.cn/app[/]")
    console.print("  📋 1) 创建企业自建应用 → 2) 添加「机器人」能力")
    console.print("  📋 3) 权限: im:message, im:chat, contact:user.base:readonly")
    console.print("  📋 4) 发布应用或添加测试用户\n")

    app_id = questionary.text("  App ID:", validate=lambda v: bool(v.strip())).ask()
    if not app_id:
        return None
    app_secret = questionary.password("  App Secret:", validate=lambda v: bool(v.strip())).ask()
    if not app_secret:
        return None

    domain = questionary.select(
        "  选择域名:",
        choices=[
            questionary.Choice(title="feishu.cn  (飞书·中国)", value="feishu"),
            questionary.Choice(title="larksuite.com  (Lark·国际)", value="lark"),
        ],
        default="feishu",
    ).ask()
    if not domain:
        return None

    env_vars["FEISHU_APP_ID"] = app_id
    env_vars["FEISHU_APP_SECRET"] = app_secret
    if domain != "feishu":
        env_vars["FEISHU_DOMAIN"] = domain

    # 连接测试
    _probe_feishu(app_id, app_secret, domain, env_vars)

    # 安全策略（无 owner open_id，用户手动控制）
    _setup_feishu_security(env_vars, owner_open_id="")

    return {"app_id": app_id, "app_secret": app_secret, "domain": domain}


def _probe_feishu(app_id: str, app_secret: str, domain: str, env_vars: dict) -> None:
    """测试飞书连接"""
    console.print("\n  🔍 正在测试连接...")
    try:
        import lark_oapi as lark
        from lark_oapi.api.verification.v1 import GetBotInfoRequest

        dom = lark.Domain.FEISHU if domain == "feishu" else lark.Domain.LARK
        client = lark.Client.builder().app_id(app_id).app_secret(app_secret).domain(dom).build()
        resp = client.verification.v1.bot_info.get(GetBotInfoRequest())
        if resp.success() and resp.data:
            bot_name = getattr(resp.data, "name", "") or app_id
            console.print(f"  ✅ 连接成功 → 机器人: [bold green]{bot_name}[/]")
            env_vars["FEISHU_BOT_NAME"] = bot_name
        else:
            console.print("  ⚠️  连接测试失败, 请检查凭证是否正确")
    except ImportError:
        console.print("  ⚠️  lark_oapi 未安装，跳过连接测试")
    except Exception as e:
        console.print(f"  ⚠️  连接测试失败: {e}")


def _setup_feishu_security(env_vars: dict, owner_open_id: str = "") -> None:
    """配置飞书安全策略（群聊策略 + 安全警告）"""
    import questionary

    # 群聊策略
    console.print("\n  [bold]群聊策略[/]")
    group_policy = questionary.select(
        "  群聊访问策略:",
        choices=[
            questionary.Choice(title="allowlist — 仅白名单用户可触发 (推荐)", value="allowlist"),
            questionary.Choice(title="open — 任何人 @提及即可触发", value="open"),
            questionary.Choice(title="disabled — 禁用群聊", value="disabled"),
        ],
        default="allowlist",
    ).ask()
    if group_policy:
        env_vars["FEISHU_GROUP_POLICY"] = group_policy

    # Webhook 安全
    if questionary.confirm("  配置 Webhook 安全验证? (推荐)", default=True).ask():
        verify_token = questionary.password("  Verify Token:").ask()
        if verify_token:
            env_vars["FEISHU_VERIFY_TOKEN"] = verify_token
        encrypt_key = questionary.password("  Encrypt Key:").ask()
        if encrypt_key:
            env_vars["FEISHU_ENCRYPT_KEY"] = encrypt_key

    # Security check — use clawhermes-lark's security module
    try:
        from clawhermes_lark.openclaw_lark.core.security import collect_security_warnings
        feishu_cfg = {
            "group_policy": group_policy or "allowlist",
            "connection_mode": "websocket",
            "encrypt_key": env_vars.get("FEISHU_ENCRYPT_KEY", ""),
            "verification_token": env_vars.get("FEISHU_VERIFY_TOKEN", ""),
            "allow_bots": "none",
        }
        warnings_list = collect_security_warnings(feishu_cfg=feishu_cfg, account_id="default")
        if warnings_list:
            console.print("\n  [yellow]⚡ 安全提示:[/]")
            for w in warnings_list:
                console.print(f"    {w}")
    except ImportError:
        pass


def _write_env(vars_dict: dict[str, str]):
    """写入 .env 文件（不覆盖已有密钥，阻断危险环境变量）"""
    from clawhermes.config import is_env_var_safe

    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    data_dir.mkdir(parents=True, exist_ok=True)
    env_path = data_dir / ".env"
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    lines_out = [
        "# ============================================================",
        "# ClawHermes · 环境变量配置",
        "# 由 clawhermes setup 生成",
        "# ============================================================",
        "",
    ]
    blocked_count = 0
    for k, v in vars_dict.items():
        if not is_env_var_safe(k):
            console.print(f"  ⚠️  阻断危险环境变量写入: {k}", style="yellow")
            blocked_count += 1
            continue
        if k in existing and existing[k] and ("KEY" in k or "SECRET" in k or "TOKEN" in k):
            lines_out.append(f"{k}={existing[k]}  # (保留已有)")
        else:
            lines_out.append(f"{k}={v}")
    if blocked_count:
        console.print(f"  ⚠️  已阻断 {blocked_count} 个危险环境变量，防止子进程注入")
    env_path.write_text("\n".join(lines_out) + "\n")


def _copy_and_populate_channel(example_path: str, dest_dir: Path, ch_id: str, env_vars: dict[str, str]):
    """复制渠道 YAML 示例到配置目录，并用 env_vars 填充 ${VAR} 占位符"""
    import re
    import shutil
    repo_root = Path(__file__).resolve().parent.parent.parent
    src = repo_root / example_path
    dst = dest_dir / f"{ch_id}.yaml"
    if src.exists():
        content = src.read_text()
        # Replace ${VAR_NAME} placeholders with actual env values
        def _replace_env_ref(m: re.Match) -> str:
            var_name: str = m.group(1)
            fallback: str = m.group(0)
            return env_vars.get(var_name, fallback)
        content = re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}', _replace_env_ref, content)
        dst.write_text(content)
        if not dst.exists():
            shutil.copy(src, dst)

def _copy_channel_example(example_path: str, dest_dir: Path, ch_id: str):
    """复制渠道 YAML 示例到配置目录（兼容旧调用）"""
    import shutil
    repo_root = Path(__file__).resolve().parent.parent.parent
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
