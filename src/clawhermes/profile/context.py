"""ClawHermes - Profile 运行时上下文

单个 Profile 的完整运行时上下文，封装该 Profile 独有的
Agent / Memory / SkillManager / SessionManager / DelegateManager / CronScheduler
六大组件，提供统一的 ``initialize`` / ``shutdown`` 生命周期入口。

设计要点：
- 所有组件实例完全隔离，profile 间互不影响
- ``initialize`` 是异步方法（CronScheduler.start / 可能的 IO 阻塞需在事件循环内完成）
- 支持从外部注入已构建的组件（GatewayState 改造时复用现有 default 组件）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clawhermes.profile.config import ProfileConfig

if TYPE_CHECKING:
    # 仅类型注解使用，避免运行时循环导入
    from clawhermes.agent.delegate import DelegateManager
    from clawhermes.agent.loop import Agent
    from clawhermes.agent.memory import MemoryManager
    from clawhermes.agent.scheduler import CronScheduler
    from clawhermes.agent.session import SessionManager
    from clawhermes.skills.manager import SkillManager

logger = logging.getLogger(__name__)


@dataclass
class ProfileContext:
    """单个 Profile 的完整运行时上下文

    Attributes:
        profile_id: Profile 唯一标识
        data_dir: 该 Profile 的独立数据目录（``profiles/<id>/``）
        config: Profile 级配置
        agent / memory / skill_manager / session_mgr / delegate_manager / scheduler:
            六大组件实例，``initialize`` 后可用
        _initialized: 是否已初始化（防止重复 initialize/shutdown）
    """

    profile_id: str
    data_dir: Path
    config: ProfileConfig
    agent: "Agent | None" = None
    memory: "MemoryManager | None" = None
    skill_manager: "SkillManager | None" = None
    session_mgr: "SessionManager | None" = None
    delegate_manager: "DelegateManager | None" = None
    scheduler: "CronScheduler | None" = None
    _initialized: bool = False

    async def initialize(self, global_api_keys: dict[str, str] | None = None) -> None:
        """初始化所有组件（Agent/Memory/Skills/Sessions/Delegate/Scheduler）

        幂等：已初始化时直接返回，避免重复创建资源（如线程池、调度循环）。

        Args:
            global_api_keys: 全局 API 密钥表，按 ``llm_provider`` 取值继承到 Profile。
                为 None 或不含当前 provider 时回退到 ``config.llm_api_key``。
        """
        if self._initialized:
            return

        # 延迟导入避免在模块加载时拉起全部子系统依赖
        from clawhermes.agent.delegate import DelegateManager
        from clawhermes.agent.loop import Agent, AgentConfig
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.agent.scheduler import CronScheduler
        from clawhermes.agent.session import SessionManager
        from clawhermes.llm.provider import LLMProvider
        from clawhermes.skills.manager import SkillManager
        from clawhermes.tools.builtin import register_builtin_tools
        from clawhermes.tools.registry import ToolRegistry

        data_dir = Path(self.data_dir)
        # 各子组件（JSONMemoryProvider / SkillManager / SessionManager / CronScheduler）
        # 在 __init__ 中会自行 mkdir(parents=True, exist_ok=True)，此处无需重复创建
        cfg = self.config

        # 1. LLM Provider — API key 优先级：profile 自带 > global_api_keys[provider] > 空
        api_key = cfg.llm_api_key
        if not api_key and global_api_keys:
            api_key = global_api_keys.get(cfg.llm_provider, "")
        provider = LLMProvider(model=cfg.llm_model, api_key=api_key)

        # 2. 工具注册表（按 tools_profile 分级）
        registry = ToolRegistry()
        register_builtin_tools(registry, profile=cfg.tools_profile)

        # 3. 记忆管理器（仅 JSON 后端，ChromaDB 由 gateway 主初始化路径处理）
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(data_dir, max_items=cfg.memory_max_items))

        # 4. 技能管理器（独立 skills 目录）
        skill_manager = SkillManager(data_dir / cfg.skills_dir)

        # 5. 会话管理器（独立 sessions.db）
        session_mgr = SessionManager(data_dir)

        # 6. 委派管理器
        delegate_mgr = DelegateManager(
            llm_provider=provider,
            tool_registry=registry,
            memory_manager=memory,
            skill_manager=skill_manager,
        )

        # 7. Agent
        agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=AgentConfig(max_iterations=cfg.agent_max_iterations),
            memory_manager=memory,
            skill_manager=skill_manager,
            delegate_manager=delegate_mgr,
            session_mgr=session_mgr,
        )

        # 8. 调度器（独立 schedules.json）
        scheduler = CronScheduler(data_dir)
        scheduler.set_executor(lambda task, sid: agent.chat(task, session_id=sid))
        await scheduler.start()

        # 全部成功后赋值（保持与 GatewayState.initialize 同样的失败回滚语义）
        self.agent = agent
        self.memory = memory
        self.skill_manager = skill_manager
        self.session_mgr = session_mgr
        self.delegate_manager = delegate_mgr
        self.scheduler = scheduler
        self._initialized = True

        logger.info(
            "ProfileContext 初始化完成: %s (model=%s, tools=%s)",
            self.profile_id,
            cfg.llm_model,
            cfg.tools_profile,
        )

    async def shutdown(self) -> None:
        """关闭所有组件（优雅释放线程池 / 调度循环 / 数据库连接）

        幂等：未初始化或已关闭时直接返回。组件 shutdown 异常被吞掉并记录，
        保证一个组件失败不会阻塞其他组件的关闭。
        """
        if not self._initialized:
            return

        # 调度器：停止 asyncio 循环
        if self.scheduler is not None:
            try:
                await self.scheduler.stop()
            except Exception as e:  # noqa: BLE001  优雅关闭需容错
                logger.warning("Profile %s scheduler 关闭失败: %s", self.profile_id, e)

        # 委派管理器：关闭线程池
        if self.delegate_manager is not None:
            try:
                self.delegate_manager.shutdown(wait=True)
            except Exception as e:  # noqa: BLE001  优雅关闭需容错
                logger.warning(
                    "Profile %s delegate_manager 关闭失败: %s", self.profile_id, e
                )

        # 会话管理器：关闭 SQLite 连接
        if self.session_mgr is not None:
            try:
                self.session_mgr.close()
            except Exception as e:  # noqa: BLE001  优雅关闭需容错
                logger.warning("Profile %s session_mgr 关闭失败: %s", self.profile_id, e)

        self._initialized = False
        logger.info("ProfileContext 已关闭: %s", self.profile_id)

    @property
    def is_initialized(self) -> bool:
        """是否已完成 initialize"""
        return self._initialized

    def attach_components(
        self,
        *,
        agent: "Agent | None" = None,
        memory: "MemoryManager | None" = None,
        skill_manager: "SkillManager | None" = None,
        session_mgr: "SessionManager | None" = None,
        delegate_manager: "DelegateManager | None" = None,
        scheduler: "CronScheduler | None" = None,
    ) -> None:
        """从外部注入已构建的组件（用于 GatewayState 包装 default profile）

        注入后标记为已初始化，跳过 ``initialize`` 的重复创建路径。
        用于 PR5a 最小化改造：GatewayState 现有 ``_init_*`` 链路构建的 default
        组件可直接包装为 ProfileContext，无需重新创建。
        """
        if agent is not None:
            self.agent = agent
        if memory is not None:
            self.memory = memory
        if skill_manager is not None:
            self.skill_manager = skill_manager
        if session_mgr is not None:
            self.session_mgr = session_mgr
        if delegate_manager is not None:
            self.delegate_manager = delegate_manager
        if scheduler is not None:
            self.scheduler = scheduler
        # 注入即视为已初始化（组件已就绪）
        self._initialized = self._initialized or any(
            v is not None
            for v in (agent, memory, skill_manager, session_mgr, delegate_manager, scheduler)
        )

    def snapshot(self) -> dict[str, Any]:
        """返回可序列化的状态快照（供 list_profiles 展示）"""
        return {
            "profile_id": self.profile_id,
            "data_dir": str(self.data_dir),
            "initialized": self._initialized,
            "llm_model": self.config.llm_model,
            "llm_provider": self.config.llm_provider,
            "tools_profile": self.config.tools_profile,
            "memory_backend": self.config.memory_backend,
        }
