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
    """初始化 — 键盘导航 + 搜索筛选 LLM/渠道/Gateway"""
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
        _setup_noninteractive()
        return

    import questionary

    # ══════════════════════════════════════════
    # Step 1: LLM
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 1/4[/]  [bold]LLM 提供商[/]\n")

    # 动态提供商列表 (litellm 兼容)
    _providers = [
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

    choices = [f"{p['name']:20s} {p['prefix']}" for p in _providers]  # type: ignore[index]
    selection = questionary.select(
        "选择 LLM 提供商 (↑↓ 移动, / 搜索):",
        choices=choices,
        use_indicator=True,
        style=questionary.Style([
            ('qmark', 'fg:cyan bold'),
            ('selected', 'fg:green bold'),
        ]),
    ).ask()
    if not selection:
        console.print("  ⚠️  已取消")
        return

    idx = choices.index(selection)
    provider = _providers[idx]
    pfx = provider["prefix"]  # type: ignore[index]

    # API Key
    if provider["key"]:  # type: ignore[index]
        if provider["url"]:  # type: ignore[index]
            console.print(f"  🔗 获取 Key: [link={provider['url']}]{provider['url']}[/]")  # type: ignore[index]
        api_key = questionary.password(f"{provider['key']} (输入隐藏):").ask()  # type: ignore[index]
        if api_key:
            env_vars[provider["key"]] = api_key  # type: ignore[index]
            console.print("  ✅ API Key 已设置")
    elif provider["name"] == "Ollama (本地)":  # type: ignore[index]
        base_url = questionary.text("Ollama 地址:", default="http://localhost:11434").ask()
        if base_url:
            env_vars["OLLAMA_BASE_URL"] = base_url
    elif provider["name"] == "vLLM (自部署)":  # type: ignore[index]
        vllm_url = questionary.text("vLLM API Base:", default="http://localhost:8000/v1").ask()
        if vllm_url:
            env_vars["OPENAI_BASE_URL"] = vllm_url
            api_key = questionary.password("vLLM API Key (可选):").ask()
            if api_key:
                env_vars["OPENAI_API_KEY"] = api_key
    elif provider["name"] == "自定义 (litellm)":  # type: ignore[index]
        base_url = questionary.text("API Base URL (可选):", default="").ask()
        if base_url:
            env_vars["CUSTOM_LLM_BASE_URL"] = base_url
        custom_key = questionary.password("API Key (可选):").ask()
        if custom_key:
            env_vars["CUSTOM_LLM_API_KEY"] = custom_key


    # ══════════════════════════════════════════
    # 该提供商的常用模型列表
    _models_by_provider: dict[str, list[tuple[str, str]]] = {
        "deepseek": [
            ("deepseek/deepseek-chat", "旗舰通用"),
            ("deepseek/deepseek-reasoner", "深度推理 (R1)"),
        ],
        "openai": [
            ("openai/gpt-4o", "旗舰多模态"),
            ("openai/gpt-4o-mini", "轻量快速"),
            ("openai/gpt-4-turbo", "Turbo"),
            ("openai/o3-mini", "推理"),
        ],
        "anthropic": [
            ("anthropic/claude-sonnet-4-20250514", "Sonnet 4"),
            ("anthropic/claude-3-5-haiku-20241022", "Haiku 3.5"),
        ],
        "gemini": [
            ("gemini/gemini-2.5-flash", "Flash 2.5"),
            ("gemini/gemini-2.5-pro", "Pro 2.5"),
            ("gemini/gemini-2.0-flash", "Flash 2.0"),
        ],
        "groq": [
            ("groq/llama-4-scout-17b-16e", "Llama 4 Scout"),
            ("groq/llama-3.3-70b-versatile", "Llama 3.3 70B"),
            ("groq/mixtral-8x7b-32768", "Mixtral 8x7B"),
        ],
        "together_ai": [
            ("together_ai/meta-llama/Llama-4-Maverick-17B-128E", "Llama 4 Maverick"),
            ("together_ai/deepseek-ai/DeepSeek-R1", "DeepSeek R1"),
        ],
        "fireworks_ai": [
            ("fireworks_ai/llama-v3p1-405b-instruct", "Llama 3.1 405B"),
            ("fireworks_ai/llama-v3p1-70b-instruct", "Llama 3.1 70B"),
        ],
        "mistral": [
            ("mistral/mistral-large-latest", "Large"),
            ("mistral/mistral-small-latest", "Small"),
            ("mistral/codestral-latest", "Codestral"),
        ],
        "cohere": [
            ("command-r-plus", "Command R+"),
            ("command-r", "Command R"),
        ],
        "xai": [
            ("xai/grok-3", "Grok 3"),
        ],
        "ollama": [
            ("ollama/qwen2.5", "Qwen 2.5"),
            ("ollama/llama3.2", "Llama 3.2"),
            ("ollama/mistral", "Mistral"),
            ("ollama/deepseek-r1", "DeepSeek R1"),
        ],
        "openrouter": [
            ("openrouter/openai/gpt-4o", "GPT-4o"),
            ("openrouter/anthropic/claude-sonnet-4-20250514", "Claude Sonnet 4"),
            ("openrouter/google/gemini-2.5-pro", "Gemini 2.5 Pro"),
        ],
    }

    # 提取 provider 的 key (如 "openai", "deepseek")
    prov_key = provider["name"].lower().replace(" ", "_").replace("(", "").replace(")", "")  # type: ignore[index]
    # 映射到模型 key
    _prov_to_model_key = {
        "deepseek": "deepseek", "openai": "openai", "anthropic": "anthropic",
        "google_gemini": "gemini", "groq": "groq", "together_ai": "together_ai",
        "fireworks_ai": "fireworks_ai", "mistral": "mistral", "cohere": "cohere",
        "xai_/_grok": "xai", "ollama_本地": "ollama", "openrouter": "openrouter",
        "vllm_自部署": None, "自定义_litellm": None,
    }
    model_key = _prov_to_model_key.get(prov_key)

    model = None
    if model_key and model_key in _models_by_provider:
        model_choices = [
            questionary.Choice(title=f"{m[0]:50s} {m[1]}", value=m[0])
            for m in _models_by_provider[model_key]
        ]
        model_choices.append(questionary.Choice(title="🔄 从 API 获取模型列表 (需要已设置 API Key)", value="__fetch__"))
        model_choices.append(questionary.Choice(title="✎ 自定义 litellm 模型标识 ...", value="__custom__"))
        model = questionary.select(
            f"选择 {provider['name']} 模型 (↑↓ 移动, / 搜索):",  # type: ignore[index]
            choices=model_choices,
            use_indicator=True,
        ).ask()
        if model == "__custom__":
            model = questionary.text(
                "自定义 litellm 模型标识:",
                default=pfx,
            ).ask()
        elif model == "__fetch__":
            model = _fetch_models_from_api(provider, pfx)
    else:
        model = questionary.text(
            f"自定义模型标识 (Enter 确认 = {pfx}):",
            default=pfx,
        ).ask()
    env_vars["CH_LLM_DEFAULT_MODEL"] = model.strip()
    console.print(f"  ✅ LLM: {model.strip()}")

    # Step 2: 消息渠道
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 2/4[/]  [bold]消息渠道[/]\n")

    channel_defs = {
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

    ch_choices = [
        questionary.Choice(
            title=f"{v['name']:25s} {v['guide'][:40]}...",
            value=k,
        )
        for k, v in channel_defs.items()
    ]
    selected = questionary.checkbox(
        "选择要启用的消息渠道 (Space 选中/取消, ↑↓ 移动):",
        choices=ch_choices,
        style=questionary.Style([('selected', 'fg:green bold')]),
    ).ask()
    if selected is None:
        console.print("  ⚠️  渠道配置已跳过")
    else:
        channels_enabled = list(selected)
        for ch_id in channels_enabled:
            ch_def = channel_defs[ch_id]
            if ch_id == "lark":
                _onboard_feishu(env_vars)
                continue
            console.print(f"\n  [bold]{ch_def['name']}[/]")
            if ch_def.get("bot_url"):
                console.print(f"  🔗 创建 Bot: [link={ch_def['bot_url']}]{ch_def['bot_url']}[/]")
            console.print(f"  📋 {ch_def['guide']}")
            for var_name, desc in ch_def["vars"]:
                val = questionary.password(f"    {desc} ({var_name}):").ask()
                if val:
                    env_vars[var_name] = val
            console.print(f"  ✅ {ch_def['name']} 已配置")

    # ══════════════════════════════════════════
    # Step 3: Gateway
    # ══════════════════════════════════════════
    console.print("\n[bold cyan]▶ Step 3/4[/]  [bold]Gateway 服务[/]\n")
    gw_host = questionary.text("监听地址:", default="127.0.0.1").ask()
    if gw_host is None:
        return
    gw_port_str = questionary.text("监听端口:", default="18789", validate=lambda v: v.isdigit()).ask()
    if gw_port_str is None:
        return
    gw_port = int(gw_port_str)
    if gw_host not in ("127.0.0.1", "localhost"):
        gw_secret = questionary.password("Gateway Secret (非本地监听必须):").ask()
        if not gw_secret:
            console.print("  ⚠️  非本地监听必须设置 Gateway Secret, 已取消")
            return
    else:
        gw_secret = questionary.password("Gateway Secret (可选):").ask()
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
    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))
    summary.add_row("数据目录", str(data_dir))
    console.print(summary)
    if not questionary.confirm("\n确认生成配置?", default=True).ask():
        console.print("  ⚠️  已取消")
        return
    _apply_setup(env_vars, channels_enabled, channel_defs, model, gw_host, gw_port)


