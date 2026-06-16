"""
ClawHermes - Node SDK 兼容层（Python 端）
启动 Node.js bridge 子进程，通过 HTTP 调用官方 SDK
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BRIDGE_PORT = int(os.environ.get("CH_BRIDGE_PORT", "18788"))
BRIDGE_SCRIPT = Path(__file__).parent.parent.parent.parent / "scripts" / "bridge.mjs"


class BridgeClient:
    """Node SDK 兼容层客户端"""

    def __init__(self, port: int = BRIDGE_PORT):
        self.port = port
        self._base = f"http://127.0.0.1:{port}"
        self._process: subprocess.Popen | None = None

    def start(self) -> bool:
        """启动 Node.js bridge 进程"""
        if self._process:
            return True
        if not BRIDGE_SCRIPT.exists():
            logger.warning("Bridge 脚本不存在: %s", BRIDGE_SCRIPT)
            return False

        try:
            self._process = subprocess.Popen(
                ["node", str(BRIDGE_SCRIPT)],
                env={**os.environ, "CH_BRIDGE_PORT": str(self.port)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # 等待启动
            for _ in range(10):
                try:
                    r = httpx.get(f"{self._base}/health", timeout=2)
                    if r.is_success:
                        logger.info("Bridge 已启动: port=%d", self.port)
                        return True
                except Exception:
                    time.sleep(0.5)
            logger.warning("Bridge 启动超时")
            return False
        except Exception as e:
            logger.warning("Bridge 启动失败: %s", e)
            return False

    def stop(self):
        """停止 bridge 进程"""
        if self._process:
            self._process.terminate()
            self._process = None

    def send(self, channel: str, to: str, text: str) -> dict[str, Any]:
        """通过 Bridge 发送消息"""
        try:
            resp = httpx.post(
                f"{self._base}/send",
                json={"channel": channel, "to": to, "text": text},
                timeout=15,
            )
            return resp.json()
        except httpx.ConnectError:
            return {"error": f"Bridge 未运行，请先调用 POST /channels/bridge/start"}
        except Exception as e:
            return {"error": str(e)}

    def health(self) -> dict:
        try:
            r = httpx.get(f"{self._base}/health", timeout=3)
            return r.json()
        except Exception:
            return {"status": "down"}


# 全局单例
_bridge: BridgeClient | None = None


def get_bridge() -> BridgeClient:
    global _bridge
    if _bridge is None:
        _bridge = BridgeClient()
    return _bridge


def ensure_bridge() -> bool:
    """确保 Bridge 已启动"""
    bridge = get_bridge()
    health = bridge.health()
    if health.get("status") == "ok":
        return True
    return bridge.start()
