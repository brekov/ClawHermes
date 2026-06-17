"""
ClawHermes - Federated Skill Hub
基于 Git 的联邦技能中心：发布、发现、安装、验证技能
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from clawhermes.skills.manager import SkillManager


@dataclass
class SkillManifest:
    """技能清单 — 描述一个技能的元数据"""
    name: str
    version: int = 1
    description: str = ""
    author: str = ""
    license: str = "MIT"
    category: str = "general"
    dependencies: list[str] = field(default_factory=list)
    min_clawhermes: str = "0.12.0"
    checksum: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "category": self.category,
            "dependencies": self.dependencies,
            "min_clawhermes": self.min_clawhermes,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> SkillManifest:
        version_raw = d.get("version", 1)
        assert isinstance(version_raw, int)
        deps_raw = d.get("dependencies", [])
        assert isinstance(deps_raw, list)
        return cls(
            name=str(d.get("name", "")),
            version=version_raw,
            description=str(d.get("description", "")),
            author=str(d.get("author", "")),
            license=str(d.get("license", "MIT")),
            category=str(d.get("category", "general")),
            dependencies=deps_raw,
            min_clawhermes=str(d.get("min_clawhermes", "0.12.0")),
            checksum=str(d.get("checksum", "")),
            created_at=str(d.get("created_at", "")),
            signature=str(d.get("signature", "")),
        )


class SkillHub:
    """联邦技能中心"""

    def __init__(self, skill_manager: SkillManager, hub_dir: str | Path):
        self._sm = skill_manager
        self._hub_dir = Path(hub_dir)
        self._hub_dir.mkdir(parents=True, exist_ok=True)
        self._registries: dict[str, str] = {}

    def add_registry(self, name: str, url: str) -> None:
        """注册一个远程技能仓库"""
        self._registries[name] = url
        logger.info("Registry added: %s -> %s", name, url)

    def remove_registry(self, name: str) -> None:
        self._registries.pop(name, None)

    def list_registries(self) -> dict[str, str]:
        return dict(self._registries)

    def search(self, query: str) -> list[SkillManifest]:
        """搜索远程技能仓库"""
        results: list[SkillManifest] = []
        for registry_name, url in self._registries.items():
            try:
                manifests = self._fetch_index(url)
                for m in manifests:
                    if query.lower() in m.name.lower() or query.lower() in m.description.lower():
                        results.append(m)
            except Exception as e:
                logger.warning("Search failed for registry %s: %s", registry_name, e)
        return results

    def install(self, name: str, registry: str = "", version: int | None = None) -> bool:
        """从远程仓库安装技能"""
        url = self._registries.get(registry, "") if registry else ""
        if not url and self._registries:
            for reg_name, reg_url in self._registries.items():
                try:
                    return self._install_from(name, reg_url, version)
                except Exception as e:
                    logger.debug("Failed from %s: %s", reg_name, e)
            logger.error("Skill '%s' not found in any registry", name)
            return False
        elif url:
            try:
                return self._install_from(name, url, version)
            except Exception as e:
                logger.error("Install failed: %s", e)
                return False
        return False

    def publish(self, name: str, registry_url: str) -> bool:
        """发布本地技能到远程仓库"""
        skill = self._sm.get(name)
        if not skill:
            logger.error("Skill not found locally: %s", name)
            return False

        content = skill.content
        checksum = hashlib.sha256(content.encode()).hexdigest()

        manifest = SkillManifest(
            name=name,
            version=skill.version,
            description=skill.description,
            category=skill.category,
            checksum=checksum,
        )

        manifest_path = self._hub_dir / f"{name}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if self._is_git_url(registry_url):
            return self._git_push(registry_url, manifest, content)

        logger.info("Skill published: %s (v%d, sha256=%s)", name, manifest.version, checksum[:12])
        return True

    def verify(self, content: str, manifest: SkillManifest) -> bool:
        """验证技能完整性"""
        actual = hashlib.sha256(content.encode()).hexdigest()
        return actual == manifest.checksum

    def _install_from(self, name: str, url: str, version: int | None = None) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            if self._is_git_url(url):
                subprocess.run(
                    ["git", "clone", "--depth=1", url, str(tmp)],
                    capture_output=True, timeout=60, check=True,
                )

            manifest_path = tmp / f"{name}.manifest.json"
            skill_path = tmp / f"{name}.md"

            if manifest_path.exists():
                manifest = SkillManifest.from_dict(
                    json.loads(manifest_path.read_text(encoding="utf-8"))
                )
                if version and manifest.version != version:
                    return False

                if skill_path.exists():
                    content = skill_path.read_text(encoding="utf-8")
                    if not self.verify(content, manifest):
                        logger.error("Checksum verification failed for %s", name)
                        return False

                    self._sm.create(
                        name=name,
                        content=content,
                        description=manifest.description,
                        category=manifest.category,
                    )
                    logger.info("Skill installed: %s (v%d)", name, manifest.version)
                    return True

            if skill_path.exists():
                content = skill_path.read_text(encoding="utf-8")
                self._sm.create(name=name, content=content)
                logger.info("Skill installed (no manifest): %s", name)
                return True

            return False

    @staticmethod
    def _fetch_index(url: str) -> list[SkillManifest]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            if SkillHub._is_git_url(url):
                subprocess.run(
                    ["git", "clone", "--depth=1", url, str(tmp)],
                    capture_output=True, timeout=30, check=True,
                )
            index = tmp / "index.json"
            if index.exists():
                data = json.loads(index.read_text(encoding="utf-8"))
                assert isinstance(data, list)
                return [SkillManifest.from_dict(item) for item in data]

            manifests: list[SkillManifest] = []
            for f in sorted(tmp.glob("*.manifest.json")):
                data = json.loads(f.read_text(encoding="utf-8"))
                assert isinstance(data, dict)
                manifests.append(SkillManifest.from_dict(data))
            return manifests

    @staticmethod
    def _is_git_url(url: str) -> bool:
        return url.startswith("git@") or url.startswith("https://") and ".git" in url

    def _git_push(self, repo_url: str, manifest: SkillManifest, content: str) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            try:
                subprocess.run(
                    ["git", "clone", repo_url, str(tmp)],
                    capture_output=True, timeout=60, check=True,
                )
            except subprocess.CalledProcessError:
                subprocess.run(
                    ["git", "init", str(tmp)],
                    capture_output=True, check=True,
                )
                subprocess.run(
                    ["git", "-C", str(tmp), "remote", "add", "origin", repo_url],
                    capture_output=True, check=True,
                )

            (tmp / f"{manifest.name}.manifest.json").write_text(
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (tmp / f"{manifest.name}.md").write_text(content, encoding="utf-8")

            subprocess.run(
                ["git", "-C", str(tmp), "add", "."],
                capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "-C", str(tmp), "commit", "-m", f"Publish {manifest.name} v{manifest.version}"],
                capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "-C", str(tmp), "push", "origin", "main"],
                capture_output=True, timeout=60, check=True,
            )
            return True