def _setup_noninteractive():
    """CI/Docker 静默初始化"""
    env_vars: dict[str, str] = {
        "CH_LLM_DEFAULT_MODEL": "deepseek/deepseek-chat",
        "CH_GATEWAY_HOST": "127.0.0.1",
        "CH_GATEWAY_PORT": "18789",
    }
    console.print("  ⚠️  非交互模式 — 使用默认值")
    console.print("  LLM: deepseek/deepseek-chat (请手动设置 DEEPSEEK_API_KEY)")
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
            _copy_channel_example(example_path, channels_dir, ch_id)
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




def _onboard_feishu(env_vars: dict[str, str]):
    """飞书渠道引导 — 对齐 larksuite/openclaw-lark onboarding"""
    import questionary

    console.print("\n  [bold]飞书 (Feishu/Lark)[/]")
    console.print("  🔗 创建应用: [link=https://open.feishu.cn/app]https://open.feishu.cn/app[/]")
    console.print("  📋 1) 创建企业自建应用 → 2) 添加「机器人」能力")
    console.print("  📋 3) 权限: im:message, im:chat, contact:user.base:readonly")
    console.print("  📋 4) 发布应用或添加测试用户\n")

    # Step b: 凭证
    app_id = questionary.text("  App ID:", validate=lambda v: bool(v.strip())).ask()
    if not app_id:
        return
    app_secret = questionary.password("  App Secret:", validate=lambda v: bool(v.strip())).ask()
    if not app_secret:
        return

    # Step c: 域名选择
    domain = questionary.select(
        "  选择域名:",
        choices=[
            questionary.Choice(title="feishu.cn  (飞书·中国)", value="feishu"),
            questionary.Choice(title="larksuite.com  (Lark·国际)", value="lark"),
        ],
        default="feishu",
    ).ask()
    if not domain:
        return

    # Step d: 连接测试 (对齐 openclaw-lark probeFeishu)
    console.print("\n  🔍 正在测试连接...")
    try:
        import lark_oapi as lark
        from lark_oapi.api.verification.v1 import GetBotInfoRequest
        client = lark.Client.builder().app_id(app_id).app_secret(app_secret).domain(
            lark.Domain.FEISHU if domain == "feishu" else lark.Domain.LARK
        ).build()
        resp = client.verification.v1.bot_info.get(GetBotInfoRequest())
        if resp.success() and resp.data:
            bot_name = getattr(resp.data, "name", app_id) or app_id
            console.print(f"  ✅ 连接成功 → 机器人: [bold green]{bot_name}[/]")
            env_vars["FEISHU_BOT_NAME"] = bot_name
        else:
            console.print("  ⚠️  连接测试失败, 请检查凭证是否正确")
    except Exception as e:
        console.print(f"  ⚠️  连接测试失败: {e}")
        if not questionary.confirm("  凭证可能无效, 仍然保存?", default=True).ask():
            return

    env_vars["FEISHU_APP_ID"] = app_id
    env_vars["FEISHU_APP_SECRET"] = app_secret
    if domain != "feishu":
        env_vars["FEISHU_DOMAIN"] = domain

    # Step e: 可选安全字段
    if questionary.confirm("  配置 Webhook 安全验证? (推荐)", default=True).ask():
        verify_token = questionary.password("  Verify Token:").ask()
        if verify_token:
            env_vars["FEISHU_VERIFY_TOKEN"] = verify_token
        encrypt_key = questionary.password("  Encrypt Key:").ask()
        if encrypt_key:
            env_vars["FEISHU_ENCRYPT_KEY"] = encrypt_key

    # Step f: 群聊策略 (对齐 openclaw-lark groupPolicy)
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

    console.print("  ✅ 飞书 (Feishu/Lark) 已配置")


