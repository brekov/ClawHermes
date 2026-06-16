"""
ClawHermes - Node SDK 兼容层（Python 端）
通过 stdin/stdout 与 bridge.mjs 通信，支持收发消息
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

BRIDGE_SCRIPT = Path(__file__).parent / "bridge.mjs"


class Bridge:
    """Node SDK 兼容层 — 管理长连接进程"""

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._msg_id = 0
        self._callbacks: dict[str, Callable] = {}
        self._running = False

    def start(self) -> bool:
        """启动 bridge 长连接进程"""
        if self._process:
            return True
        try:
            self._process = subprocess.Popen(
                ["node", str(BRIDGE_SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ},
            )
            # 启动 stdout 读取线程
            self._running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            return True
        except FileNotFoundError:
            logger.error("Node.js 未安装")
            return False
        except Exception as e:
            logger.error("Bridge 启动失败: %s", e)
            return False

    def _read_loop(self):
        """读取 bridge 的 stdout，处理消息"""
        while self._running and self._process and self._process.stdout:
            line = self._process.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line.strip())
                msg_type = data.get("type", "")

                if msg_type == "ready":
                    logger.info("Bridge 就绪: weixin=%s feishu=%s",
                               data.get("weixin"), data.get("feishu"))

                elif msg_type == "message":
                    # 收到来自微信/飞书的消息
                    cb = self._callbacks.get("on_message")
                    if cb:
                        cb(data)

                elif msg_type == "result":
                    cb = self._callbacks.get(data.get("id", ""))
                    if cb:
                        cb(data)

            except json.JSONDecodeError:
                pass

    def send(self, channel: str, to: str, text: str) -> dict[str, Any]:
        """发送消息（同步，等待结果）"""
        if not self._process or not self._process.stdin:
            return {"error": "Bridge 未运行"}

        self._msg_id += 1
        msg_id = str(self._msg_id)
        result_holder = []

        def on_result(data):
            result_holder.append(data)

        self._callbacks[msg_id] = on_result

        cmd = json.dumps({"type": "send", "id": msg_id, "channel": channel, "to": to, "text": text})
        self._process.stdin.write(cmd + "\n")
        self._process.stdin.flush()

        # 等待结果（最多 15 秒）
        import time
        for _ in range(150):
            if result_holder:
                self._callbacks.pop(msg_id, None)
                return result_holder[0]
            time.sleep(0.1)

        self._callbacks.pop(msg_id, None)
        return {"error": "发送超时"}

    def on_message(self, callback: Callable):
        """注册消息接收回调"""
        self._callbacks["on_message"] = callback

    def stop(self):
        self._running = False
        if self._process:
            self._process.terminate()
            self._process = None

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None


# 全局单例
_bridge: Bridge | None = None


def get_bridge() -> Bridge:
    global _bridge
    if _bridge is None:
        _bridge = Bridge()
    return _bridge
