"""ClawHermes - Profile 管理器

管理多 Profile 完整生命周期：扫描加载、按需创建、用户绑定、
解析优先级（explicit_id > user_id binding > default）。

线程安全：
- ``_profiles`` / ``_user_bindings`` 的读写均通过 ``_lock`` 保护
- ``resolve_profile`` / ``get_profile`` / ``bind_user`` 可在多线程上下文调用
- 异步方法（``initialize`` / ``create_profile`` / ``delete_profile`` / ``shutdown_all``）
  在持有锁时仅做 dict 操作，IO/异步操作在锁外执行以避免长持有
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clawhermes.profile.config import ProfileConfig
from clawhermes.profile.context import ProfileContext

if TYPE_CHECKING:
    # 仅类型注解使用，避免运行时循环导入
    pass

logger = logging.getLogger(__name__)

# Profile ID 命名规则：与 ScopedPath.NAME_PATTERN 对齐，确保目录名安全
_PROFILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_\-]{1,64}")

# 全局绑定持久化文件名（与 pairing.json 同级，独立文件避免污染 pairing 状态）
_BINDINGS_FILENAME = "profile_bindings.json"


class ProfileManager:
    """管理多 Profile 完整生命周期"""

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._profiles_dir = self._data_dir / "profiles"
        self._profiles: dict[str, ProfileContext] = {}
        self._user_bindings: dict[str, str] = {}  # user_id → profile_id
        self._lock = threading.RLock()
        self._default_id = "default"
        self._bindings_file = self._data_dir / _BINDINGS_FILENAME

    # ============================================================
    # 生命周期
    # ============================================================

    async def initialize(
        self,
        global_config: dict | None = None,
        default_context: ProfileContext | None = None,
    ) -> None:
        """扫描 ``profiles/`` 目录自动加载所有 profile

        步骤：
        1. 确保 ``profiles/`` 目录存在
        2. 处理 default profile：
           - 若 ``default_context`` 提供：直接注册为 default（跳过自动创建/加载，
             用于 GatewayState 复用现有 default 组件，避免重复初始化）
           - 否则：若 ``profiles/default`` 不存在则自动创建，并加载
        3. 遍历 ``profiles/`` 下每个其他子目录，加载 ProfileConfig + 创建 ProfileContext
        4. 加载 user_bindings（从 ``profile_bindings.json``）

        Args:
            global_config: 全局配置 dict，用于为 Profile 提供默认 api_key 等继承值。
                当前实现仅透传 ``global_api_keys`` 子 dict 到 ProfileContext.initialize。
            default_context: 外部预构建的 default ProfileContext（可选）。
                提供时跳过 default 的自动创建与加载，直接注册到 ``_profiles``。
        """
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        # 1. 处理 default profile
        if default_context is not None:
            # 外部注入 default（GatewayState 改造路径）：直接注册，跳过自动创建
            with self._lock:
                self._profiles[default_context.profile_id] = default_context
            logger.info("使用外部注入的 default ProfileContext: %s", default_context.profile_id)
        else:
            # 自动创建 default profile（若不存在）
            default_dir = self._profiles_dir / self._default_id
            if not default_dir.exists():
                logger.info("未检测到 default profile，自动创建: %s", default_dir)
                default_cfg = ProfileConfig.default()
                default_cfg.to_yaml(default_dir / "config.yaml")

        # 2. 提取全局 API 密钥表（供 profile 继承）
        global_api_keys: dict[str, str] = {}
        if isinstance(global_config, dict):
            raw_keys = global_config.get("api_keys")
            if isinstance(raw_keys, dict):
                global_api_keys = {str(k): str(v) for k, v in raw_keys.items()}

        # 3. 遍历加载每个 profile 子目录（跳过已注册的 default）
        loaded_ids: list[str] = []
        with self._lock:
            already_loaded = set(self._profiles.keys())
        for child in sorted(self._profiles_dir.iterdir()):
            if not child.is_dir():
                continue
            pid = child.name
            if not _PROFILE_ID_PATTERN.fullmatch(pid):
                logger.warning("跳过非法 profile 目录名: %s", pid)
                continue
            if pid in already_loaded:
                # default_context 注入路径下跳过 default 重新加载
                loaded_ids.append(pid)
                continue
            try:
                await self._load_profile(pid, global_api_keys)
                loaded_ids.append(pid)
            except Exception as e:  # noqa: BLE001  加载单个 profile 失败不应阻断其他
                logger.error("加载 profile %s 失败: %s", pid, e)

        # 4. 加载用户绑定
        self._load_bindings()

        logger.info(
            "ProfileManager 初始化完成: %d 个 profile (%s)",
            len(loaded_ids),
            loaded_ids,
        )

    async def _load_profile(
        self, profile_id: str, global_api_keys: dict[str, str]
    ) -> ProfileContext:
        """加载单个 profile：读取 config.yaml → 创建 ProfileContext → initialize"""
        data_dir = self._profiles_dir / profile_id
        config = ProfileConfig.from_yaml(data_dir / "config.yaml")
        ctx = ProfileContext(
            profile_id=profile_id,
            data_dir=data_dir,
            config=config,
        )
        await ctx.initialize(global_api_keys=global_api_keys)
        with self._lock:
            self._profiles[profile_id] = ctx
        return ctx

    async def create_profile(
        self,
        profile_id: str,
        config: ProfileConfig | None = None,
        global_api_keys: dict[str, str] | None = None,
    ) -> ProfileContext:
        """创建新 profile

        Args:
            profile_id: 新 Profile ID（必须匹配 ``[A-Za-z0-9_\\-]{1,64}``）
            config: Profile 配置；为 None 时使用 ``ProfileConfig.default()``
            global_api_keys: 全局 API 密钥表（透传给 ProfileContext.initialize）

        Raises:
            ValueError: profile_id 非法或与现有 profile 冲突
        """
        # 1. 校验 profile_id
        if not profile_id or not _PROFILE_ID_PATTERN.fullmatch(profile_id):
            raise ValueError(
                f"无效的 profile_id: {profile_id!r}，"
                f"仅允许字母、数字、下划线、连字符（1-64 字符）"
            )

        with self._lock:
            if profile_id in self._profiles:
                raise ValueError(f"Profile 已存在: {profile_id}")

        # 2. 创建目录 & 写入 config.yaml
        data_dir = self._profiles_dir / profile_id
        data_dir.mkdir(parents=True, exist_ok=True)
        cfg = config or ProfileConfig.default()
        cfg.to_yaml(data_dir / "config.yaml")

        # 3. 创建 ProfileContext 并初始化（锁外执行 IO / 异步操作）
        ctx = ProfileContext(
            profile_id=profile_id,
            data_dir=data_dir,
            config=cfg,
        )
        await ctx.initialize(global_api_keys=global_api_keys)

        # 4. 加入 _profiles dict
        with self._lock:
            if profile_id in self._profiles:
                # 并发竞态：另一线程已创建同名 profile，回滚
                await ctx.shutdown()
                shutil.rmtree(data_dir, ignore_errors=True)
                raise ValueError(f"Profile 已存在: {profile_id}")
            self._profiles[profile_id] = ctx

        logger.info("Profile 创建成功: %s", profile_id)
        return ctx

    def get_profile(self, profile_id: str | None) -> ProfileContext:
        """获取 profile（None → default）

        Raises:
            KeyError: profile 不存在
        """
        pid = profile_id or self._default_id
        with self._lock:
            if pid not in self._profiles:
                raise KeyError(f"Profile not found: {pid}")
            return self._profiles[pid]

    def get_default(self) -> ProfileContext:
        """获取默认 profile"""
        return self.get_profile(self._default_id)

    async def delete_profile(self, profile_id: str) -> bool:
        """删除 profile（不能删除 default）

        Returns:
            True 表示删除成功，False 表示 profile 不存在

        Raises:
            ValueError: 尝试删除 default profile
        """
        if profile_id == self._default_id:
            raise ValueError("不能删除 default profile")

        # 锁内取出 ctx 并清理 dict / 绑定（短临界区）
        with self._lock:
            ctx = self._profiles.pop(profile_id, None)
            if ctx is None:
                return False
            # 清理指向该 profile 的用户绑定
            orphan_users = [u for u, p in self._user_bindings.items() if p == profile_id]
            for u in orphan_users:
                self._user_bindings.pop(u, None)
            self._save_bindings()

        # 锁外执行 IO / 异步操作（避免长持有锁）
        try:
            await ctx.shutdown()
        except Exception as e:  # noqa: BLE001  删除路径需容错
            logger.warning("删除 profile %s 时 shutdown 失败: %s", profile_id, e)

        shutil.rmtree(ctx.data_dir, ignore_errors=True)
        logger.info("Profile 已删除: %s", profile_id)
        return True

    def list_profiles(self) -> list[dict[str, Any]]:
        """列出所有 profile 信息（按 profile_id 字典序）"""
        with self._lock:
            items = [ctx.snapshot() for ctx in self._profiles.values()]
        items.sort(key=lambda x: x["profile_id"])
        return items

    # ============================================================
    # 用户绑定
    # ============================================================

    def bind_user(self, user_id: str, profile_id: str) -> None:
        """绑定 user_id → profile_id

        Raises:
            KeyError: profile_id 不存在
            ValueError: user_id 为空
        """
        if not user_id:
            raise ValueError("user_id 不能为空")
        with self._lock:
            if profile_id not in self._profiles:
                raise KeyError(f"Profile not found: {profile_id}")
            self._user_bindings[user_id] = profile_id
            self._save_bindings()

    def unbind_user(self, user_id: str) -> bool:
        """解除用户绑定

        Returns:
            True 表示成功解绑，False 表示该用户未绑定
        """
        with self._lock:
            if user_id not in self._user_bindings:
                return False
            self._user_bindings.pop(user_id, None)
            self._save_bindings()
            return True

    def get_user_binding(self, user_id: str) -> str | None:
        """查询用户绑定的 profile_id（未绑定返回 None）"""
        with self._lock:
            return self._user_bindings.get(user_id)

    def resolve_profile(
        self,
        user_id: str | None,
        explicit_id: str | None = None,
    ) -> ProfileContext:
        """解析 profile（优先级：explicit_id > user_id binding > default）

        Raises:
            KeyError: explicit_id 指定但不存在
        """
        with self._lock:
            if explicit_id:
                return self.get_profile(explicit_id)
            if user_id and user_id in self._user_bindings:
                return self.get_profile(self._user_bindings[user_id])
            return self.get_default()

    # ============================================================
    # 关闭
    # ============================================================

    async def shutdown_all(self) -> None:
        """关闭所有 profile（顺序 shutdown，单个失败不阻塞其他）"""
        with self._lock:
            contexts = list(self._profiles.values())

        for ctx in contexts:
            try:
                await ctx.shutdown()
            except Exception as e:  # noqa: BLE001  优雅关闭需容错
                logger.warning("Profile %s shutdown 失败: %s", ctx.profile_id, e)

        with self._lock:
            self._profiles.clear()
            self._user_bindings.clear()

        logger.info("ProfileManager 已关闭所有 profile")

    # ============================================================
    # 绑定持久化
    # ============================================================

    def _save_bindings(self) -> None:
        """保存 user_bindings 到 ``profile_bindings.json``（在锁内调用）"""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._bindings_file.write_text(
                json.dumps(self._user_bindings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:  # noqa: BLE001  持久化失败不应阻断内存状态
            logger.warning("保存 profile_bindings 失败: %s", e)

    def _load_bindings(self) -> None:
        """从 ``profile_bindings.json`` 加载 user_bindings（在锁内调用）"""
        if not self._bindings_file.exists():
            return
        try:
            data = json.loads(self._bindings_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                with self._lock:
                    # 仅保留指向现存 profile 的绑定，避免悬空引用
                    self._user_bindings = {
                        str(k): str(v)
                        for k, v in data.items()
                        if str(v) in self._profiles
                    }
        except Exception as e:  # noqa: BLE001  损坏的 bindings 文件回退到空
            logger.warning("加载 profile_bindings 失败: %s", e)
            with self._lock:
                self._user_bindings = {}

    # ============================================================
    # 内部辅助（供测试 / 调试使用）
    # ============================================================

    @property
    def profiles_dir(self) -> Path:
        """profiles 目录路径"""
        return self._profiles_dir

    @property
    def default_id(self) -> str:
        """默认 profile ID"""
        return self._default_id

    def has_profile(self, profile_id: str) -> bool:
        """是否存在指定 profile"""
        with self._lock:
            return profile_id in self._profiles

    def profile_count(self) -> int:
        """已加载 profile 数量"""
        with self._lock:
            return len(self._profiles)
