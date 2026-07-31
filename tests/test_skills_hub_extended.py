"""
ClawHermes - Federated Skill Hub 扩展测试

覆盖 hub.py 中未被 test_skill_hub.py 覆盖的分支：
- _get_clawhermes_version 异常分支
- SkillManifest.from_dict 类型校验
- search() 异常路径
- install() 多注册表回退 / 指定 registry
- publish() 技能不存在 / git push 路径
- verify() 签名校验
- _install_from() manifest 校验 / 版本检查 / min_clawhermes / 无 manifest 路径
- _fetch_index() git clone / index.json / glob manifest
- _check_min_version() 异常分支
- _is_git_url() 其他 case
- _git_push() init 路径
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawhermes.skills.hub import SkillHub, SkillManifest, _get_clawhermes_version
from clawhermes.skills.manager import SkillManager


def _make_hub(tmpdir: str) -> tuple[SkillHub, SkillManager]:
    """构造一个 SkillHub + SkillManager 实例（隔离临时目录）"""
    sm = SkillManager(Path(tmpdir) / "skills")
    hub = SkillHub(sm, Path(tmpdir))
    return hub, sm


# ============================================================
# _get_clawhermes_version 测试
# ============================================================


class TestGetClawhermesVersion:
    def test_normal_returns_version(self):
        """正常情况下应返回 clawhermes.__version__"""
        v = _get_clawhermes_version()
        # 任何非空字符串都接受（具体版本号随发布变化）
        assert isinstance(v, str)
        assert v != ""

    def test_exception_returns_zero(self):
        """import 失败时返回 '0.0.0' 兜底"""
        with patch.dict("sys.modules", {"clawhermes": None}):
            # 让 from clawhermes import __version__ 抛异常
            import builtins

            orig_import = builtins.__import__

            def _fake_import(name, *args, **kwargs):
                if name == "clawhermes":
                    raise ImportError("simulated")
                return orig_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=_fake_import):
                v = _get_clawhermes_version()
                assert v == "0.0.0"


# ============================================================
# SkillManifest.from_dict 类型校验
# ============================================================


class TestSkillManifestFromDict:
    def test_version_not_int_raises(self):
        """version 字段非 int 应抛 TypeError"""
        with pytest.raises(TypeError, match="version"):
            SkillManifest.from_dict({"name": "x", "version": "1"})

    def test_dependencies_not_list_raises(self):
        """dependencies 字段非 list 应抛 TypeError"""
        with pytest.raises(TypeError, match="dependencies"):
            SkillManifest.from_dict({"name": "x", "dependencies": "not_a_list"})

    def test_from_dict_defaults(self):
        """from_dict 应正确填充默认值"""
        m = SkillManifest.from_dict({"name": "demo"})
        assert m.name == "demo"
        assert m.version == 1
        assert m.license == "MIT"
        assert m.category == "general"
        assert m.dependencies == []
        assert m.min_clawhermes == "0.12.0"


# ============================================================
# search 异常路径
# ============================================================


class TestSearchException:
    def test_search_registry_exception_skipped(self):
        """search 中某 registry _fetch_index 抛异常时应跳过并返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            hub.add_registry("broken", "https://example.com/skills.git")

            with patch.object(hub, "_fetch_index", side_effect=RuntimeError("network fail")):
                results = hub.search("anything")
                assert results == []


# ============================================================
# install 多注册表回退
# ============================================================


