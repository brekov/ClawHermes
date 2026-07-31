"""ClawHermes - Profile 级配置

每个 Profile 拥有独立的配置文件 ``profiles/<id>/config.yaml``，
用于覆盖全局配置（LLM 提供商、记忆后端、工具分级等）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProfileConfig:
    """Profile 级配置

    所有字段均有默认值，缺失字段自动回填，保证向后兼容：
    旧版 ``profiles/<id>/config.yaml`` 不存在的 key 不会导致加载失败。
    """

    llm_provider: str = "deepseek"
    llm_model: str = "deepseek/deepseek-chat"
    # 从环境变量或全局配置继承（不在 profile 配置中持久化真实密钥）
    llm_api_key: str = ""
    memory_backend: str = "json"  # "json" | "chroma"
    memory_max_items: int = 1000
    skills_dir: str = "skills"
    tools_profile: str = "standard"  # "minimal" | "standard" | "full"
    agent_max_iterations: int = 10
    agent_max_context_tokens: int = 30000
    # 预留扩展字段（未识别的 YAML key 收集于此，避免丢失用户自定义配置）
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "ProfileConfig":
        """从 YAML 文件加载配置

        文件不存在或解析失败时返回默认配置（容错策略，对齐 ``config.load_yaml``）。
        """
        import yaml

        p = Path(path)
        if not p.exists():
            return cls.default()
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.warning("Profile 配置加载失败 (%s): %s，回退到默认", p, e)
            return cls.default()

        if not isinstance(data, dict):
            logger.warning("Profile 配置顶层不是 dict (%s)，回退到默认", p)
            return cls.default()

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileConfig":
        """从 dict 构造配置，未知 key 收集到 ``extra``"""
        known = {f.name for f in fields(cls) if f.name != "extra"}
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for k, v in data.items():
            if k in known:
                kwargs[k] = v
            else:
                extra[k] = v
        kwargs["extra"] = extra
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """序列化为可写 YAML 的 dict（剔除空 extra 减少噪音）"""
        result: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "extra":
                if self.extra:
                    result.update(self.extra)
                continue
            result[f.name] = getattr(self, f.name)
        return result

    def to_yaml(self, path: Path) -> None:
        """保存配置到 YAML 文件"""
        import yaml

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(
                self.to_dict(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    @classmethod
    def default(cls) -> "ProfileConfig":
        """默认配置（向后兼容：无 profile 时等效于现有单 Profile 行为）"""
        return cls()
