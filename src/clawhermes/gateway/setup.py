"""ClawHermes - Provider 配置管理"""
from __future__ import annotations

import os
from pathlib import Path

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


def provider_dir() -> Path:
    d = get_data_dir() / "providers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def provider_path(name: str) -> Path:
    return provider_dir() / f"{name}.yaml"


def load_providers() -> dict[str, dict]:
    providers = {}
    for f in sorted(provider_dir().glob("*.yaml")):
        name = f.stem
        data = _read_yaml(f)
        if data:
            providers[name] = data
    return providers


def save_provider(name: str, cfg: dict):
    _write_yaml(provider_path(name), cfg)


def delete_provider(name: str):
    p = provider_path(name)
    if p.exists():
        p.unlink()
