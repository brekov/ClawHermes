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

    # 微信（通过 Bridge 调用官方 Node SDK）
    if Confirm.ask("📱 配置个人微信渠道？（扫码登录）", default=True):
        _check_npm(console, "@tencent-weixin/openclaw-weixin")
        # 扫码登录（纯 Python，无需 SDK）
        import httpx, qrcode, time
        try:
            resp = httpx.post(
                "https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3",
                json={"local_token_list": []}, timeout=15,
            )
            data = resp.json()
            qr = data.get("qrcode")
            if qr:
                qrcode.QRCode(border=1, box_size=2).add_data(qr).make(fit=True).print_ascii()
                console.print("\n[dim]等待扫码... (60秒超时)[/dim]")
                start = time.time()
                with httpx.Client(timeout=65) as client:
                    while time.time() - start < 60:
                        r = client.get(f"https://ilinkai.weixin.qq.com/ilink/bot/get_qrcode_status?qrcode={qr}")
                        s = r.json().get("status", "")
                        if s == "wait": console.print(".", end="")
                        elif s == "scaned": console.print("\n[green]已扫码，请确认[/green]")
                        elif s == "confirmed":
                            token = r.json().get("bot_token", "")
                            if token:
                                save_channel("wechat", {"bot_token": token})
                                console.print(f"\n[green]✅ 微信已配置[/green]")
                            break
                        elif s == "expired": console.print("\n[red]二维码已过期[/red]"); break
                        time.sleep(1)
            else:
                console.print("[red]获取二维码失败[/red]")
        except Exception as e:
            console.print(f"[red]扫码失败: {e}[/red]")

    # 企业微信
    if Confirm.ask("📡 配置企业微信渠道？", default=False):
        from rich.prompt import Prompt
        corp_id = Prompt.ask("  企业微信 Corp ID")
        corp_secret = Prompt.ask("  企业微信 Corp Secret")
        agent_id = Prompt.ask("  应用 Agent ID", default="1000001")
        if corp_id and corp_secret:
            save_channel("wechat_corp", {"corp_id": corp_id, "corp_secret": corp_secret, "agent_id": int(agent_id)})
            console.print("  ✅ 企业微信已配置")

    # 飞书（需要 pip install lark-oapi）
    if Confirm.ask("📡 配置飞书渠道？", default=False):
        try:
            import lark_oapi
        except ImportError:
            console.print("[yellow]⚠️  需要安装飞书 SDK[/yellow]")
            console.print("   运行: pip install lark-oapi")
            if not Confirm.ask("  现在安装？", default=True):
                return
            import subprocess
            subprocess.run(["pip3", "install", "lark-oapi"], cwd=os.getcwd())
        from rich.prompt import Prompt
        console.print("请提供飞书应用凭证（在飞书开发者后台获取）")
        app_id = Prompt.ask("  飞书 App ID")
        app_secret = Prompt.ask("  飞书 App Secret")
        if app_id and app_secret:
            save_channel("feishu", {"app_id": app_id, "app_secret": app_secret})
            console.print("  ✅ 飞书已配置")

    # QQ
    if Confirm.ask("📡 配置 QQ 渠道？（需 go-cqhttp）", default=False):
        from rich.prompt import Prompt
        ws_url = Prompt.ask("  go-cqhttp 地址", default="ws://127.0.0.1:6700")
        token = Prompt.ask("  访问令牌（可选）", default="")
        cfg = {"ws_url": ws_url}
        if token:
            cfg["token"] = token
        save_channel("qq", cfg)
        console.print("  ✅ QQ 已配置")

    # Telegram
    if Confirm.ask("📡 配置 Telegram 渠道？", default=False):
        from rich.prompt import Prompt
        token = Prompt.ask("  Bot Token")
        if token:
            save_channel("telegram", {"token": token})
            console.print("  ✅ Telegram 已配置")

    channels = load_channels()
    if channels:
        console.print(f"\n✅ 共 {len(channels)} 个渠道已配置")
        console.print("💡 运行 [bold]clawhermes gateway start[/bold] 启动")


def _check_npm(console, pkg: str) -> bool:
    """检查 npm 包是否已安装，未安装则提示"""
    import subprocess
    try:
        subprocess.run(["npx", "--version"], capture_output=True, timeout=5)
    except Exception:
        console.print("[yellow]⚠️  需要 Node.js + npm[/yellow]")
        console.print(f"   先安装 Node.js，然后运行:")
        console.print(f"   npm install {pkg}")
        return False

    # 检查包是否已安装
    try:
        subprocess.run(["node", "-e", f"require('{pkg}')"], capture_output=True, timeout=5)
        return True
    except Exception:
        console.print(f"[yellow]⚠️  需要安装 {pkg}[/yellow]")
        console.print(f"   运行: npm install {pkg}")
        if Confirm.ask("  现在安装？", default=True):
            result = subprocess.run(["npm", "install", pkg], cwd=os.getcwd())
            if result.returncode == 0:
                console.print(f"  ✅ {pkg} 已安装")
                return True
        return False


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
