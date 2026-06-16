"""
ClawHermes - Node SDK 兼容层（Python 端）
通过 subprocess 调用 bridge.mjs，加载官方 Node SDK 发消息
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BRIDGE_SCRIPT = Path(__file__).parent.parent.parent.parent / "scripts" / "bridge.mjs"


def _run_node(args: list[str]) -> dict[str, Any]:
    """运行 bridge.mjs 并解析结果"""
    try:
        result = subprocess.run(
            ["node", str(BRIDGE_SCRIPT)] + args,
            capture_output=True, text=True, timeout=15,
            env={**__import__('os').environ},
        )
        return json.loads(result.stdout.strip())
    except FileNotFoundError:
        return {"error": "Node.js 未安装"}
    except subprocess.TimeoutExpired:
        return {"error": "调用超时"}
    except json.JSONDecodeError:
        return {"error": result.stdout.strip()[:200] if result.stdout else "无输出"}
    except Exception as e:
        return {"error": str(e)}


def check_sdk(channel: str) -> bool:
    """检查 Node SDK 是否已安装"""
    result = _run_node(["check", channel])
    return result.get("installed", False)


def send(channel: str, to: str, text: str) -> dict[str, Any]:
    """通过 Node SDK 发送消息"""
    return _run_node(["send", channel, to, text])
