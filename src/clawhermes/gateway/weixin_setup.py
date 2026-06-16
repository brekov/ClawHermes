"""
ClawHermes - 微信扫码配置
支持通过 openclaw-weixin-cli 扫码，也支持独立配置
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

# OpenClaw 账号目录（可配置，默认 ~/.openclaw/openclaw-weixin/accounts/）
OPENCLAW_ACCOUNTS_DIR = Path(
    os.environ.get(
        "CH_OPENCLAW_ACCOUNTS_DIR",
        str(Path.home() / ".openclaw" / "openclaw-weixin" / "accounts"),
    )
)


def get_existing_weixin_account() -> dict[str, Any] | None:
    """读取已有微信账号凭证（兼容 OpenClaw 的账号文件格式）"""
    if not OPENCLAW_ACCOUNTS_DIR.exists():
        return None

    try:
        for f in sorted(OPENCLAW_ACCOUNTS_DIR.glob("*.json")):
            name = f.stem
            if name.endswith(".sync") or name.endswith(".context-tokens"):
                continue
            try:
                data = json.loads(f.read_text())
                if data.get("token"):
                    return {
                        "bot_token": data["token"],
                        "base_url": data.get("baseUrl", "https://ilinkai.weixin.qq.com"),
                        "user_id": data.get("userId", ""),
                        "account_id": name,
                    }
            except Exception:
                continue
    except Exception:
        pass
    return None


def run_weixin_installer() -> bool:
    """运行 openclaw-weixin-cli 安装器（需要 Node.js + npm 环境）"""
    console.print(Panel.fit(
        "[bold]📱 微信扫码登录[/bold]\n"
        "需要 Node.js 和 npm 环境。\n"
        "将调用 npx @tencent-weixin/openclaw-weixin-cli 安装器，"
        "终端显示二维码后请用个人微信扫码。",
        border_style="green",
    ))

    # 检测 npm
    try:
        subprocess.run(["npx", "--version"], capture_output=True, timeout=5)
    except Exception:
        console.print("[yellow]⚠️  未检测到 npx，请先安装 Node.js[/yellow]")
        console.print("   也可以手动在微信开发者后台获取凭证后配置")
        return False

    try:
        result = subprocess.run(
            ["npx", "-y", "@tencent-weixin/openclaw-weixin-cli@latest", "install"],
            capture_output=False,
            timeout=120,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        console.print("[red]❌ 安装超时（120秒）[/red]")
        return False
    except Exception as e:
        console.print(f"[red]❌ 安装失败: {e}[/red]")
        return False


def wechat_qr_setup() -> dict[str, Any] | None:
    """微信扫码配置入口"""
    # 先检查是否已有凭证
    existing = get_existing_weixin_account()
    if existing:
        console.print(f"[green]✅ 检测到已有微信账号: {existing.get('user_id', '?')[:20]}...[/green]")
        if not Confirm.ask("  是否重新扫码？（否则使用已有账号）", default=False):
            return existing

    # 运行安装器
    if run_weixin_installer():
        account = get_existing_weixin_account()
        if account:
            console.print(f"[green]✅ 微信扫码成功！[/green]")
            console.print(f"   用户: {account.get('user_id', '?')}")
            return account
        else:
            console.print("[yellow]⚠️  安装完成但未读取到凭证[/yellow]")
            from rich.prompt import Prompt
            token = Prompt.ask("  请输入 Bot Token")
            if token:
                return {"bot_token": token}
    return None
