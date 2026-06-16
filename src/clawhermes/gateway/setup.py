"""
ClawHermes - 渠道/Provider 配置管理器
每个渠道/Provider 独立文件，存于 ~/.clawhermes/channels/ 和 providers/
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def get_data_dir() -> Path:
    return Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))


def _read_yaml(path: Path) -> dict:
    if path.exists():
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}


def _write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# ===== Channels =====

def channel_dir() -> Path:
    d = get_data_dir() / "channels"
    d.mkdir(parents=True, exist_ok=True)
    return d


def channel_path(name: str) -> Path:
    return channel_dir() / f"{name}.yaml"


def load_channels() -> dict[str, dict]:
    """加载所有渠道配置"""
    channels = {}
    for f in sorted(channel_dir().glob("*.yaml")):
        name = f.stem
        data = _read_yaml(f)
        if data:
            channels[name] = data
    return channels


def save_channel(name: str, cfg: dict):
    _write_yaml(channel_path(name), cfg)


def delete_channel(name: str):
    p = channel_path(name)
    if p.exists():
        p.unlink()


# ===== Providers =====

def provider_dir() -> Path:
    d = get_data_dir() / "providers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def provider_path(name: str) -> Path:
    return provider_dir() / f"{name}.yaml"


def load_providers() -> dict[str, dict]:
    """加载所有 LLM Provider 配置"""
    providers = {}
    for f in sorted(provider_dir().glob("*.yaml")):
        name = f.stem
        data = _read_yaml(f)
        if data:
            providers[name] = data
    return providers


def save_provider(name: str, cfg: dict):
    _write_yaml(provider_path(name), cfg)


def delete_provider(name: str):
    p = provider_path(name)
    if p.exists():
        p.unlink()


# ===== 兼容旧版 channels.json =====

def migrate_legacy():
    """如果存在 channels.json，迁移到 channels/*.yaml"""
    legacy = get_data_dir() / "channels.json"
    if legacy.exists():
        import json
        try:
            data = json.loads(legacy.read_text())
            for name, cfg in data.items():
                save_channel(name, cfg)
                print(f"  ✅ 已迁移 channels/{name}.yaml")
            legacy.unlink()
            print("  channels.json 已删除")
        except Exception:
            pass


# ===== 交互式配置（保留，但写入 channels/*.yaml）=====

def interactive_setup():
    """交互式渠道配置向导"""
    from rich.console import Console
    from rich.prompt import Confirm
    from rich.panel import Panel

    console = Console()
    migrate_legacy()

    console.print(Panel.fit(
        "[bold]ClawHermes Gateway 配置向导[/bold]",
        border_style="blue",
    ))

    # 微信（个人号扫码）
    if Confirm.ask("📱 配置个人微信渠道？（扫码登录）", default=True):
        from clawhermes.gateway.weixin_setup import wechat_qr_setup
        result = wechat_qr_setup()
        if result:
            save_channel("wechat", result)
            console.print("  ✅ 微信已配置")

    # 企业微信
    if Confirm.ask("📡 配置企业微信渠道？", default=False):
        from clawhermes.gateway.qr_setup import wechat_qr_login
        result = wechat_qr_login()
        if result:
            save_channel("wechat_corp", result)
            console.print("  ✅ 企业微信已配置")

    # 飞书
    if Confirm.ask("📡 配置飞书渠道？", default=False):
        from clawhermes.gateway.qr_setup import feishu_qr_login
        result = feishu_qr_login()
        if result:
            save_channel("feishu", result)
            console.print("  ✅ 飞书已配置")

    # QQ
    if Confirm.ask("📡 配置 QQ 渠道？（需 go-cqhttp）", default=False):
        from clawhermes.gateway.qr_setup import qq_setup
        result = qq_setup()
        if result:
            save_channel("qq", result)
            console.print("  ✅ QQ 已配置")

    # Telegram
    if Confirm.ask("📡 配置 Telegram 渠道？", default=False):
        from clawhermes.gateway.qr_setup import telegram_setup
        result = telegram_setup()
        if result:
            save_channel("telegram", result)
            console.print("  ✅ Telegram 已配置")

    channels = load_channels()
    if channels:
        console.print(f"\n✅ 共 {len(channels)} 个渠道已配置")
        console.print("💡 运行 [bold]clawhermes gateway start[/bold] 启动")


def show_status():
    """显示渠道配置状态"""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    channels = load_channels()

    if not channels:
        console.print("⚠️  未配置任何渠道，运行 [bold]clawhermes gateway setup[/bold] 配置")
        return

    table = Table(title="渠道配置")
    table.add_column("渠道", style="cyan")
    table.add_column("文件")
    for name in sorted(channels):
        table.add_row(name, str(channel_path(name)))
    console.print(table)
    console.print(f"\n共 {len(channels)} 个渠道")
