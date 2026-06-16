
# ===== Providers =====

def provider_dir():
    d = get_data_dir() / "providers"
    d.mkdir(parents=True, exist_ok=True)
    return d

def provider_path(name):
    return provider_dir() / f"{name}.yaml"

def load_providers():
    providers = {}
    for f in sorted(provider_dir().glob("*.yaml")):
        name = f.stem
        data = _read_yaml(f)
        if data:
            providers[name] = data
    return providers

def save_provider(name, cfg):
    _write_yaml(provider_path(name), cfg)

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
