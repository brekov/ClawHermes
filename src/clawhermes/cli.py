"""
ClawHermes - CLI 入口
"""
from __future__ import annotations

import click


@click.group()
def main():
    """ClawHermes - 融合 Hermes 与 OpenClaw 的 AI Agent 框架"""
    pass


@main.command()
@click.option("--env-file", default=None, help="自定义 .env 路径")
def setup(env_file: str | None):
    """一键初始化配置和数据目录"""
    from clawhermes.config import load_config
    from pathlib import Path

    cfg = load_config(env_file)
    data_dir = Path(cfg.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"✅ 数据目录已创建: {data_dir}")


@main.command()
@click.option("--port", default=18789, help="Gateway 端口")
@click.option("--host", default="127.0.0.1", help="绑定地址")
def gateway(port: int, host: str):
    """启动消息网关"""
    click.echo(f"🚀 Gateway 启动: {host}:{port}")
    click.echo("(功能开发中 - M6 里程碑)")


@main.command()
@click.argument("message", required=False)
def chat(message: str | None):
    """CLI 对话模式"""
    click.echo("💬 CLI 对话模式")
    click.echo("(功能开发中 - M3 里程碑)")


@main.command()
def doctor():
    """诊断系统配置"""
    click.echo("🔍 诊断中...")
    click.echo("✅ Python OK")
    click.echo("(功能开发中)")


if __name__ == "__main__":
    main()