class TestInstallMultiRegistry:
    def test_install_iterates_registries_on_success(self):
        """未指定 registry 时应遍历所有 registries，任一成功即返回 True"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            hub.add_registry("r1", "https://example.com/r1.git")
            hub.add_registry("r2", "https://example.com/r2.git")

            with patch.object(hub, "_install_from", return_value=True) as mock_install:
                result = hub.install("demo-skill")
                assert result is True
                mock_install.assert_called_once()

    def test_install_iterates_registries_all_fail(self):
        """所有 registry 都失败时应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            hub.add_registry("r1", "https://example.com/r1.git")
            hub.add_registry("r2", "https://example.com/r2.git")

            with patch.object(hub, "_install_from", side_effect=RuntimeError("fail")):
                result = hub.install("demo-skill")
                assert result is False

    def test_install_with_specific_registry_url(self):
        """指定 registry 时应走 _install_from 路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            hub.add_registry("primary", "https://example.com/primary.git")

            with patch.object(hub, "_install_from", return_value=True) as mock_install:
                result = hub.install("demo-skill", registry="primary")
                assert result is True
                mock_install.assert_called_once()
                args = mock_install.call_args
                assert args[0][1] == "https://example.com/primary.git" or \
                    args.kwargs.get("url") == "https://example.com/primary.git"

    def test_install_with_specific_registry_url_fails(self):
        """指定 registry 时 _install_from 抛异常应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            hub.add_registry("primary", "https://example.com/primary.git")

            with patch.object(hub, "_install_from", side_effect=RuntimeError("boom")):
                result = hub.install("demo-skill", registry="primary")
                assert result is False

    def test_install_registry_not_found_no_registries(self):
        """指定不存在的 registry 且无任何注册表时应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            result = hub.install("demo-skill", registry="nonexistent")
            assert result is False


# ============================================================
# publish 边界
# ============================================================


class TestPublishBoundary:
    def test_publish_skill_not_found(self):
        """publish 不存在的技能应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            result = hub.publish("ghost", "https://example.com/skills.git")
            assert result is False

    def test_publish_to_git_url_triggers_git_push(self):
        """publish 到 git URL 应调用 _git_push"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, sm = _make_hub(tmpdir)
            sm.create("demo", "# Demo", "desc")

            with patch.object(hub, "_git_push", return_value=True) as mock_push, \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub.publish("demo", "git@github.com:org/skills.git")
                assert result is True
                mock_push.assert_called_once()
                # _git_push 第三参数为 content
                call_args = mock_push.call_args
                # 位置参数或关键字参数
                if call_args.args:
                    assert len(call_args.args) >= 3
                    assert call_args.args[2] == "# Demo"
                else:
                    assert call_args.kwargs["content"] == "# Demo"


# ============================================================
# verify 签名校验
# ============================================================


class TestVerifySignature:
    def test_verify_with_signature_rejected(self):
        """manifest 声明了签名但当前未实现签名校验时应拒绝"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            content = "skill content"
            checksum = hashlib.sha256(content.encode()).hexdigest()
            manifest = SkillManifest(name="x", checksum=checksum, signature="fake_sig")
            assert hub.verify(content, manifest) is False

    def test_verify_no_signature_passes(self):
        """无签名的 manifest 仅做 checksum 校验"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            content = "skill content"
            checksum = hashlib.sha256(content.encode()).hexdigest()
            manifest = SkillManifest(name="x", checksum=checksum, signature="")
            assert hub.verify(content, manifest) is True


# ============================================================
# _install_from 完整路径
# ============================================================


class TestInstallFrom:
    def test_install_from_git_url_clone_success(self):
        """git URL 走 git clone 子流程，manifest 完整时安装成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, sm = _make_hub(tmpdir)

            # 准备 manifest + skill 文件（_install_from 在临时目录里读取）
            content = "# Demo Skill\nprint('hi')"

            def _fake_run(cmd, **kwargs):
                # 模拟 git clone：在目标目录写 manifest 和 skill 文件
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                manifest = SkillManifest(
                    name="demo",
                    version=1,
                    description="A demo",
                    checksum=hashlib.sha256(content.encode()).hexdigest(),
                    min_clawhermes="0.1.0",
                )
                (target / "demo.manifest.json").write_text(
                    json.dumps(manifest.to_dict()), encoding="utf-8"
                )
                (target / "demo.md").write_text(content, encoding="utf-8")
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub._install_from("demo", "https://example.com/skills.git")
                assert result is True
                # 技能应被创建到 SkillManager
                assert sm.get("demo") is not None

    def test_install_from_version_mismatch_returns_false(self):
        """manifest 版本不匹配时应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)

            content = "# Demo"

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                manifest = SkillManifest(
                    name="demo",
                    version=2,
                    checksum=hashlib.sha256(content.encode()).hexdigest(),
                )
                (target / "demo.manifest.json").write_text(
                    json.dumps(manifest.to_dict()), encoding="utf-8"
                )
                (target / "demo.md").write_text(content, encoding="utf-8")
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub._install_from("demo", "https://example.com/skills.git", version=1)
                assert result is False

    def test_install_from_min_clawhermes_unmet_returns_false(self):
        """min_clawhermes 不满足时应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            content = "# Demo"

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                manifest = SkillManifest(
                    name="demo",
                    version=1,
                    checksum=hashlib.sha256(content.encode()).hexdigest(),
                    min_clawhermes="999.0.0",  # 远高于当前版本
                )
                (target / "demo.manifest.json").write_text(
                    json.dumps(manifest.to_dict()), encoding="utf-8"
                )
                (target / "demo.md").write_text(content, encoding="utf-8")
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True), \
                    patch("clawhermes.skills.hub._get_clawhermes_version", return_value="0.15.0"):
                result = hub._install_from("demo", "https://example.com/skills.git")
                assert result is False

    def test_install_from_checksum_mismatch_returns_false(self):
        """checksum 校验失败时应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            content = "# Demo"

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                manifest = SkillManifest(
                    name="demo",
                    version=1,
                    checksum="bad_checksum",
                )
                (target / "demo.manifest.json").write_text(
                    json.dumps(manifest.to_dict()), encoding="utf-8"
                )
                (target / "demo.md").write_text(content, encoding="utf-8")
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub._install_from("demo", "https://example.com/skills.git")
                assert result is False

    def test_install_from_no_manifest_allow_unverified(self):
        """无 manifest 但 allow_unverified=True 时应安装"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, sm = _make_hub(tmpdir)

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                (target / "demo.md").write_text("# Unverified", encoding="utf-8")
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub._install_from(
                    "demo", "https://example.com/skills.git", allow_unverified=True
                )
                assert result is True
                assert sm.get("demo") is not None

    def test_install_from_no_manifest_rejected_by_default(self):
        """无 manifest 且未启用 allow_unverified 时应拒绝"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                (target / "demo.md").write_text("# Unverified", encoding="utf-8")
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub._install_from("demo", "https://example.com/skills.git")
                assert result is False

    def test_install_from_no_files_returns_false(self):
        """仓库里既无 manifest 也无 skill 文件时应返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(hub, "_is_git_url", return_value=True):
                result = hub._install_from("ghost", "https://example.com/skills.git")
                assert result is False

    def test_install_from_non_git_url_no_manifest_file(self):
        """非 git URL（不触发 clone）且无 manifest 时返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            # _is_git_url 返回 False 时不会调用 subprocess.run
            with patch.object(hub, "_is_git_url", return_value=False):
                result = hub._install_from("ghost", "https://example.com/skills")
                assert result is False


# ============================================================
# _fetch_index 测试
# ============================================================


class TestFetchIndex:
    def test_fetch_index_with_index_json(self):
        """index.json 存在时应返回 manifest 列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)

            def _fake_run(cmd, **kwargs):
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                manifests = [
                    SkillManifest(name="skill-a", description="A skill").to_dict(),
                    SkillManifest(name="skill-b", description="B skill").to_dict(),
                ]
                (target / "index.json").write_text(
                    json.dumps(manifests), encoding="utf-8"
                )
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                    patch.object(SkillHub, "_is_git_url", return_value=True):
                results = SkillHub._fetch_index("https://example.com/skills.git")
                assert len(results) == 2
                assert results[0].name == "skill-a"

    def test_fetch_index_index_json_not_list_raises(self):
        """index.json 非 list 时应抛 TypeError"""
        # _fetch_index 是静态方法，内部自己创建 TemporaryDirectory
        def _fake_run(cmd, **kwargs):
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / "index.json").write_text(
                json.dumps({"not": "a_list"}), encoding="utf-8"
            )
            return MagicMock(returncode=0)

        with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                patch.object(SkillHub, "_is_git_url", return_value=True):
            with pytest.raises(TypeError, match="index.json"):
                SkillHub._fetch_index("https://example.com/skills.git")

    def test_fetch_index_glob_manifests(self):
        """无 index.json 时应 glob *.manifest.json 文件"""
        def _fake_run(cmd, **kwargs):
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            m1 = SkillManifest(name="a", description="A").to_dict()
            m2 = SkillManifest(name="b", description="B").to_dict()
            (target / "a.manifest.json").write_text(
                json.dumps(m1), encoding="utf-8"
            )
            (target / "b.manifest.json").write_text(
                json.dumps(m2), encoding="utf-8"
            )
            return MagicMock(returncode=0)

        with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                patch.object(SkillHub, "_is_git_url", return_value=True):
            results = SkillHub._fetch_index("https://example.com/skills.git")
            assert len(results) == 2

    def test_fetch_index_glob_manifest_not_dict_raises(self):
        """glob 出的 manifest 文件非 dict 时应抛 TypeError"""
        def _fake_run(cmd, **kwargs):
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / "a.manifest.json").write_text(
                json.dumps(["not", "a", "dict"]), encoding="utf-8"
            )
            return MagicMock(returncode=0)

        with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                patch.object(SkillHub, "_is_git_url", return_value=True):
            with pytest.raises(TypeError, match="manifest"):
                SkillHub._fetch_index("https://example.com/skills.git")

    def test_fetch_index_empty_returns_empty(self):
        """仓库为空时应返回空列表"""
        def _fake_run(cmd, **kwargs):
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0)

        with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run), \
                patch.object(SkillHub, "_is_git_url", return_value=True):
            results = SkillHub._fetch_index("https://example.com/skills.git")
            assert results == []


