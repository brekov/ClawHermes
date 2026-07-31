"""
ClawHermes - SkillManager / BackgroundReview / Curator 扩展测试

覆盖 manager.py 中未被 test_unit_extended.py 覆盖的分支：
- _load_all() JSON 元数据损坏路径
- update() 技能不存在
- record_usage() 完整流程
- get_context() with/without active_skills
- BackgroundReview.review() 异常路径
- BackgroundReview.apply() 完整流程（更新已有技能 + 创建新技能 + memory 保存）
- Curator.run() 非 dry_run + bundled 跳过 + archive 路径
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

from clawhermes.skills.manager import BackgroundReview, Curator, SkillManager

# ============================================================
# _load_all 异常路径
# ============================================================


class TestLoadAllException:
    def test_load_all_skips_malformed_meta(self, tmp_path):
        """meta 文件 JSON 损坏时应记录 warning 并跳过该 meta，技能仍可加载"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # 写一个技能 md 文件
        (skills_dir / "demo.md").write_text("# Demo", encoding="utf-8")
        # 写一个损坏的 .json meta 文件
        (skills_dir / "demo.json").write_text("{invalid json", encoding="utf-8")

        sm = SkillManager(skills_dir)
        # 触发懒加载
        skill = sm.get("demo")
        assert skill is not None
        assert skill.content == "# Demo"
        # 损坏 meta 时使用默认值
        assert skill.description == ""

    def test_load_all_with_valid_meta(self, tmp_path):
        """有效的 meta 文件应被正确加载"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "demo.md").write_text("# Demo", encoding="utf-8")
        meta = {
            "description": "A demo skill",
            "category": "test",
            "version": 3,
            "usage_count": 5,
            "last_used": 1000.0,
            "created_at": 500.0,
            "status": "stale",
            "source": "user",
        }
        (skills_dir / "demo.json").write_text(json.dumps(meta), encoding="utf-8")

        sm = SkillManager(skills_dir)
        skill = sm.get("demo")
        assert skill is not None
        assert skill.description == "A demo skill"
        assert skill.version == 3
        assert skill.usage_count == 5
        assert skill.status == "stale"


# ============================================================
# update 边界
# ============================================================


class TestUpdateBoundary:
    def test_update_nonexistent_returns_none(self, tmp_path):
        """update 不存在的技能应返回 None"""
        sm = SkillManager(tmp_path)
        result = sm.update("ghost", content="new")
        assert result is None

    def test_update_multiple_fields(self, tmp_path):
        """update 应支持同时更新多个字段"""
        sm = SkillManager(tmp_path)
        sm.create("demo", "orig", "desc")
        result = sm.update(
            "demo",
            content="new content",
            description="new desc",
            category="new_cat",
            version=2,
            usage_count=10,
            status="stale",
        )
        assert result is not None
        assert result.content == "new content"
        assert result.description == "new desc"
        assert result.category == "new_cat"
        assert result.version == 2
        assert result.usage_count == 10
        assert result.status == "stale"

        # 验证持久化（重新创建 SkillManager 实例加载）
        sm2 = SkillManager(tmp_path)
        reloaded = sm2.get("demo")
        assert reloaded is not None
        assert reloaded.content == "new content"
        assert reloaded.description == "new desc"


# ============================================================
# record_usage 完整流程
# ============================================================


class TestRecordUsage:
    def test_record_usage_increments_count(self, tmp_path):
        """record_usage 应增加 usage_count 并更新 last_used"""
        sm = SkillManager(tmp_path)
        sm.create("demo", "content", "desc")
        original_last_used = sm.get("demo").last_used

        time.sleep(0.01)  # 确保 last_used 变化
        sm.record_usage("demo")

        skill = sm.get("demo")
        assert skill.usage_count == 1
        assert skill.last_used > original_last_used

        sm.record_usage("demo")
        sm.record_usage("demo")
        assert sm.get("demo").usage_count == 3

    def test_record_usage_nonexistent_no_error(self, tmp_path):
        """record_usage 不存在的技能不应抛异常"""
        sm = SkillManager(tmp_path)
        # 不抛异常即可
        sm.record_usage("ghost")


# ============================================================
# get_context
# ============================================================


class TestGetContext:
    def test_get_context_no_skills_returns_empty(self, tmp_path):
        """无技能时应返回空字符串"""
        sm = SkillManager(tmp_path)
        assert sm.get_context() == ""

    def test_get_context_default_active(self, tmp_path):
        """无 active_skills 参数时应返回前 5 个 active 技能"""
        sm = SkillManager(tmp_path)
        for i in range(7):
            sm.create(f"skill_{i}", f"content_{i}", f"desc_{i}")
        ctx = sm.get_context()
        assert "## 可用技能" in ctx
        # 前 5 个技能都应在上下文中
        for i in range(5):
            assert f"skill_{i}" in ctx

    def test_get_context_with_active_skills(self, tmp_path):
        """指定 active_skills 时应只返回指定技能"""
        sm = SkillManager(tmp_path)
        sm.create("skill_a", "content_a", "desc_a")
        sm.create("skill_b", "content_b", "desc_b")
        sm.create("skill_c", "content_c", "desc_c")

        ctx = sm.get_context(active_skills=["skill_a", "skill_c"])
        assert "skill_a" in ctx
        assert "skill_c" in ctx
        assert "skill_b" not in ctx

    def test_get_context_active_skills_with_missing(self, tmp_path):
        """active_skills 中包含不存在技能时应跳过"""
        sm = SkillManager(tmp_path)
        sm.create("real_skill", "real content", "real desc")
        ctx = sm.get_context(active_skills=["real_skill", "ghost"])
        assert "real_skill" in ctx

    def test_get_context_truncates_long_content(self, tmp_path):
        """技能内容超过 500 字符时应被截断"""
        sm = SkillManager(tmp_path)
        long_content = "x" * 1000
        sm.create("long_skill", long_content, "desc")
        ctx = sm.get_context()
        # 上下文中应包含前 500 字符
        assert "x" * 500 in ctx
        # 不应包含完整的 1000 字符
        assert "x" * 1000 not in ctx

    def test_get_context_no_description_omitted(self, tmp_path):
        """无描述的技能应只显示名称和内容"""
        sm = SkillManager(tmp_path)
        sm.create("nodesc", "content", "")
        ctx = sm.get_context()
        assert "nodesc" in ctx
        assert "content" in ctx

    def test_get_context_stale_skills_excluded_by_default(self, tmp_path):
        """stale 状态的技能默认不应出现在上下文中"""
        sm = SkillManager(tmp_path)
        sm.create("active_skill", "active content", "active desc")
        sm.create("stale_skill", "stale content", "stale desc")
        sm.update("stale_skill", status="stale")
        ctx = sm.get_context()
        assert "active_skill" in ctx
        assert "stale_skill" not in ctx


# ============================================================
# BackgroundReview.review 异常路径
# ============================================================


class TestBackgroundReviewReviewException:
    def test_review_llm_exception_returns_empty(self, tmp_path):
        """review() 在 LLM 抛异常时应返回空 memories/skills"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.side_effect = RuntimeError("LLM down")
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        result = br.review([{"role": "user", "content": "hi"}])
        assert result == {"memories": [], "skills": []}

    def test_review_success_returns_parsed(self, tmp_path):
        """review() 在 LLM 返回有效 JSON 时应返回解析结果"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [{"content": "fact", "importance": 0.9}], '
                    '"skills": [{"name": "s1", "description": "d1"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        result = br.review([{"role": "user", "content": "hi"}])
        assert len(result["memories"]) == 1
        assert result["memories"][0]["content"] == "fact"
        assert len(result["skills"]) == 1


# ============================================================
# BackgroundReview.apply 完整流程
# ============================================================


class TestBackgroundReviewApply:
    def test_apply_creates_new_skill_and_memory(self, tmp_path):
        """apply() 应创建新技能并保存 memory"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [{"content": "user likes Python", "importance": 0.9}], '
                    '"skills": [{"name": "new_skill", "description": "A new skill", '
                    '"content": "skill content"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "I like Python"}])

        # 技能应被创建
        skill = sm.get("new_skill")
        assert skill is not None
        assert skill.content == "skill content"
        assert skill.description == "A new skill"

        # memory 应被保存
        results = memory.search("Python")
        assert len(results) >= 1

    def test_apply_updates_existing_skill(self, tmp_path):
        """apply() 对已存在的技能应更新内容并增加 usage_count"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [], "skills": [{"name": "existing", '
                    '"description": "updated desc", "content": "updated content"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)
        sm.create("existing", "original content", "original desc")
        sm.record_usage("existing")
        original_count = sm.get("existing").usage_count

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "hi"}])

        skill = sm.get("existing")
        assert skill is not None
        assert skill.content == "updated content"
        assert skill.description == "updated desc"
        # usage_count 应增加 1
        assert skill.usage_count == original_count + 1

    def test_apply_memory_missing_content_skipped(self, tmp_path):
        """apply() 中 memory 项缺失 content 字段应跳过该项"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [{"importance": 0.5}, {"content": "valid"}], "skills": []}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "hi"}])

        # 只有 valid memory 应被保存
        results = memory.search("valid")
        assert len(results) >= 1

    def test_apply_memory_with_non_dict_skipped(self, tmp_path):
        """apply() 中 memory 项非 dict（如 None）应跳过"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [null, "string_item", {"content": "valid"}], "skills": []}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        # 不抛异常即可
        br.apply([{"role": "user", "content": "hi"}])
        results = memory.search("valid")
        assert len(results) >= 1

    def test_apply_skill_missing_name_skipped(self, tmp_path):
        """apply() 中 skill 项缺失 name 字段应跳过"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [], "skills": [{"description": "no name"}, '
                    '{"name": "valid_skill", "content": "c"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "hi"}])

        assert sm.get("valid_skill") is not None
        # 未命名的 skill 不应被创建
        assert len(sm.list()) == 1

    def test_apply_skill_with_non_dict_skipped(self, tmp_path):
        """apply() 中 skill 项非 dict（如 None）应跳过"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [], "skills": [null, "string", '
                    '{"name": "valid", "content": "c"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "hi"}])
        assert sm.get("valid") is not None
        assert len(sm.list()) == 1

    def test_apply_existing_skill_only_count_increment(self, tmp_path):
        """apply() 中已有技能且无新 content/description 时应只增加 usage_count"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [], "skills": [{"name": "existing"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)
        sm.create("existing", "orig content", "orig desc")
        sm.record_usage("existing")
        sm.record_usage("existing")
        original_count = sm.get("existing").usage_count
        original_content = sm.get("existing").content

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "hi"}])

        skill = sm.get("existing")
        assert skill.usage_count == original_count + 1
        # content 和 description 不变
        assert skill.content == original_content

    def test_apply_new_skill_uses_description_as_content(self, tmp_path):
        """apply() 创建新技能时若无 content 应使用 description 作为 content"""
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content='{"memories": [], "skills": [{"name": "desc_only", '
                    '"description": "use this as content"}]}'
        )
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        br.apply([{"role": "user", "content": "hi"}])

        skill = sm.get("desc_only")
        assert skill is not None
        # 既无 content 又无 description 时为空字符串
        # 这里给了 description，所以 content 应是 description
        assert skill.content == "use this as content"


