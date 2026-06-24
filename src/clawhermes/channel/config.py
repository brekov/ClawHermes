"""
ClawHermes — 渠道配置加载器

单一配置来源：YAML + ${VAR} 环境变量引用
- 敏感值：.env → os.environ → YAML ${FEISHU_APP_ID} 插值
- 操作配置：channels/<name>.yaml（内置默认值为后备）
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ${VAR_NAME} 或 ${VAR_NAME:-default} 模式
_ENV_REF_RE = re.compile(r'\$\{(\w+)(?::-(\s*[^}]*))?\}')


def _resolve_env_ref(value: Any) -> Any:
    """递归解析值中的 ${VAR} 引用"""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            var_name = m.group(1)
            default = m.group(2)
            if default is not None:
                default = default.strip()
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return str(env_val)
            if default is not None:
                return str(default)
            return str(m.group(0))
        return _ENV_REF_RE.sub(_replace, value)

    if isinstance(value, dict):
        return {k: _resolve_env_ref(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_resolve_env_ref(item) for item in value]

    return value


# ── 内置默认值 ────────────────────────────────────────────────────

_CHANNEL_DEFAULTS: dict[str, dict[str, Any]] = {
    "feishu": {
        "domain": "feishu",
        "connection_mode": "websocket",
        "group_policy": "allowlist",
        "allow_bots": "none",
        "require_mention": True,
        "webhook_host": "0.0.0.0",
        "webhook_port": 8080,
        "webhook_path": "/feishu/webhook",
        "ws_reconnect_nonce": 30,
        "ws_reconnect_interval": 120,
        "log_level": 20,
        "max_retries": 3,
        "retry_delay": 1.0,
        "dedup_cache_size": 1024,
        "reactions_enabled": True,
    },
    "wechat": {
        "sub_type": "personal",
    },
    "qq": {
        "sandbox": True,
        "auto_reconnect": True,
        "max_retries": 3,
        "retry_delay": 1.0,
    },
}


# ── 公共 API ──────────────────────────────────────────────────────

def load_channel_config(channel_name: str) -> dict[str, Any]:
    """加载渠道配置，${VAR} 自动从 os.environ 注入"""
    data_dir = Path(os.environ.get("CH_DATA_DIR", Path.home() / ".clawhermes"))
    runtime_path = data_dir / "channels" / f"{channel_name}.yaml"
    example_path = (
        Path(__file__).parent.parent.parent.parent
        / "config" / "channels" / f"{channel_name}.yaml.example"
    )

    config: dict[str, Any] = dict(_CHANNEL_DEFAULTS.get(channel_name, {}))

    for path in (runtime_path, example_path):
        if path.exists():
            try:
                with open(path) as f:
                    loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    config.update(loaded)
                logger.debug("Loaded channel config: %s", path)
            except Exception as e:
                logger.warning("Failed to load channel config %s: %s", path, e)

    resolved = _resolve_env_ref(config)
    assert isinstance(resolved, dict)
    return resolved


def build_adapter_config(channel_name: str) -> dict[str, Any]:
    """构建适配器所需的配置 dict（移除元数据字段）"""
    yaml_config = load_channel_config(channel_name)
    return {
        k: v for k, v in yaml_config.items()
        if k not in ("channel_type", "enabled", "routing", "comment")
    }
