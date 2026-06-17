"""
ClawHermes - Federated Skill Hub 测试
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from clawhermes.skills.hub import SkillHub, SkillManifest


class TestSkillManifest:
    def test_create_manifest(self):
        m = SkillManifest(name="test-skill", version=2, description="A test skill")
        assert m.name == "test-skill"
        assert m.version == 2
        assert m.description == "A test skill"
        assert m.license == "MIT"

    def test_serialization_roundtrip(self):
        m = SkillManifest(
            name="code-review",
            version=3,
            description="Review code changes",
            author="team",
            dependencies=["git-checkout", "lint-runner"],
        )
        d = m.to_dict()
        restored = SkillManifest.from_dict(d)
        assert restored.name == "code-review"
        assert restored.version == 3
        assert restored.dependencies == ["git-checkout", "lint-runner"]

    def test_checksum_field(self):
        m = SkillManifest(name="test", checksum="abc123")
        assert m.checksum == "abc123"

    def test_min_clawhermes_default(self):
        m = SkillManifest(name="test")
        assert m.min_clawhermes == "0.12.0"


class TestSkillHub:
    def test_add_and_list_registries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            hub.add_registry("community", "https://github.com/org/skills.git")
            hub.add_registry("private", "git@gitlab.com:team/skills.git")

            regs = hub.list_registries()
            assert len(regs) == 2
            assert regs["community"].endswith(".git")

    def test_remove_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            hub.add_registry("temp", "https://example.com/skills.git")
            hub.remove_registry("temp")
            assert len(hub.list_registries()) == 0

    def test_verify_valid_checksum(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            content = "This is a skill"
            import hashlib
            checksum = hashlib.sha256(content.encode()).hexdigest()
            manifest = SkillManifest(name="test", checksum=checksum)
            assert hub.verify(content, manifest) is True

    def test_verify_invalid_checksum(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            manifest = SkillManifest(name="test", checksum="badhash")
            assert hub.verify("content", manifest) is False

    def test_publish_creates_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            hub._sm.create("demo", "# Demo Skill\nprint('hello')", "A demo")

            with patch.object(hub, "_is_git_url", return_value=False):
                result = hub.publish("demo", "https://example.com/skills.git")
                assert result is True

            manifest_path = Path(tmpdir) / "demo.manifest.json"
            assert manifest_path.exists()
            data = json.loads(manifest_path.read_text())
            assert data["name"] == "demo"

    def test_search_mocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            hub.add_registry("test", "https://example.com/skills.git")

            fake_manifest = SkillManifest(
                name="python-linter",
                description="Lint Python code with ruff",
            )
            with patch.object(hub, "_fetch_index", return_value=[fake_manifest]):
                results = hub.search("ruff")
                assert len(results) == 1
                assert results[0].name == "python-linter"

    def test_search_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            hub.add_registry("test", "https://example.com/skills.git")

            with patch.object(hub, "_fetch_index", return_value=[]):
                results = hub.search("nonexistent")
                assert len(results) == 0

    def test_install_no_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = self._make_hub(tmpdir)
            result = hub.install("some-skill")
            assert result is False

    def test_is_git_url(self):
        assert SkillHub._is_git_url("git@github.com:org/repo.git") is True
        assert SkillHub._is_git_url("https://github.com/org/repo.git") is True
        assert SkillHub._is_git_url("https://example.com/skills") is False

    @staticmethod
    def _make_hub(tmpdir: str) -> SkillHub:
        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(Path(tmpdir) / "skills")
        return SkillHub(sm, Path(tmpdir))
