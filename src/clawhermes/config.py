"""
ClawHermes - 类型安全配置管理（Pydantic Settings）
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Track config parse warnings to avoid spam
_CONFIG_PARSE_WARNED: set = set()

# Env var names that control how the next subprocess executes —
# never writable through save_env_value.
_BLOCKED_ENV_PREFIXES: tuple[str, ...] = (
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT",  # Linux dynamic loader
    "DYLD_",                                      # macOS dynamic loader
    "PYTHONPATH", "PYTHONHOME",                   # Python loader
    "PATH",                                        # Shell path
)

# ===== 数据目录 =====

def get_data_dir() -> Path:
    """ClawHermes 数据目录 — 默认为 ~/.clawhermes"""
    return Path(os.getenv("CH_DATA_DIR", str(Path.home() / ".clawhermes")))


def load_env() -> None:
    """加载 $CH_DATA_DIR/.env 到 os.environ（不覆盖已有环境变量）。

    统一入口，替代各模块自行手写 .env 解析或直接调用 load_dotenv。
    """
    from dotenv import load_dotenv
    load_dotenv(get_data_dir() / ".env", override=False)




class LLMProviderConf(BaseSettings):
    """单个 LLM 提供商配置"""
    model: str = ""
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 64000
    temperature: float = 0.7
    timeout_ms: int = 60000


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
        env_file=str(get_data_dir() / ".env"),
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
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 18789
    gateway_secret: str | None = None

    # 渠道（声明式配置，启动自动连接）

    # === 子系统 ===
    memory: MemoryConf = MemoryConf()
    skills: SkillsConf = SkillsConf()
    context: ContextConf = ContextConf()
    tools: ToolsConf = ToolsConf()

    # === 存储 ===
    # 使用 default_factory 延迟到实例化时求值，确保尊重 CH_DATA_DIR 环境变量
    # （类级默认值会在模块导入时调用 Path.home()，无法响应后续 env 变更）
    data_dir: str = Field(default_factory=lambda: str(get_data_dir()))
    db_url: str = Field(
        default_factory=lambda: f"sqlite+aiosqlite:///{get_data_dir() / 'clawhermes.db'}"
    )

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
        host = info.data.get("gateway_host", "0.0.0.0")  # noqa: S104  默认绑定地址，非实际监听
        if host not in ("127.0.0.1", "localhost") and not v:
            raise ValueError(f"Gateway 绑定 {host} 时必须设置 gateway_secret")
        return v


# ===== YAML 配置文件（类似 Hermes config.yaml / OpenClaw openclaw.json）=====


def get_yaml_path() -> Path:
    return get_data_dir() / "config.yaml"


def _backup_corrupt_config(config_path: Path) -> Path | None:
    """备份损坏的 config.yaml 到 .bak 文件

    对齐 Hermes _backup_corrupt_config：损坏的配置文件在静默回退到默认
    配置前会被快照保存，防止用户丢失可恢复的手动编辑。
    """
    try:
        if config_path.is_symlink():
            return None
        st = config_path.stat()
        if st.st_size == 0:
            return None
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.corrupt.{ts}.bak")
        if backup_path.exists():
            return None
        shutil.copy2(config_path, backup_path)
        return backup_path
    except Exception:
        return None


def _warn_config_parse_failure(config_path: Path, exc: Exception) -> None:
    """记录并报告 config.yaml 解析失败

    对齐 Hermes _warn_config_parse_failure：每个损坏文件只警告一次
    （通过 mtime/size 去重），同时记录到日志和 stderr。
    """
    try:
        st = config_path.stat()
        key = (str(config_path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(config_path), 0, 0)
    if key in _CONFIG_PARSE_WARNED:
        return
    _CONFIG_PARSE_WARNED.add(key)

    backup_path = _backup_corrupt_config(config_path)
    msg = (
        f"无法解析 {config_path}: {exc}. "
        f"回退到默认配置 — 所有用户覆盖（模型、Gateway、渠道设置）均被忽略. "
        f"修复 YAML 后重启."
    )
    if backup_path is not None:
        msg += f" 损坏文件的副本已保存到 {backup_path}."
    logger.warning(msg)
    try:
        import sys
        sys.stderr.write(f"⚠️  clawhermes config: {msg}\n")
        sys.stderr.flush()
    except Exception:  # noqa: S110  stderr 写入失败时无法记录，静默忽略
        pass


def load_yaml(path: Path | None = None) -> dict:
    """加载 YAML 配置文件（带损坏备份）

    Args:
        path: YAML 文件路径。默认为 config.yaml (get_yaml_path())。
              传入路径可获得与主配置相同的损坏备份 + 告警行为。
    """
    import yaml
    p = path or get_yaml_path()
    if p.exists():
        try:
            with open(p) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            _warn_config_parse_failure(p, e)
    return {}


def is_env_var_safe(name: str) -> bool:
    """检查环境变量名是否安全可写入 .env

    阻断可能影响子进程执行的危险环境变量（对齐 Hermes env var safety）。
    """
    name_upper = name.upper()
    for prefix in _BLOCKED_ENV_PREFIXES:
        if name_upper.startswith(prefix):
            return False
    return True


def save_yaml(cfg: dict):
    """保存 config.yaml"""
    import yaml
    p = get_yaml_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, indent=2)
    print(f"  ✅ 配置已保存: {p}")


def default_yaml() -> dict:
    """生成默认 config.yaml"""
    return {
        "agent": {
            "name": "default",
            "model": "deepseek/deepseek-chat",
            "max_iterations": 50,
        },
        "gateway": {"host": "127.0.0.1", "port": 18789},
        "llm": {"provider": "deepseek"},
        "memory": {"engine": "chromadb"},
        "skills": {"enabled": True, "background_review": True, "curator_interval_hours": 168},
        "context": {"compress_threshold": 0.75, "protect_first_n": 3, "protect_last_n": 6},
        "tools": {"parallel_execution": True, "profile": "standard"},
    }


# 全局单例
config: ClawHermesConfig | None = None


def load_config(env_file: str | None = None) -> ClawHermesConfig:
    """加载配置（环境变量 + YAML）"""
    global config
    config = ClawHermesConfig()
    return config
