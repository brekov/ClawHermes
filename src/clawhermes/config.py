"""
ClawHermes - 类型安全配置管理（Pydantic Settings）
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderConf(BaseSettings):
    """单个 LLM 提供商配置"""
    model: str = ""
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 64000
    temperature: float = 0.7
    timeout_ms: int = 60000


class GatewayPlatformConf(BaseSettings):
    """消息渠道配置"""
    enabled: bool = False
    token: str | None = None
    secret: str | None = None


class MemoryConf(BaseSettings):
    """记忆系统配置"""
    engine: Literal["chromadb", "json"] = "chromadb"
    sync_after_turn: bool = True
    max_items: int = 1000


class SkillsConf(BaseSettings):
    """技能系统配置"""
    enabled: bool = True
    background_review: bool = True
    curator_interval_hours: int = 168        # 7天
    stale_after_days: int = 30
    archive_after_days: int = 90


class ContextConf(BaseSettings):
    """上下文管理配置"""
    engine: str = "llm_summary"
    compress_threshold: float = 0.75           # 75% 触发压缩
    protect_first_n: int = 3
    protect_last_n: int = 6
    summary_ratio: float = 0.20                # 摘要 = 内容 × 20%
    summary_tokens_ceiling: int = 12000
    image_token_estimate: int = 1600


class ToolsConf(BaseSettings):
    """工具系统配置"""
    parallel_execution: bool = True
    max_workers: int = 8
    default_timeout_ms: int = 30000
    profile: Literal["minimal", "standard", "full"] = "standard"
    allow: list[str] = []
    deny: list[str] = []


class AgentsConf(BaseSettings):
    """Agent 核心配置"""
    name: str = "clawhermes"
    max_iterations: int = 50
    max_tool_calls_per_round: int = 20
    queue_mode: str = "steer"
    ephemeral_system_prompt: bool = False


class ClawHermesConfig(BaseSettings):
    """ClawHermes 全局配置 - 类型安全"""
    model_config = SettingsConfigDict(
        env_prefix="CH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === LLM Providers ===
    llm_default_model: str = "deepseek/deepseek-chat"
    llm_default_max_tokens: int = 64000

    # DeepSeek
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek/deepseek-chat"

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Google
    google_api_key: str | None = None
    google_model: str = "gemini/gemini-2.5-flash"

    # 本地 Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"

    # === Agent ===
    agent: AgentsConf = AgentsConf()

    # === Gateway ===
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 18789
    gateway_secret: str | None = None

    # 渠道
    weixin: GatewayPlatformConf = GatewayPlatformConf()
    telegram: GatewayPlatformConf = GatewayPlatformConf()
    feishu: GatewayPlatformConf = GatewayPlatformConf()

    # === 子系统 ===
    memory: MemoryConf = MemoryConf()
    skills: SkillsConf = SkillsConf()
    context: ContextConf = ContextConf()
    tools: ToolsConf = ToolsConf()

    # === 存储 ===
    data_dir: str = str(Path.home() / ".clawhermes")
    db_url: str = f"sqlite+aiosqlite:///{Path.home() / '.clawhermes' / 'clawhermes.db'}"

    @field_validator("llm_default_max_tokens")
    @classmethod
    def check_min_context(cls, v: int) -> int:
        """fail-fast: 上下文窗口至少 16K（比Hermes的64K宽松）"""
        if v < 16384:
            raise ValueError(f"max_tokens ({v}) < 16384，请设置更大的上下文窗口")
        return v

    @field_validator("gateway_secret")
    @classmethod
    def check_gateway_secret(cls, v: str | None, info) -> str | None:
        """非回环绑定必须设置 secret"""
        host = info.data.get("gateway_host", "0.0.0.0")
        if host not in ("127.0.0.1", "localhost") and not v:
            raise ValueError(f"Gateway 绑定 {host} 时必须设置 gateway_secret")
        return v


# 全局单例配置
config: ClawHermesConfig | None = None


def load_config(env_file: str | None = None) -> ClawHermesConfig:
    """加载配置，支持自定义 .env 路径"""
    global config
    config = ClawHermesConfig(_env_file=env_file)
    return config
