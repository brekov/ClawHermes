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
from typing import Any

from clawhermes.config import get_data_dir, load_yaml

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
        "group_policy": "open",
        "allow_bots": "none",
        "require_mention": True,
        "webhook_host": "0.0.0.0",  # noqa: S104  飞书 webhook 默认监听地址
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
    """加载渠道配置，${VAR} 自动从 os.environ 注入

    配置来源（按优先级）：
    1. $CH_DATA_DIR/channels/<name>.yaml （用户运行时配置）
    2. _CHANNEL_DEFAULTS （内置默认值）

    注意：不再回退到 config/channels/*.yaml.example — 示例文件仅作为模板参考。
    缺少运行时配置时仅使用内置默认值，敏感字段（api_key 等）需通过环境变量提供。
    """
    runtime_path = get_data_dir() / "channels" / f"{channel_name}.yaml"

    config: dict[str, Any] = dict(_CHANNEL_DEFAULTS.get(channel_name, {}))

    if not runtime_path.exists():
        logger.info(
            "渠道配置文件不存在: %s — 使用内置默认值（敏感字段需通过环境变量提供）",
            runtime_path,
        )
    else:
        loaded = load_yaml(runtime_path)
        if isinstance(loaded, dict) and loaded:
            config.update(loaded)
            logger.debug("Loaded channel config: %s", runtime_path)

    resolved = _resolve_env_ref(config)
    if not isinstance(resolved, dict):
        raise TypeError("channel config 必须是 dict")
    return resolved


def build_adapter_config(channel_name: str) -> dict[str, Any]:
    """构建适配器所需的配置 dict（移除元数据字段）"""
    yaml_config = load_channel_config(channel_name)
    return {
        k: v for k, v in yaml_config.items()
        if k not in ("channel_type", "enabled", "routing", "comment")
    }
