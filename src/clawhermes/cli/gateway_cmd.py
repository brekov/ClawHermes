"""Gateway 子命令组 — start / setup / uninstall / status。"""
from __future__ import annotations

import os

import click

from clawhermes.cli import _load_dotenv, console


@click.group()
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
