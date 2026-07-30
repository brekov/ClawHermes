"""ClawHermes - Gateway 服务安装与配置

对齐 Hermes gateway install 和 openclaw gateway wizard：
  - systemd (Linux) / launchd (macOS) 服务模板生成
  - Gateway auth token 自动生成
  - 服务生命周期管理 (enable/disable/status)
"""
from __future__ import annotations

import os
import platform
import secrets
from pathlib import Path

from clawhermes.config import get_data_dir


def get_gateway_token_path() -> Path:
    """Gateway auth token 存储路径"""
    return get_data_dir() / "gateway_token"


def generate_gateway_token() -> str:
    """生成 64 字符十六进制 Gateway auth token"""
    return secrets.token_hex(32)


def read_gateway_token() -> str | None:
    """读取已保存的 Gateway token，不存在则返回 None"""
    p = get_gateway_token_path()
    if p.exists():
        return p.read_text().strip()
    return None


def ensure_gateway_token() -> str:
    """确保 Gateway token 存在，不存在则生成并保存"""
    token = read_gateway_token()
    if not token:
        token = generate_gateway_token()
        p = get_gateway_token_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(token)
        p.chmod(0o600)
    return token


# ====== systemd (Linux) ======

SYSTEMD_UNIT_TEMPLATE = """[Unit]
Description=ClawHermes Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Environment=CH_DATA_DIR={data_dir}
Environment=CH_GATEWAY_HOST={host}
Environment=CH_GATEWAY_PORT={port}
{secret_env}
ExecStart={python} -m clawhermes.gateway.app --host {host} --port {port}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def install_systemd_service(
    host: str = "127.0.0.1",
    port: int = 18789,
    user: str | None = None,
) -> bool:
    """安装 systemd 服务"""
    import subprocess
    import sys

    if platform.system() != "Linux":
        print("  ⚠️  systemd 仅在 Linux 上可用")
        return False

    token = ensure_gateway_token()
    data_dir = str(get_data_dir())
    username = user or os.environ.get("USER", "clawhermes")
    python_path = sys.executable

    secret_env = ""
    if host not in ("127.0.0.1", "localhost"):
        secret_env = f"Environment=CH_GATEWAY_SECRET={token}\n"

    unit_content = SYSTEMD_UNIT_TEMPLATE.format(
        user=username,
        data_dir=data_dir,
        host=host,
        port=port,
        secret_env=secret_env,
        python=python_path,
    )

    unit_path = Path.home() / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(unit_content)

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)  # noqa: S607  受控系统命令
        subprocess.run(["systemctl", "--user", "enable", "--now", "clawhermes-gateway"], check=True, capture_output=True)  # noqa: S607  受控系统命令
        print("  ✅ systemd 服务已安装并启动: clawhermes-gateway")
        print(f"    Token: {token}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ systemd 安装失败: {e}")
        return False
    except FileNotFoundError:
        print("  ⚠️  systemctl 不可用")
        return False


# ====== launchd (macOS) ======

LAUNCHD_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.clawhermes.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>clawhermes.gateway.app</string>
        <string>--host</string>
        <string>{host}</string>
        <string>--port</string>
        <string>{port}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CH_DATA_DIR</key>
        <string>{data_dir}</string>
        <key>CH_GATEWAY_HOST</key>
        <string>{host}</string>
        <key>CH_GATEWAY_PORT</key>
        <string>{port}</string>
        {secret_env}
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/gateway.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/gateway-error.log</string>
</dict>
</plist>
"""


def install_launchd_service(
    host: str = "127.0.0.1",
    port: int = 18789,
) -> bool:
    """安装 macOS launchd 服务"""
    import subprocess
    import sys

    if platform.system() != "Darwin":
        print("  ⚠️  launchd 仅在 macOS 上可用")
        return False

    token = ensure_gateway_token()
    data_dir = str(get_data_dir())
    python_path = sys.executable
    log_dir = str(get_data_dir() / "logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    secret_env = ""
    if host not in ("127.0.0.1", "localhost"):
        secret_env = f"<key>CH_GATEWAY_SECRET</key>\n        <string>{token}</string>"

    plist_content = LAUNCHD_PLIST_TEMPLATE.format(
        python=python_path,
        host=host,
        port=port,
        data_dir=data_dir,
        secret_env=secret_env,
        log_dir=log_dir,
    )

    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)

    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)  # noqa
        subprocess.run(["launchctl", "load", str(plist_path)], check=True, capture_output=True)  # noqa: S603, S607  受控系统命令
        print("  ✅ launchd 服务已安装并启动: com.clawhermes.gateway")
        print(f"    Token: {token}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ launchd 安装失败: {e}")
        return False
    except FileNotFoundError:
        print("  ⚠️  launchctl 不可用")
        return False


# ====== 统一入口 ======


def install_gateway_service(
    host: str = "127.0.0.1",
    port: int = 18789,
    user: str | None = None,
) -> bool:
    """自动检测平台并安装对应的服务管理器"""
    system = platform.system()
    if system == "Linux":
        return install_systemd_service(host=host, port=port, user=user)
    elif system == "Darwin":
        return install_launchd_service(host=host, port=port)
    else:
        print(f"  ⚠️  不支持的平台: {system}")
        return False


def uninstall_gateway_service() -> bool:
    """卸载 Gateway 服务"""
    import subprocess

    system = platform.system()
    if system == "Linux":
        try:
            subprocess.run(["systemctl", "--user", "disable", "--now", "clawhermes-gateway"],  # noqa: S607  受控系统命令
                         check=True, capture_output=True)
            unit_path = Path.home() / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
            if unit_path.exists():
                unit_path.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)  # noqa: S607  受控系统命令
            print("  ✅ systemd 服务已卸载")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  ❌ 卸载失败: {e}")
            return False
    elif system == "Darwin":
        try:
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
            if plist_path.exists():
                subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)  # noqa: S603, S607  受控系统命令
                plist_path.unlink()
            print("  ✅ launchd 服务已卸载")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  ❌ 卸载失败: {e}")
            return False
    else:
        print(f"  ⚠️  不支持的平台: {system}")
        return False


def check_gateway_service_status() -> dict:
    """检查 Gateway 服务状态"""
    import subprocess

    result = {
        "installed": False,
        "running": False,
        "platform": platform.system(),
        "token_configured": read_gateway_token() is not None,
    }

    system = platform.system()
    if system == "Linux":
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", "clawhermes-gateway"],  # noqa: S607  受控系统命令
                capture_output=True, text=True,
            )
            result["running"] = r.stdout.strip() == "active"
            unit_path = Path.home() / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
            result["installed"] = unit_path.exists()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    elif system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        result["installed"] = plist_path.exists()
        if result["installed"]:
            try:
                r = subprocess.run(
                    ["launchctl", "list", "com.clawhermes.gateway"],  # noqa: S607  受控系统命令
                    capture_output=True, text=True,
                )
                result["running"] = r.returncode == 0 and "PID" in r.stdout
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    return result