# ============================================================
# Curator.run 非 dry_run 完整流程
# ============================================================


class TestCuratorRunFull:
    def test_curator_bundled_skill_skipped(self, tmp_path):
        """bundled 技能应被 Curator 跳过"""
        sm = SkillManager(tmp_path)
        sm.create("bundled_skill", "content", "desc")
        sm.update("bundled_skill", source="bundled", last_used=0)

        curator = Curator(sm)
        stats = curator.run(dry_run=False)
        # bundled 不进入任何分支
        assert stats["active"] == 0
        assert stats["stale"] == 0
        assert stats["archived"] == 0

    def test_curator_archives_old_skill(self, tmp_path):
        """90+ 天未使用的非 active 技能应被归档（非 dry_run）"""
        sm = SkillManager(tmp_path)
        sm.create("ancient", "content", "desc")
        # last_used = 0 → days_since_used = 999 > archive_days(90)
        sm.update("ancient", last_used=0, status="active")

        curator = Curator(sm)
        stats = curator.run(dry_run=False)
        assert stats["archived"] >= 1
        skill = sm.get("ancient")
        assert skill is not None
        assert skill.status == "archived"

    def test_curator_marks_stale(self, tmp_path):
        """30+ 天未使用的 active 技能应被标记为 stale（非 dry_run）"""
        sm = SkillManager(tmp_path)
        sm.create("aging", "content", "desc")
        # 40 天前使用过
        sm.update("aging", last_used=time.time() - 40 * 86400, status="active")

        curator = Curator(sm)
        stats = curator.run(dry_run=False)
        assert stats["stale"] >= 1
        skill = sm.get("aging")
        assert skill is not None
        assert skill.status == "stale"

    def test_curator_keeps_recent_active(self, tmp_path):
        """最近使用过的 active 技能应保持 active"""
        sm = SkillManager(tmp_path)
        sm.create("fresh", "content", "desc")
        sm.update("fresh", last_used=time.time(), status="active")

        curator = Curator(sm)
        stats = curator.run(dry_run=False)
        assert stats["active"] >= 1
        skill = sm.get("fresh")
        assert skill is not None
        assert skill.status == "active"

    def test_curator_already_archived_skipped(self, tmp_path):
        """已 archived 的技能不应重复归档"""
        sm = SkillManager(tmp_path)
        sm.create("already_archived", "content", "desc")
        sm.update("already_archived", last_used=0, status="archived")

        curator = Curator(sm)
        stats = curator.run(dry_run=False)
        # 已 archived 应进入 active 分支（days_since_used > 90 but status == archived）
        # 不会再次 archive
        assert stats["archived"] == 0
        # days_since_used > 90 but status == archived, 走 else 分支 active+1
        # (因为 elif 的条件是 status == active)
        assert stats["active"] >= 1

    def test_curator_stale_skill_not_remarked(self, tmp_path):
        """已 stale 的技能不应被重新标记（elif 条件要求 status == active）"""
        sm = SkillManager(tmp_path)
        sm.create("already_stale", "content", "desc")
        sm.update("already_stale", last_used=time.time() - 40 * 86400, status="stale")

        curator = Curator(sm)
        stats = curator.run(dry_run=False)
        # stale 状态不会被再次标记
        assert stats["stale"] == 0
        # 进入 else 分支 active+1
        assert stats["active"] >= 1
