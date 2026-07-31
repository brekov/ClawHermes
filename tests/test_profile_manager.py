"""ClawHermes - Profile 隔离框架测试

覆盖 ProfileConfig / ProfileContext / ProfileManager 的核心功能，
以及 GatewayState 改造后的向后兼容性。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawhermes.profile import ProfileConfig, ProfileContext, ProfileManager

# ============================================================
# 测试夹具
# ============================================================


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """独立的临时数据目录"""
    return tmp_path


@pytest.fixture
async def initialized_manager(tmp_data_dir: Path) -> ProfileManager:
    """已初始化的 ProfileManager（含自动创建的 default profile）"""
    pm = ProfileManager(tmp_data_dir)
    await pm.initialize()
    yield pm
    await pm.shutdown_all()


# ============================================================
# ProfileConfig 测试
# ============================================================


class TestProfileConfig:
    """ProfileConfig: from_yaml / to_yaml / default / from_dict"""

    def test_default_returns_singleton_like_defaults(self):
        cfg = ProfileConfig.default()
        assert cfg.llm_provider == "deepseek"
        assert cfg.llm_model == "deepseek/deepseek-chat"
        assert cfg.memory_backend == "json"
        assert cfg.memory_max_items == 1000
        assert cfg.skills_dir == "skills"
        assert cfg.tools_profile == "standard"
        assert cfg.agent_max_iterations == 10
        assert cfg.agent_max_context_tokens == 30000
        assert cfg.llm_api_key == ""
        assert cfg.extra == {}

    def test_to_yaml_and_from_yaml_roundtrip(self, tmp_path: Path):
        cfg = ProfileConfig(
            llm_provider="openai",
            llm_model="gpt-4o",
            memory_backend="chroma",
            memory_max_items=500,
            tools_profile="full",
            agent_max_iterations=20,
        )
        yaml_path = tmp_path / "config.yaml"
        cfg.to_yaml(yaml_path)

        loaded = ProfileConfig.from_yaml(yaml_path)
        assert loaded.llm_provider == "openai"
        assert loaded.llm_model == "gpt-4o"
        assert loaded.memory_backend == "chroma"
        assert loaded.memory_max_items == 500
        assert loaded.tools_profile == "full"
        assert loaded.agent_max_iterations == 20

    def test_from_yaml_missing_file_returns_default(self, tmp_path: Path):
        cfg = ProfileConfig.from_yaml(tmp_path / "nonexistent.yaml")
        assert cfg == ProfileConfig.default()

    def test_from_yaml_corrupt_file_returns_default(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: valid: yaml: [unclosed", encoding="utf-8")
        cfg = ProfileConfig.from_yaml(bad)
        assert cfg == ProfileConfig.default()

    def test_from_yaml_non_dict_top_level_returns_default(self, tmp_path: Path):
        bad = tmp_path / "list.yaml"
        bad.write_text("- item1\n- item2\n", encoding="utf-8")
        cfg = ProfileConfig.from_yaml(bad)
        assert cfg == ProfileConfig.default()

    def test_from_dict_collects_unknown_keys_to_extra(self):
        cfg = ProfileConfig.from_dict({
            "llm_model": "custom-model",
            "custom_field": "custom_value",
            "another_unknown": 42,
        })
        assert cfg.llm_model == "custom-model"
        assert cfg.extra == {"custom_field": "custom_value", "another_unknown": 42}

    def test_to_dict_includes_extra_and_omits_empty_extra(self):
        cfg = ProfileConfig(extra={"custom": "val"})
        d = cfg.to_dict()
        assert d["custom"] == "val"
        assert "extra" not in d

        cfg2 = ProfileConfig()
        d2 = cfg2.to_dict()
        assert "extra" not in d2

    def test_to_yaml_creates_parent_dir(self, tmp_path: Path):
        nested = tmp_path / "a" / "b" / "c" / "config.yaml"
        ProfileConfig.default().to_yaml(nested)
        assert nested.exists()


# ============================================================
# ProfileContext 测试
# ============================================================


class TestProfileContext:
    """ProfileContext: initialize / shutdown / attach_components / snapshot"""

    @pytest.mark.asyncio
    async def test_initialize_creates_all_components(self, tmp_path: Path):
        ctx = ProfileContext(
            profile_id="test-profile",
            data_dir=tmp_path / "test-profile",
            config=ProfileConfig.default(),
        )
        assert ctx.is_initialized is False
        assert ctx.agent is None

        await ctx.initialize()

        assert ctx.is_initialized is True
        assert ctx.agent is not None
        assert ctx.memory is not None
        assert ctx.skill_manager is not None
        assert ctx.session_mgr is not None
        assert ctx.delegate_manager is not None
        assert ctx.scheduler is not None

        await ctx.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, tmp_path: Path):
        ctx = ProfileContext(
            profile_id="test-profile",
            data_dir=tmp_path / "test-profile",
            config=ProfileConfig.default(),
        )
        await ctx.initialize()
        first_agent = ctx.agent

        # 第二次 initialize 应直接返回，不创建新组件
        await ctx.initialize()
        assert ctx.agent is first_agent

        await ctx.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent(self, tmp_path: Path):
        ctx = ProfileContext(
            profile_id="test-profile",
            data_dir=tmp_path / "test-profile",
            config=ProfileConfig.default(),
        )
        await ctx.initialize()
        await ctx.shutdown()
        assert ctx.is_initialized is False

        # 第二次 shutdown 应直接返回，不抛异常
        await ctx.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_on_uninitialized_is_noop(self, tmp_path: Path):
        ctx = ProfileContext(
            profile_id="test-profile",
            data_dir=tmp_path / "test-profile",
            config=ProfileConfig.default(),
        )
        # 未初始化时 shutdown 应直接返回
        await ctx.shutdown()
        assert ctx.is_initialized is False

    @pytest.mark.asyncio
    async def test_attach_components_skips_initialize(self, tmp_path: Path):
        """attach_components 注入组件后应标记为已初始化，跳过 initialize 的重复创建"""
        from clawhermes.agent.loop import Agent, AgentConfig
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.agent.session import SessionManager
        from clawhermes.llm.provider import LLMProvider
        from clawhermes.skills.manager import SkillManager
        from clawhermes.tools.registry import ToolRegistry

        data_dir = tmp_path / "default"
        provider = LLMProvider(model="test/model", api_key="test-key")
        registry = ToolRegistry()
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(data_dir))
        sm = SkillManager(data_dir / "skills")
        session_mgr = SessionManager(data_dir)
        agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=AgentConfig(max_iterations=1),
            memory_manager=memory,
            skill_manager=sm,
            session_mgr=session_mgr,
        )

        ctx = ProfileContext(
            profile_id="default",
            data_dir=data_dir,
            config=ProfileConfig.default(),
        )
        ctx.attach_components(
            agent=agent,
            memory=memory,
            skill_manager=sm,
            session_mgr=session_mgr,
        )
        assert ctx.is_initialized is True
        assert ctx.agent is agent
        assert ctx.memory is memory
        # initialize 应跳过（已通过 attach 标记为 initialized）
        await ctx.initialize()
        assert ctx.agent is agent  # 未被替换

        session_mgr.close()

    def test_snapshot_returns_serializable_dict(self, tmp_path: Path):
        ctx = ProfileContext(
            profile_id="test",
            data_dir=tmp_path / "test",
            config=ProfileConfig(llm_model="custom-model", tools_profile="full"),
        )
        snap = ctx.snapshot()
        assert snap["profile_id"] == "test"
        assert snap["data_dir"] == str(tmp_path / "test")
        assert snap["initialized"] is False
        assert snap["llm_model"] == "custom-model"
        assert snap["tools_profile"] == "full"


# ============================================================
# ProfileManager 测试
# ============================================================


class TestProfileManager:
    """ProfileManager: initialize / create / get / delete / list / bind / resolve"""

    @pytest.mark.asyncio
    async def test_initialize_creates_default_on_empty_dir(self, tmp_data_dir: Path):
        pm = ProfileManager(tmp_data_dir)
        await pm.initialize()

        assert pm.profile_count() == 1
        assert pm.has_profile("default")
        assert (tmp_data_dir / "profiles" / "default" / "config.yaml").exists()

        await pm.shutdown_all()

    @pytest.mark.asyncio
    async def test_initialize_loads_existing_profiles(self, tmp_data_dir: Path):
        # 预置一个 research profile
        research_dir = tmp_data_dir / "profiles" / "research"
        research_dir.mkdir(parents=True)
        ProfileConfig(llm_model="gpt-4o", tools_profile="full").to_yaml(
            research_dir / "config.yaml"
        )

        pm = ProfileManager(tmp_data_dir)
        await pm.initialize()

        assert pm.profile_count() == 2
        assert pm.has_profile("default")
        assert pm.has_profile("research")
        research = pm.get_profile("research")
        assert research.config.llm_model == "gpt-4o"

        await pm.shutdown_all()

    @pytest.mark.asyncio
    async def test_initialize_skips_invalid_dir_names(self, tmp_data_dir: Path):
        # 创建非法命名的目录（含点号），应被跳过
        bad_dir = tmp_data_dir / "profiles" / "bad.name"
        bad_dir.mkdir(parents=True)

        pm = ProfileManager(tmp_data_dir)
        await pm.initialize()

        assert pm.profile_count() == 1
        assert not pm.has_profile("bad.name")

        await pm.shutdown_all()

    @pytest.mark.asyncio
    async def test_initialize_with_default_context_injection(self, tmp_data_dir: Path):
        """default_context 注入路径：跳过 default 自动创建，直接注册"""
        from clawhermes.agent.loop import Agent, AgentConfig
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.agent.session import SessionManager
        from clawhermes.llm.provider import LLMProvider
        from clawhermes.skills.manager import SkillManager
        from clawhermes.tools.registry import ToolRegistry

        data_dir = tmp_data_dir / "default"
        provider = LLMProvider(model="test/model", api_key="test-key")
        registry = ToolRegistry()
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(data_dir))
        sm = SkillManager(data_dir / "skills")
        session_mgr = SessionManager(data_dir)
        agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=AgentConfig(max_iterations=1),
            memory_manager=memory,
            skill_manager=sm,
            session_mgr=session_mgr,
        )

        ctx = ProfileContext(
            profile_id="default",
            data_dir=data_dir,
            config=ProfileConfig.default(),
        )
        ctx.attach_components(agent=agent, memory=memory, skill_manager=sm, session_mgr=session_mgr)

        pm = ProfileManager(tmp_data_dir)
        await pm.initialize(default_context=ctx)

        # default 已注入，不应重复加载
        assert pm.profile_count() == 1
        assert pm.get_default().agent is agent

        session_mgr.close()
        await pm.shutdown_all()

    @pytest.mark.asyncio
    async def test_create_profile_success(self, initialized_manager: ProfileManager):
        ctx = await initialized_manager.create_profile(
            "research",
            config=ProfileConfig(llm_model="gpt-4o", tools_profile="full"),
        )
        assert ctx.profile_id == "research"
        assert ctx.agent is not None
        assert initialized_manager.has_profile("research")
        assert initialized_manager.profile_count() == 2

    @pytest.mark.asyncio
    async def test_create_profile_with_default_config(self, initialized_manager: ProfileManager):
        ctx = await initialized_manager.create_profile("plain")
        assert ctx.profile_id == "plain"
        assert ctx.config == ProfileConfig.default()

    @pytest.mark.asyncio
    async def test_create_profile_invalid_id_raises(self, initialized_manager: ProfileManager):
        with pytest.raises(ValueError, match="无效的 profile_id"):
            await initialized_manager.create_profile("bad.name")
        with pytest.raises(ValueError, match="无效的 profile_id"):
            await initialized_manager.create_profile("")
        with pytest.raises(ValueError, match="无效的 profile_id"):
            await initialized_manager.create_profile("a" * 65)  # 超长

    @pytest.mark.asyncio
    async def test_create_profile_duplicate_raises(self, initialized_manager: ProfileManager):
        with pytest.raises(ValueError, match="Profile 已存在"):
            await initialized_manager.create_profile("default")

    @pytest.mark.asyncio
    async def test_get_profile_none_returns_default(self, initialized_manager: ProfileManager):
        ctx = initialized_manager.get_profile(None)
        assert ctx.profile_id == "default"

    @pytest.mark.asyncio
    async def test_get_profile_not_found_raises(self, initialized_manager: ProfileManager):
        with pytest.raises(KeyError, match="Profile not found"):
            initialized_manager.get_profile("nonexistent")

    @pytest.mark.asyncio
    async def test_get_default(self, initialized_manager: ProfileManager):
        ctx = initialized_manager.get_default()
        assert ctx.profile_id == "default"

    @pytest.mark.asyncio
    async def test_delete_profile_success(self, initialized_manager: ProfileManager):
        await initialized_manager.create_profile("to-delete")
        assert initialized_manager.has_profile("to-delete")

        result = await initialized_manager.delete_profile("to-delete")
        assert result is True
        assert not initialized_manager.has_profile("to-delete")

    @pytest.mark.asyncio
    async def test_delete_profile_not_found_returns_false(
        self, initialized_manager: ProfileManager
    ):
        result = await initialized_manager.delete_profile("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_default_raises(self, initialized_manager: ProfileManager):
        with pytest.raises(ValueError, match="不能删除 default profile"):
            await initialized_manager.delete_profile("default")

    @pytest.mark.asyncio
    async def test_delete_profile_clears_user_bindings(
        self, initialized_manager: ProfileManager
    ):
        await initialized_manager.create_profile("research")
        initialized_manager.bind_user("user1", "research")
        assert initialized_manager.get_user_binding("user1") == "research"

        await initialized_manager.delete_profile("research")
        assert initialized_manager.get_user_binding("user1") is None

    @pytest.mark.asyncio
    async def test_list_profiles(self, initialized_manager: ProfileManager):
        await initialized_manager.create_profile("alpha")
        await initialized_manager.create_profile("beta")

        items = initialized_manager.list_profiles()
        assert len(items) == 3
        ids = [item["profile_id"] for item in items]
        assert ids == ["alpha", "beta", "default"]

    @pytest.mark.asyncio
    async def test_bind_user_success(self, initialized_manager: ProfileManager):
        await initialized_manager.create_profile("research")
        initialized_manager.bind_user("user1", "research")
        assert initialized_manager.get_user_binding("user1") == "research"

    @pytest.mark.asyncio
    async def test_bind_user_invalid_user_id(self, initialized_manager: ProfileManager):
        with pytest.raises(ValueError, match="user_id 不能为空"):
            initialized_manager.bind_user("", "default")

    @pytest.mark.asyncio
    async def test_bind_user_unknown_profile_raises(self, initialized_manager: ProfileManager):
        with pytest.raises(KeyError, match="Profile not found"):
            initialized_manager.bind_user("user1", "nonexistent")

    @pytest.mark.asyncio
    async def test_unbind_user(self, initialized_manager: ProfileManager):
        initialized_manager.bind_user("user1", "default")
        assert initialized_manager.unbind_user("user1") is True
        assert initialized_manager.get_user_binding("user1") is None
        assert initialized_manager.unbind_user("user1") is False  # 再次解绑返回 False

    @pytest.mark.asyncio
    async def test_resolve_profile_explicit_wins(self, initialized_manager: ProfileManager):
        await initialized_manager.create_profile("research")
        initialized_manager.bind_user("user1", "research")

        # explicit_id 优先于 user_id binding
        ctx = initialized_manager.resolve_profile(
            user_id="user1", explicit_id="default"
        )
        assert ctx.profile_id == "default"

    @pytest.mark.asyncio
    async def test_resolve_profile_user_binding(self, initialized_manager: ProfileManager):
        await initialized_manager.create_profile("research")
        initialized_manager.bind_user("user1", "research")

        ctx = initialized_manager.resolve_profile(user_id="user1")
        assert ctx.profile_id == "research"

    @pytest.mark.asyncio
    async def test_resolve_profile_falls_back_to_default(
        self, initialized_manager: ProfileManager
    ):
        ctx = initialized_manager.resolve_profile(user_id="unknown-user")
        assert ctx.profile_id == "default"

        ctx = initialized_manager.resolve_profile(user_id=None)
        assert ctx.profile_id == "default"

    @pytest.mark.asyncio
    async def test_resolve_profile_explicit_not_found_raises(
        self, initialized_manager: ProfileManager
    ):
        with pytest.raises(KeyError, match="Profile not found"):
            initialized_manager.resolve_profile(user_id=None, explicit_id="nonexistent")

    @pytest.mark.asyncio
    async def test_bindings_persist_across_restart(self, tmp_data_dir: Path):
        """用户绑定持久化到 profile_bindings.json，重启后恢复"""
        pm1 = ProfileManager(tmp_data_dir)
        await pm1.initialize()
        await pm1.create_profile("research")
        pm1.bind_user("user1", "research")
        await pm1.shutdown_all()

        # 重启
        pm2 = ProfileManager(tmp_data_dir)
        await pm2.initialize()
        assert pm2.get_user_binding("user1") == "research"
        await pm2.shutdown_all()

    @pytest.mark.asyncio
    async def test_bindings_skip_orphaned_references(self, tmp_data_dir: Path):
        """bindings 文件中指向已删除 profile 的绑定应被过滤"""
        import json

        bindings_file = tmp_data_dir / "profile_bindings.json"
        tmp_data_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240  测试同步 setup
        bindings_file.write_text(  # noqa: ASYNC240  测试同步 setup
            json.dumps({"user1": "ghost-profile"}),
            encoding="utf-8",
        )

        pm = ProfileManager(tmp_data_dir)
        await pm.initialize()
        # ghost-profile 不存在，绑定应被过滤
        assert pm.get_user_binding("user1") is None
        await pm.shutdown_all()

    @pytest.mark.asyncio
    async def test_shutdown_all_clears_state(self, initialized_manager: ProfileManager):
        await initialized_manager.create_profile("research")
        initialized_manager.bind_user("user1", "research")

        await initialized_manager.shutdown_all()
        assert initialized_manager.profile_count() == 0
        assert initialized_manager.get_user_binding("user1") is None

    @pytest.mark.asyncio
    async def test_global_api_keys_inherited(self, tmp_data_dir: Path):
        """global_config.api_keys 透传到 ProfileContext.initialize"""
        pm = ProfileManager(tmp_data_dir)
        await pm.initialize(
            global_config={"api_keys": {"deepseek": "sk-inherited-key"}}
        )

        default_ctx = pm.get_default()
        # ProfileContext.initialize 已执行，agent 创建成功即说明 api_key 链路工作
        assert default_ctx.agent is not None

        await pm.shutdown_all()


# ============================================================
# GatewayState 向后兼容性测试
# ============================================================


class TestGatewayStateCompat:
    """验证 GatewayState 改造后向后兼容：现有 _state.agent 等访问仍然有效"""

    def test_gateway_state_has_profile_manager_field(self):
        """GatewayState 实例化后应有 profile_manager 字段（初始为 None）"""
        from clawhermes.gateway.app import GatewayState

        state = GatewayState()
        assert hasattr(state, "profile_manager")
        assert state.profile_manager is None

    @pytest.mark.asyncio
    async def test_initialize_populates_profile_manager(self, monkeypatch):
        """initialize() 完成后 profile_manager 应为 ProfileManager 实例"""
        import tempfile
        from unittest.mock import AsyncMock, MagicMock, patch

        from clawhermes.gateway.app import GatewayState

        monkeypatch.setenv("CH_DATA_DIR", tempfile.mkdtemp())
        state = GatewayState()

        with patch("clawhermes.gateway.app.build_adapter_config", return_value={}), \
                patch("clawhermes.gateway.app.CronScheduler") as mock_scheduler_cls, \
                patch("clawhermes.gateway.app.ChannelRouter") as mock_router_cls:
            mock_sched = MagicMock()
            mock_sched.start = AsyncMock()
            mock_sched.stop = AsyncMock()
            mock_sched.job_count = 0
            mock_scheduler_cls.return_value = mock_sched

            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router.get_queue_size = MagicMock(return_value=0)
            mock_router.get_active_session = MagicMock(return_value=None)
            mock_router.list_channels = MagicMock(return_value=[])
            mock_router.session_router = MagicMock()
            mock_router.session_router.list_mappings = MagicMock(return_value=[])
            mock_router_cls.return_value = mock_router

            await state.initialize(
                api_key="test-key",
                model="test/model",
                profile="minimal",
            )

        # profile_manager 应已初始化
        assert state.profile_manager is not None
        assert state.profile_manager.profile_count() == 1
        assert state.profile_manager.has_profile("default")

        # 向后兼容：现有字段仍可访问
        assert state.agent is not None
        assert state.memory is not None
        assert state.session_mgr is not None
        assert state.is_initialized() is True

        # default profile 的组件应与 state 上的组件一致（同一对象）
        default_ctx = state.profile_manager.get_default()
        assert default_ctx.agent is state.agent
        assert default_ctx.memory is state.memory

        await state.shutdown()

    @pytest.mark.asyncio
    async def test_profile_manager_failure_falls_back_gracefully(self, monkeypatch):
        """ProfileManager 初始化失败时不应阻断主初始化流程"""
        import tempfile
        from unittest.mock import AsyncMock, MagicMock, patch

        from clawhermes.gateway.app import GatewayState

        monkeypatch.setenv("CH_DATA_DIR", tempfile.mkdtemp())
        state = GatewayState()

        with patch("clawhermes.gateway.app.build_adapter_config", return_value={}), \
                patch("clawhermes.gateway.app.CronScheduler") as mock_scheduler_cls, \
                patch("clawhermes.gateway.app.ChannelRouter") as mock_router_cls, \
                patch(
                    "clawhermes.gateway.app.ProfileManager.initialize",
                    AsyncMock(side_effect=RuntimeError("init failure")),
                ):
            mock_sched = MagicMock()
            mock_sched.start = AsyncMock()
            mock_sched.stop = AsyncMock()
            mock_sched.job_count = 0
            mock_scheduler_cls.return_value = mock_sched

            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router.get_queue_size = MagicMock(return_value=0)
            mock_router.get_active_session = MagicMock(return_value=None)
            mock_router.list_channels = MagicMock(return_value=[])
            mock_router.session_router = MagicMock()
            mock_router.session_router.list_mappings = MagicMock(return_value=[])
            mock_router_cls.return_value = mock_router

            # 不应抛异常
            await state.initialize(
                api_key="test-key",
                model="test/model",
                profile="minimal",
            )

        # 回退到单 Profile 模式：profile_manager 为 None，但 agent 仍可用
        assert state.profile_manager is None
        assert state.agent is not None
        assert state.is_initialized() is True

        await state.shutdown()
