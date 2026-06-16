"""
ClawHermes - 微信扫码登录（纯 Python，无外部依赖）
基于 WeCom Bot ilink 协议，完全独立于 OpenClaw
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import qrcode
from rich.console import Console
from rich.panel import Panel

console = Console()

ILINK_BASE = "https://ilinkai.weixin.qq.com"
POLL_TIMEOUT = 60  # 秒


def _render_qrcode(data: str):
    """在终端显示二维码"""
    qr = qrcode.QRCode(border=1, box_size=2)
    qr.add_data(data)
    qr.make(fit=True)
    console.print(qr.make_image(fill_color="black", back_color="white"))


def wechat_qr_login() -> dict[str, Any] | None:
    """个人微信扫码登录——纯 Python，不依赖 OpenClaw"""
    console.print(Panel.fit(
        "[bold]📱 微信扫码登录[/bold]\n"
        "请使用个人微信扫描终端中的二维码",
        border_style="green",
    ))

    try:
        # Step 1: 获取二维码
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{ILINK_BASE}/ilink/bot/get_bot_qrcode?bot_type=3",
                json={"local_token_list": []},
            )
            data = resp.json()

        qrcode_token = data.get("qrcode", "")
        if not qrcode_token:
            console.print("[red]❌ 获取二维码失败[/red]")
            return None

        # 显示二维码
        _render_qrcode(qrcode_token)
        console.print("\n[dim]等待扫码... (60秒超时)[/dim]")

        # Step 2: 轮询扫码状态
        start = time.time()
        with httpx.Client(timeout=65) as client:
            while time.time() - start < POLL_TIMEOUT:
                resp = client.get(
                    f"{ILINK_BASE}/ilink/bot/get_qrcode_status",
                    params={"qrcode": qrcode_token},
                )
                status_data = resp.json()
                status = status_data.get("status", "")

                if status == "wait":
                    console.print(".", end="")
                elif status == "scaned":
                    console.print("\n[green]✅ 已扫码，请在手机上确认[/green]")
                elif status == "confirmed":
                    nick = status_data.get("nick_name", "")
                    bot_token = status_data.get("bot_token", "")
                    bot_id = status_data.get("ilink_bot_id", "")
                    console.print(f"\n[green]✅ 扫码成功！[/green]")
                    if nick:
                        console.print(f"   微信昵称: {nick}")
                    result = {"bot_token": bot_token, "bot_id": bot_id}
                    if nick:
                        result["nick_name"] = nick
                    return result
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


def wechat_send_text(bot_token: str, to_user: str, text: str) -> dict:
    """通过 ilink 协议发送文本消息（纯 Python）"""
    with httpx.Client(timeout=10) as client:
        resp = client.post(
            f"{ILINK_BASE}/ilink/bot/send_message",
            json={
                "bot_token": bot_token,
                "to_userid": to_user,
                "msg_type": "text",
                "content": text,
            },
        )
        return resp.json()
