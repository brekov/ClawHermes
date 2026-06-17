"""
ClawHermes - 技能系统（Skills）
技能加载、管理、自进化、Curator 维护
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """一条技能"""
    name: str
    content: str
    description: str = ""
    category: str = "general"
    version: int = 1
    usage_count: int = 0
    last_used: float = 0.0  # timestamp
    created_at: float = 0.0
    status: str = "active"  # active / stale / archived
    source: str = "user"    # user / bundled / review


class SkillManager:
    """技能管理器"""

    def __init__(self, skills_dir: str | Path):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._load_all()

    def _load_all(self):
        """从 skills_dir 加载所有技能"""
        self._skills.clear()
        for f in self.skills_dir.glob("*.md"):
            name = f.stem
            meta_file = f.with_suffix(".json")
            meta = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                except Exception:
                    pass

            self._skills[name] = Skill(
                name=name,
                content=f.read_text(encoding="utf-8"),
                description=meta.get("description", ""),
                category=meta.get("category", "general"),
                version=meta.get("version", 1),
                usage_count=meta.get("usage_count", 0),
                last_used=meta.get("last_used", 0.0),
                created_at=meta.get("created_at", time.time()),
                status=meta.get("status", "active"),
                source=meta.get("source", "user"),
            )

    def _save_meta(self, skill: Skill):
        """保存技能元数据"""
        meta_file = self.skills_dir / f"{skill.name}.json"
        meta_file.write_text(json.dumps({
            "description": skill.description,
            "category": skill.category,
            "version": skill.version,
            "usage_count": skill.usage_count,
            "last_used": skill.last_used,
            "created_at": skill.created_at,
            "status": skill.status,
            "source": skill.source,
        }, indent=2, ensure_ascii=False))

    def list(self, status: str | None = None) -> list[Skill]:
        """列出技能"""
        skills = list(self._skills.values())
        if status:
            skills = [s for s in skills if s.status == status]
        return sorted(skills, key=lambda s: s.usage_count, reverse=True)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def create(self, name: str, content: str, description: str = "", category: str = "general") -> Skill:
        """创建新技能"""
        skill = Skill(
            name=name,
            content=content,
            description=description,
            category=category,
            created_at=time.time(),
            source="user",
        )
        skill_file = self.skills_dir / f"{name}.md"
        skill_file.write_text(content, encoding="utf-8")
        self._save_meta(skill)
        self._skills[name] = skill
        logger.info("技能创建: %s", name)
        return skill

    def update(self, name: str, **kwargs) -> Skill | None:
        """更新技能"""
        skill = self.get(name)
        if not skill:
            return None
        for k, v in kwargs.items():
            if hasattr(skill, k):
                setattr(skill, k, v)
        if "content" in kwargs:
            skill_file = self.skills_dir / f"{name}.md"
            skill_file.write_text(kwargs["content"], encoding="utf-8")
        self._save_meta(skill)
        return skill

    def record_usage(self, name: str):
        """记录技能使用"""
        skill = self.get(name)
        if skill:
            skill.usage_count += 1
            skill.last_used = time.time()
            self._save_meta(skill)

    def get_context(self, active_skills: List[str] | None = None) -> str:
        """生成技能上下文（供 System Prompt 使用）"""
        if active_skills:
            skills = [self._skills[n] for n in active_skills if n in self._skills]
        else:
            skills = [s for s in self._skills.values() if s.status == "active"][:5]

        if not skills:
            return ""

        parts = ["## 可用技能"]
        for s in skills:
            parts.append(f"### {s.name}")
            if s.description:
                parts.append(s.description)
            parts.append(s.content[:500])
        return "\n\n".join(parts)


class BackgroundReview:
    """对话后背景审查 - 自动沉淀记忆和技能（自进化核心）"""

    def __init__(self, llm_provider, memory_manager, skill_manager):
        self.llm = llm_provider
        self.memory = memory_manager
        self.skills = skill_manager

    def review(self, conversation: list[dict]) -> dict:
        """审阅一段对话，返回需要保存的记忆和技能"""
        # 构造审查 prompt
        review_prompt = self._build_review_prompt(conversation)

        try:
            resp = self.llm.chat(
                messages=[{"role": "user", "content": review_prompt}],
            )
            return self._parse_review(resp.content or "")
        except Exception as e:
            logger.warning("Background review failed: %s", e)
            return {"memories": [], "skills": []}

    def _build_review_prompt(self, conversation: list[dict]) -> str:
        lines = []
        for msg in conversation:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"[{role}]: {content[:200]}")
        convo_text = "\n".join(lines)

        return f"""Review this conversation and decide what to remember and what skills to create/update.

Conversation:
{convo_text}

Output format (JSON only):
{{
  "memories": [{{"content": "...", "importance": 0.8}}],
  "skills": [{{"name": "...", "description": "...", "content": "..."}}]
}}

Rules:
- Only save memories that are user preferences, facts, or important context
- Only create skills if the conversation reveals a reusable workflow or pattern
- Be conservative - don't save trivial information"""

    def _parse_review(self, text: str) -> dict:
        """解析 LLM 返回的审查结果"""
        import json
        # 提取 JSON
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                assert isinstance(result, dict)
                return result
            except json.JSONDecodeError:
                pass
        return {"memories": [], "skills": []}

    def apply(self, conversation: list[dict]):
        """审查并应用结果"""
        result = self.review(conversation)
        for m in result.get("memories", []):
            self.memory.save(
                content=m["content"],
                importance=m.get("importance", 0.5),
            )
            logger.info("背景审查 → 新记忆: %s", m["content"][:60])
        for s in result.get("skills", []):
            existing = self.skills.get(s["name"])
            if existing:
                self.skills.update(s["name"], usage_count=existing.usage_count + 1)
                logger.info("背景审查 → 技能更新: %s", s["name"])
            else:
                self.skills.create(
                    name=s["name"],
                    content=s.get("content", s.get("description", "")),
                    description=s.get("description", ""),
                )
                logger.info("背景审查 → 新技能: %s", s["name"])


class Curator:
    """技能库维护员 - 定期清理和归档"""

    def __init__(self, skill_manager: SkillManager):
        self.skills = skill_manager
        self.stale_days = 30
        self.archive_days = 90

    def run(self, dry_run: bool = False) -> dict:
        """执行一轮维护"""
        now = time.time()
        stats = {"stale": 0, "archived": 0, "active": 0}

        for skill in self.skills.list():
            if skill.source in ("bundled",):
                continue  # 不碰内置技能

            days_since_used = (now - skill.last_used) / 86400 if skill.last_used > 0 else 999

            if days_since_used > self.archive_days and skill.status != "archived":
                if not dry_run:
                    self.skills.update(skill.name, status="archived")
                stats["archived"] += 1
                logger.info("Curator 归档技能: %s (%d 天未用)", skill.name, days_since_used)

            elif days_since_used > self.stale_days and skill.status == "active":
                if not dry_run:
                    self.skills.update(skill.name, status="stale")
                stats["stale"] += 1
                logger.info("Curator 标记 stale: %s (%d 天未用)", skill.name, days_since_used)

            else:
                stats["active"] += 1

        return stats
