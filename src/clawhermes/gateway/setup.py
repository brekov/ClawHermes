"""
ClawHermes - 渠道配置管理器
参照 OpenClaw 的设计，通过 gateway setup 命令配置，配置文件存储在 ~/.clawhermes/
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def get_config_path() -> Path:
    """获取渠道配置文件路径"""
    data_dir = Path(os.getenv("CH_DATA_DIR", Path.home() / ".clawhermes"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "channels.json"


def load_config() -> dict[str, Any]:
    """加载渠道配置"""
    path = get_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def save_config(config: dict[str, Any]):
    """保存渠道配置"""
    path = get_config_path()
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"  ✅ 配置已保存: {path}")


def set_channel(name: str, **kwargs):
    """设置单个渠道配置"""
    config = load_config()
    if name not in config:
        config[name] = {}
    for k, v in kwargs.items():
        if v is not None:
            config[name][k] = v
    save_config(config)


def remove_channel(name: str):
    """移除渠道配置"""
    config = load_config()
    config.pop(name, None)
    save_config(config)


# ===== 交互式配置向导 =====

def interactive_setup():
    """交互式渠道配置向导（类似 OpenClaw 的 gateway setup）"""
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit(
        "[bold]ClawHermes Gateway 配置向导[/bold]\n"
        "配置消息渠道，保存后启动 Gateway 自动连接",
        border_style="blue",
    ))

    config = load_config()

    # 飞书
    if Confirm.ask("📡 配置飞书渠道？", default=False):
        app_id = Prompt.ask("  飞书 App ID")
        app_secret = Prompt.ask("  飞书 App Secret")
        config["feishu"] = {"app_id": app_id, "app_secret": app_secret}
        console.print("  ✅ 飞书已配置")

    # 企业微信
    if Confirm.ask("📡 配置企业微信渠道？", default=False):
        corp_id = Prompt.ask("  企业微信 Corp ID")
        corp_secret = Prompt.ask("  企业微信 Corp Secret")
        agent_id = Prompt.ask("  应用 Agent ID", default="1000001")
        config["wechat"] = {
            "corp_id": corp_id,
            "corp_secret": corp_secret,
            "agent_id": int(agent_id),
        }
        console.print("  ✅ 企业微信已配置")

    # QQ
    if Confirm.ask("📡 配置 QQ 渠道？（需 go-cqhttp）", default=False):
        ws_url = Prompt.ask("  go-cqhttp WebSocket 地址", default="ws://127.0.0.1:6700")
        token = Prompt.ask("  访问令牌（可选）", default="")
        config["qq"] = {"ws_url": ws_url}
        if token:
            config["qq"]["token"] = token
        console.print("  ✅ QQ 已配置")

    # Telegram
    if Confirm.ask("📡 配置 Telegram 渠道？", default=False):
        token = Prompt.ask("  Bot Token", default="")
        if token:
            config["telegram"] = {"token": token}
            console.print("  ✅ Telegram 已配置")

    save_config(config)

    if config:
        console.print("\n💡 现在运行 [bold]clawhermes gateway[/bold] 启动，渠道将自动连接")
    else:
        console.print("\n💡 未配置任何渠道，随时可以重新运行 [bold]clawhermes gateway setup[/bold]")


def show_status():
    """显示当前渠道配置状态"""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    config = load_config()

    if not config:
        console.print("⚠️  未配置任何渠道，运行 [bold]clawhermes gateway setup[/bold] 配置")
        return

    table = Table(title="渠道配置状态")
    table.add_column("渠道", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("配置概要")

    for name, cfg in config.items():
        status = "✅ 已配置"
        summary = ""
        if name == "feishu":
            summary = f"app_id: {cfg.get('app_id', '?')[:15]}..."
        elif name == "wechat":
            summary = f"corp_id: {cfg.get('corp_id', '?')[:10]}..."
        elif name == "qq":
            summary = cfg.get("ws_url", "?")
        elif name == "telegram":
            summary = f"token: {cfg.get('token', '?')[:10]}..."
        else:
            summary = str(cfg)[:30]
        table.add_row(name, status, summary)

    console.print(table)
    console.print(f"\n共 {len(config)} 个渠道已配置")