# ============================================================
# _check_min_version 测试
# ============================================================


class TestCheckMinVersion:
    def test_meets_min_version(self):
        """当前版本 >= min_clawhermes 时应返回 True"""
        m = SkillManifest(name="x", min_clawhermes="0.12.0")
        with patch("clawhermes.skills.hub._get_clawhermes_version", return_value="0.15.0"):
            assert SkillHub._check_min_version(m) is True

    def test_below_min_version(self):
        """当前版本 < min_clawhermes 时应返回 False"""
        m = SkillManifest(name="x", min_clawhermes="1.0.0")
        with patch("clawhermes.skills.hub._get_clawhermes_version", return_value="0.15.0"):
            assert SkillHub._check_min_version(m) is False

    def test_invalid_version_parts_returns_true(self):
        """版本号解析失败时应保守返回 True"""
        m = SkillManifest(name="x", min_clawhermes="not_a_version")
        with patch("clawhermes.skills.hub._get_clawhermes_version", return_value="0.15.0"):
            assert SkillHub._check_min_version(m) is True


# ============================================================
# _is_git_url 其他 case
# ============================================================


class TestIsGitUrl:
    def test_git_protocol(self):
        """git:// 协议应识别为 git URL"""
        assert SkillHub._is_git_url("git://github.com/org/repo") is True

    def test_http_no_git_suffix(self):
        """http:// 不以 .git 结尾应返回 False"""
        assert SkillHub._is_git_url("http://example.com/skills") is False

    def test_https_with_git_suffix(self):
        """https://xxx.git 应识别为 git URL"""
        assert SkillHub._is_git_url("https://github.com/org/repo.git") is True

    def test_ssh_style(self):
        """git@host:path 格式应识别为 git URL"""
        assert SkillHub._is_git_url("git@gitlab.com:team/skills.git") is True

    def test_unknown_scheme(self):
        """未知 scheme 应返回 False"""
        assert SkillHub._is_git_url("ftp://example.com/repo") is False

    def test_empty_string(self):
        """空字符串应返回 False"""
        assert SkillHub._is_git_url("") is False


