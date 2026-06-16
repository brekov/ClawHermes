"""
ClawHermes - 微信扫码配置入口
纯 Python 实现，不依赖 OpenClaw
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from clawhermes.gateway.ilink import wechat_qr_login
from clawhermes.gateway.setup import save_channel

console = Console()


def wechat_setup() -> dict | None:
    """微信配置入口：扫码登录，保存到 channels/wechat.yaml"""
    console.print(Panel.fit(
        "[bold]📱 个人微信扫码登录[/bold]\n"
        "无需 OpenClaw，无需 Node.js\n"
        "直接通过微信 Bot 协议扫码",
        border_style="green",
    ))

    result = wechat_qr_login()
    if result and result.get("bot_token"):
        save_channel("wechat", result)
        console.print("  ✅ 微信已配置")
        return result
    else:
        console.print("  ⚠️  扫码未完成")
        return None
