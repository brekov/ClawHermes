"""
ClawHermes - 扫码配置渠道（微信/飞书）
"""
from __future__ import annotations

import json
import time
from io import BytesIO
from base64 import b64decode
from typing import Any

import httpx
import qrcode
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

# ===== 微信扫码登录（复用 OpenClaw 的 ilink 协议）=====

WEIXIN_API_BASE = "https://ilinkai.weixin.qq.com"
POLL_TIMEOUT = 35  # 秒


def _render_qrcode(data: str):
    """在终端显示二维码"""
    qr = qrcode.QRCode(border=1, box_size=2)
    qr.add_data(data)
    qr.make(fit=True)
    console.print(qr.make_image(fill_color="black", back_color="white"))


def _render_qrcode_from_base64(base64_data: str):
    """从 base64 图片数据渲染二维码"""
    try:
        img_data = b64decode(base64_data)
        from PIL import Image
        img = Image.open(BytesIO(img_data))
        # 转成 ASCII
        qr = qrcode.QRCode(border=1, box_size=2)
        qr.add_data(img.tobytes())
        # 简单方案：直接用 PIL 图片显示尺寸信息
        console.print(f"[dim]二维码图片: {img.size[0]}x{img.size[1]}[/dim]")
    except Exception:
        pass
    # 用文本方式也渲染一个
    _render_qrcode(base64_data[:100])  # fallback


def wechat_qr_login() -> dict[str, Any] | None:
    """微信扫码登录——终端显示二维码，手机扫码自动授权"""
    console.print(Panel.fit(
        "[bold]📱 微信扫码登录[/bold]\n"
        "请使用微信扫描终端中的二维码",
        border_style="green",
    ))

    try:
        # Step 1: 获取二维码
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{WEIXIN_API_BASE}/ilink/bot/get_bot_qrcode?bot_type=3",
                json={"local_token_list": []},
            )
            resp.raise_for_status()
            data = resp.json()

        qrcode_token = data.get("qrcode", "")
        qrcode_img = data.get("qrcode_img_content", "")

        if not qrcode_token:
            console.print("[red]❌ 获取二维码失败[/red]")
            return None

        # 显示二维码
        if qrcode_img:
            _render_qrcode_from_base64(qrcode_img)
        else:
            _render_qrcode(qrcode_token)

        console.print("\n[dim]等待扫码... (35秒超时)[/dim]")

        # Step 2: 轮询扫码状态
        start = time.time()
        with httpx.Client(timeout=POLL_TIMEOUT + 5) as client:
            while time.time() - start < POLL_TIMEOUT:
                poll_resp = client.get(
                    f"{WEIXIN_API_BASE}/ilink/bot/get_qrcode_status",
                    params={"qrcode": qrcode_token},
                )
                poll_resp.raise_for_status()
                status_data = poll_resp.json()
                status = status_data.get("status", "")

                if status == "wait":
                    console.print(".", end="")
                elif status == "scaned":
                    console.print("\n[green]✅ 已扫码，请在手机上确认[/green]")
                elif status == "confirmed":
                    nick = status_data.get("nick_name", "")
                    bot_token = status_data.get("bot_token", "")
                    console.print(f"\n[green]✅ 扫码成功！[/green]")
                    if nick:
                        console.print(f"   微信昵称: {nick}")
                    if bot_token:
                        console.print(f"   Bot Token: {bot_token[:20]}...")
                        return {
                            "nick_name": nick,
                            "bot_token": bot_token,
                            "qrcode": qrcode_token,
                        }
                elif status == "expired":
                    console.print("\n[red]❌ 二维码已过期，请重试[/red]")
                    return None
                elif status == "need_verifycode":
                    console.print("\n[yellow]⚠️  需要验证码，请查看手机[/yellow]")
                    return None

                time.sleep(1)

        console.print("\n[yellow]⏰ 扫码超时[/yellow]")
        return None

    except httpx.RequestError as e:
        console.print(f"\n[red]❌ 网络错误: {e}[/red]")
        return None
    except Exception as e:
        console.print(f"\n[red]❌ 错误: {e}[/red]")
        return None


# ===== 飞书扫码/OAuth 授权 =====

def feishu_oauth_url() -> str:
    """生成飞书授权 URL（用户访问后在浏览器授权）"""
    app_id = "cli_a961a1f06039dcb1"  # 已有飞书应用
    redirect_uri = "https://127.0.0.1:18789/channels/feishu/callback"
    return (
        f"https://open.feishu.cn/open-apis/authen/v1/index"
        f"?app_id={app_id}&redirect_uri={redirect_uri}"
        f"&scope=im:message"
    )


def feishu_qr_login() -> dict[str, Any] | None:
    """飞书扫码授权"""
    console.print(Panel.fit(
        "[bold]📱 飞书扫码授权[/bold]\n"
        "请使用飞书扫描二维码完成授权",
        border_style="blue",
    ))

    # 生成授权二维码（包含授权 URL）
    auth_url = feishu_oauth_url()
    _render_qrcode(auth_url)

    console.print(f"\n[dim]或访问: {auth_url}[/dim]")
    console.print("\n[yellow]⚠️  由于需要公网回调地址，飞书扫码暂只支持生成授权链接[/yellow]")
    console.print("[dim]请手动在飞书开发者后台获取 App ID 和 App Secret[/dim]")

    # 回退到手动输入
    from rich.prompt import Prompt
    app_id = Prompt.ask("  飞书 App ID")
    app_secret = Prompt.ask("  飞书 App Secret")
    if app_id and app_secret:
        return {"app_id": app_id, "app_secret": app_secret}
    return None


# ===== Telegram（无法扫码，保持交互式）=====

def telegram_setup() -> dict[str, Any] | None:
    """Telegram 配置（无扫码能力，走交互）"""
    console.print(Panel.fit(
        "[bold]📱 Telegram 配置[/bold]\n"
        "需要 Bot Token，通过 @BotFather 创建 Bot 获取",
        border_style="cyan",
    ))
    from rich.prompt import Prompt
    token = Prompt.ask("  Bot Token")
    if token:
        return {"token": token}
    return None


# ===== QQ（无法扫码，保持交互式）=====

def qq_setup() -> dict[str, Any] | None:
    """QQ 配置"""
    console.print(Panel.fit(
        "[bold]📱 QQ 配置[/bold]\n"
        "需要 go-cqhttp WebSocket 地址",
        border_style="magenta",
    ))
    from rich.prompt import Prompt
    ws_url = Prompt.ask("  go-cqhttp 地址", default="ws://127.0.0.1:6700")
    token = Prompt.ask("  访问令牌（可选）", default="")
    result = {"ws_url": ws_url}
    if token:
        result["token"] = token
    return result