# ============================================================
# _git_push 测试
# ============================================================


class TestGitPush:
    def test_git_push_clone_success(self):
        """_git_push 在 git clone 成功时应完成 add/commit/push 流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            content = "# Demo"
            manifest = SkillManifest(name="demo", version=1, checksum="abc")

            with patch("clawhermes.skills.hub.subprocess.run", return_value=MagicMock(returncode=0)):
                result = hub._git_push("https://example.com/repo.git", manifest, content)
                assert result is True

    def test_git_push_clone_fails_init_path(self):
        """_git_push 在 clone 失败时应走 git init + remote add 路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub, _ = _make_hub(tmpdir)
            content = "# Demo"
            manifest = SkillManifest(name="demo", version=1, checksum="abc")

            call_count = {"n": 0}

            def _fake_run(cmd, **kwargs):
                call_count["n"] += 1
                # 第一次 clone 失败
                if call_count["n"] == 1:
                    raise __import__("subprocess").CalledProcessError(1, cmd)
                return MagicMock(returncode=0)

            with patch("clawhermes.skills.hub.subprocess.run", side_effect=_fake_run):
                result = hub._git_push("https://example.com/repo.git", manifest, content)
                assert result is True
                # clone 失败 + init + remote add + add + commit + push = 6 次
                assert call_count["n"] == 6


# ============================================================
# SkillHub 初始化
# ============================================================


class TestSkillHubInit:
    def test_init_creates_hub_dir(self):
        """init 时应自动创建 hub_dir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            hub_dir = Path(tmpdir) / "new_hub"
            assert not hub_dir.exists()
            sm = SkillManager(Path(tmpdir) / "skills")
            SkillHub(sm, hub_dir)
            assert hub_dir.exists()

    def test_init_with_str_path(self):
        """init 接受 str 类型路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SkillManager(Path(tmpdir) / "skills")
            hub = SkillHub(sm, tmpdir)
            assert hub._hub_dir == Path(tmpdir)