def _write_env(vars_dict: dict[str, str]):
    """写入 .env 文件（不覆盖已有密钥）"""
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
    for k, v in vars_dict.items():
        if k in existing and existing[k] and ("KEY" in k or "SECRET" in k or "TOKEN" in k):
            lines_out.append(f"{k}={existing[k]}  # (保留已有)")
        else:
            lines_out.append(f"{k}={v}")
    env_path.write_text("\n".join(lines_out) + "\n")


def _copy_channel_example(example_path: str, dest_dir: Path, ch_id: str):
    """复制渠道 YAML 示例到配置目录"""
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
    import subprocess
    _load_dotenv()
    data_dir = Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))

    console.print("[bold]ClawHermes Doctor[/]\n")

    py_ok = sys.version_info >= (3, 12)
    icon = "✅" if py_ok else "❌"
    console.print(f"{icon} Python {sys.version_info.major}.{sys.version_info.minor}" +
                 ("" if py_ok else " (需要 3.12+)"))

    for pkg, role in [("litellm", "llm"), ("fastapi", "web"), ("chromadb", "vector"),
                      ("rich", "cli"), ("yaml", "config"), ("click", "cli"),
                      ("questionary", "wizard"), ("pydantic", "validation")]:
        try:
            __import__(pkg.replace("-", "_"))
            console.print(f"  ✅ {pkg:15s} ({role})")
        except ImportError:
            console.print(f"  ❌ {pkg:15s} ({role}) — pip install {pkg}")

    for ch_id, ch_name in [("lark", "飞书"), ("weixin", "微信"), ("qq", "QQ")]:
        try:
            __import__(f"clawhermes_{ch_id}")
            console.print(f"  ✅ clawhermes-{ch_id:8s} ({ch_name})")
        except ImportError:
            console.print(f"  ⚠️  clawhermes-{ch_id:8s} ({ch_name}) — pip install -e ./clawhermes-{ch_id}")

    env_p = data_dir / ".env"
    yaml_p = data_dir / "config.yaml"
    console.print(f"  {'✅' if env_p.exists() else '⚠️'} .env ({'已存在' if env_p.exists() else '未找到 — clawhermes setup'})")
    console.print(f"  {'✅' if yaml_p.exists() else '⚠️'} config.yaml ({'已存在' if yaml_p.exists() else '未找到 — clawhermes setup'})")
    channels_dir = data_dir / "channels"
    if channels_dir.exists():
        for y in sorted(channels_dir.glob("*.yaml")):
            console.print(f"  ✅ channels/{y.name}")
    else:
        console.print("  ⚠️  channels/ 目录未创建")

    found = sorted(k for k in os.environ if k.endswith("_API_KEY") and os.environ[k])
    if found:
        for k in found[:5]:
            masked = os.environ[k][:8] + "..." if len(os.environ[k]) > 8 else "***"
            console.print(f"  ✅ {k}={masked}")
        if len(found) > 5:
            console.print(f"  ... 还有 {len(found)-5} 个 Key")
    else:
        console.print("  ⚠️  未设置 API Key — 在 .env 中配置")

    console.print(f"  ℹ️  Gateway: {os.getenv('CH_GATEWAY_HOST', '127.0.0.1')}:{os.getenv('CH_GATEWAY_PORT', '18789')}")

    try:
        result = subprocess.run(
            ["git", "submodule", "status"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            if line:
                status = "✅" if not line.startswith("-") else "⚠️  (未初始化)"
                parts = line.split()
                if len(parts) >= 2:
                    console.print(f"  {status} submodule: {parts[1]}")
    except Exception:
        pass



if __name__ == "__main__":
    main()
