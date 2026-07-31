"""Profile 子命令组 — create / list / delete / bind。

通过 ProfileManager 直接操作文件系统与运行时状态，
不依赖 Gateway HTTP API，适合脚本化运维场景。
"""
from __future__ import annotations

import asyncio

import click

from clawhermes.cli import console


def _get_data_dir():
    """获取数据目录路径"""
    from clawhermes.config import get_data_dir

    return get_data_dir()


def _make_profile_manager():
    """构造 ProfileManager 并初始化（含 default 加载）"""
    from clawhermes.profile.manager import ProfileManager

    pm = ProfileManager(_get_data_dir())
    asyncio.run(pm.initialize())
    return pm


def _shutdown(pm) -> None:
    """安全关闭 ProfileManager"""
    try:
        asyncio.run(pm.shutdown_all())
    except Exception as e:  # noqa: BLE001  CLI 关闭需容错
        console.print(f"⚠️  关闭 ProfileManager 时出错: {e}", style="yellow")


@click.group()
def profile():
    """管理 Profile"""
    pass


@profile.command("create")
@click.argument("profile_id")
@click.option("--llm", "llm_provider", default=None, help="LLM 提供商（如 deepseek）")
@click.option("--model", "llm_model", default=None, help="LLM 模型名（如 deepseek-chat）")
@click.option("--tools", "tools_profile", default=None, help="工具分级（minimal/standard/full）")
def profile_create(profile_id, llm_provider, llm_model, tools_profile):
    """创建新 Profile"""
    from clawhermes.profile.config import ProfileConfig

    pm = _make_profile_manager()
    try:
        cfg = ProfileConfig.default()
        if llm_provider is not None:
            cfg.llm_provider = llm_provider
        if llm_model is not None:
            cfg.llm_model = llm_model
        if tools_profile is not None:
            cfg.tools_profile = tools_profile

        asyncio.run(pm.create_profile(profile_id, config=cfg))
        console.print(f"✅ 已创建 Profile: {profile_id}", style="green")
    except ValueError as e:
        console.print(f"❌ {e}", style="red")
    finally:
        _shutdown(pm)


@profile.command("list")
def profile_list():
    """列出所有 Profile"""
    pm = _make_profile_manager()
    try:
        items = pm.list_profiles()
        if not items:
            console.print("（无 Profile）", style="yellow")
            return

        for item in items:
            status = "✅" if item.get("initialized") else "⏸️"
            console.print(
                f"{status} {item['profile_id']:<20} "
                f"model={item.get('llm_model', '-')} "
                f"tools={item.get('tools_profile', '-')}"
            )
    finally:
        _shutdown(pm)


@profile.command("delete")
@click.argument("profile_id")
def profile_delete(profile_id):
    """删除 Profile（不能删除 default）"""
    pm = _make_profile_manager()
    try:
        result = asyncio.run(pm.delete_profile(profile_id))
        if result:
            console.print(f"✅ 已删除 Profile: {profile_id}", style="green")
        else:
            console.print(f"❌ Profile 不存在: {profile_id}", style="red")
    except ValueError as e:
        console.print(f"❌ {e}", style="red")
    finally:
        _shutdown(pm)


@profile.command("bind")
@click.argument("user_id")
@click.argument("profile_id")
def profile_bind(user_id, profile_id):
    """绑定 user_id → profile_id"""
    pm = _make_profile_manager()
    try:
        pm.bind_user(user_id, profile_id)
        console.print(
            f"✅ 已绑定 user_id={user_id} → profile_id={profile_id}", style="green"
        )
    except (ValueError, KeyError) as e:
        console.print(f"❌ {e}", style="red")
    finally:
        _shutdown(pm)
