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
    """交互式渠道配置向导（微信扫码，飞书扫码，其他手动）"""
    from rich.console import Console
    from rich.prompt import Confirm
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit(
        "[bold]ClawHermes Gateway 配置向导[/bold]\n"
        "企业微信支持扫码登录，无需手动填写凭证",
        border_style="blue",
    ))

    config = load_config()

    # 微信（通过 openclaw-weixin-cli 扫码登录个人微信）
    if Confirm.ask("📱 配置个人微信渠道？（扫码登录）", default=True):
        from clawhermes.gateway.weixin_setup import wechat_qr_setup
        result = wechat_qr_setup()
        if result and result.get("bot_token"):
            config["wechat"] = {"bot_token": result["bot_token"]}
            if result.get("base_url"):
                config["wechat"]["base_url"] = result["base_url"]
            console.print("  ✅ 微信已配置")
        else:
            console.print("  ⚠️  配置未完成")

    # 企业微信（扫码登录，不同于个人微信）
    if Confirm.ask("📡 配置企业微信渠道？", default=False):
        from clawhermes.gateway.qr_setup import wechat_qr_login
        result = wechat_qr_login()
        if result and result.get("bot_token"):
            config["wechat_corp"] = result
            console.print("  ✅ 企业微信已配置")
        else:
            console.print("  ⚠️  配置未完成")

    # 飞书
    if Confirm.ask("📡 配置飞书渠道？", default=False):
        from clawhermes.gateway.qr_setup import feishu_qr_login
        result = feishu_qr_login()
        if result:
            config["feishu"] = result
            console.print("  ✅ 飞书已配置")

    # QQ
    if Confirm.ask("📡 配置 QQ 渠道？（需 go-cqhttp）", default=False):
        from clawhermes.gateway.qr_setup import qq_setup
        result = qq_setup()
        if result:
            config["qq"] = result
            console.print("  ✅ QQ 已配置")

    # Telegram
    if Confirm.ask("📡 配置 Telegram 渠道？", default=False):
        from clawhermes.gateway.qr_setup import telegram_setup
        result = telegram_setup()
        if result:
            config["telegram"] = result
            console.print("  ✅ Telegram 已配置")

    save_config(config)

    if config:
        console.print("\n💡 现在运行 [bold]clawhermes gateway start[/bold] 启动")
    else:
        console.print("\n💡 未配置任何渠道，随时重新运行 [bold]clawhermes gateway setup[/bold]")


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
