"""
Gateway Setup 模块测试。

覆盖:
- Token 生成与持久化
- 服务状态检查
- CLI gateway 子命令
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from clawhermes.cli import main


@pytest.fixture(autouse=True)
def _prevent_network(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-mock")
    monkeypatch.setenv("CH_DATA_DIR", os.path.join(os.getcwd(), ".test_gw_tmp"))


class TestGatewayToken:
    def test_generate_token_format(self):
        from clawhermes.gateway.setup import generate_gateway_token
        token = generate_gateway_token()
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_generate_token_unique(self):
        from clawhermes.gateway.setup import generate_gateway_token
        t1 = generate_gateway_token()
        t2 = generate_gateway_token()
        assert t1 != t2

    def test_token_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.gateway.setup import ensure_gateway_token, read_gateway_token
        token = ensure_gateway_token()
        assert token is not None
        assert len(token) == 64
        token2 = read_gateway_token()
        assert token2 == token

    def test_read_nonexistent_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.gateway.setup import read_gateway_token
        assert read_gateway_token() is None


class TestGatewayServiceStatus:
    def test_status_returns_dict(self):
        from clawhermes.gateway.setup import check_gateway_service_status
        st = check_gateway_service_status()
        assert isinstance(st, dict)
        assert "installed" in st
        assert "running" in st
        assert "platform" in st
        assert "token_configured" in st

    def test_install_on_unsupported_platform(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "SunOS")
        from clawhermes.gateway.setup import install_gateway_service
        result = install_gateway_service()
        assert result is False

    def test_uninstall_on_unsupported_platform(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "SunOS")
        from clawhermes.gateway.setup import uninstall_gateway_service
        result = uninstall_gateway_service()
        assert result is False


class TestGatewayCLI:
    def test_gateway_setup_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["gateway", "setup", "--help"])
        assert result.exit_code == 0

    def test_gateway_status(self):
        runner = CliRunner()
        result = runner.invoke(main, ["gateway", "status"])
        assert result.exit_code == 0
        assert "platform" in result.output

    def test_gateway_setup(self):
        runner = CliRunner()
        result = runner.invoke(main, ["gateway", "setup", "--host", "0.0.0.0"])  # noqa: S104  公网监听测试
        # Should not crash on macOS without launchctl
        assert result.exit_code in (0, 1)

    def test_gateway_uninstall(self):
        runner = CliRunner()
        result = runner.invoke(main, ["gateway", "uninstall"])
        assert result.exit_code in (0, 1)


# ============================================================
# systemd (Linux) 安装/卸载/状态测试 — 通过 mock platform.system 模拟
# ============================================================


class TestSystemdService:
    """覆盖 install_systemd_service / uninstall_gateway_service / check_gateway_service_status 的 Linux 分支"""

    def test_install_systemd_localhost_no_secret_env(self, tmp_path, monkeypatch):
        """Linux 上安装 systemd 服务（监听 127.0.0.1）不应包含 CH_GATEWAY_SECRET"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("os.environ", {**os.environ, "USER": "testuser"})

        from clawhermes.gateway import setup
        # mock subprocess.run 避免真实调用 systemctl
        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            # mock Path.home() 到 tmp_path 避免污染真实家目录
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_systemd_service(host="127.0.0.1", port=18789)
            assert result is True

        # 验证 unit 文件已写入
        unit_path = tmp_path / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
        assert unit_path.exists()
        content = unit_path.read_text()
        # localhost 不应有 CH_GATEWAY_SECRET
        assert "CH_GATEWAY_SECRET" not in content
        assert "CH_DATA_DIR" in content

    def test_install_systemd_public_host_with_secret(self, tmp_path, monkeypatch):
        """Linux 上安装 systemd 服务（监听 0.0.0.0）应包含 CH_GATEWAY_SECRET"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Linux")

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_systemd_service(host="0.0.0.0", port=18789)  # noqa: S104  公网监听测试
            assert result is True

        unit_path = tmp_path / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
        content = unit_path.read_text()
        # 公网监听应有 CH_GATEWAY_SECRET
        assert "CH_GATEWAY_SECRET" in content

    def test_install_systemd_subprocess_failure(self, tmp_path, monkeypatch):
        """systemctl 调用失败（CalledProcessError）应返回 False"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Linux")

        import subprocess as sp

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(sp.CalledProcessError(1, [])),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_systemd_service(host="127.0.0.1")
            assert result is False

    def test_install_systemd_systemctl_missing(self, tmp_path, monkeypatch):
        """systemctl 不可用（FileNotFoundError）应返回 False"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Linux")

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("no systemctl")),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_systemd_service(host="127.0.0.1")
            assert result is False

    def test_install_systemd_explicit_user(self, tmp_path, monkeypatch):
        """显式传入 user 参数时应使用该 user"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Linux")

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_systemd_service(host="127.0.0.1", user="customuser")
            assert result is True

        unit_path = tmp_path / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
        content = unit_path.read_text()
        assert "customuser" in content

    def test_install_gateway_service_linux_dispatch(self, tmp_path, monkeypatch):
        """install_gateway_service 在 Linux 上应调用 install_systemd_service"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        from clawhermes.gateway import setup
        with patch.object(setup, "install_systemd_service", return_value=True) as mock_install:
            result = setup.install_gateway_service(host="127.0.0.1", port=18789, user="u")
            assert result is True
            mock_install.assert_called_once()

    def test_uninstall_systemd_success(self, tmp_path, monkeypatch):
        """Linux 卸载 systemd 服务成功路径"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        from clawhermes.gateway import setup

        unit_path = tmp_path / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text("dummy")

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.uninstall_gateway_service()
            assert result is True
            # unit 文件应被删除
            assert not unit_path.exists()

    def test_uninstall_systemd_subprocess_failure(self, tmp_path, monkeypatch):
        """Linux 卸载时 systemctl 失败应返回 False"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        import subprocess as sp

        from clawhermes.gateway import setup

        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(sp.CalledProcessError(1, [])),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.uninstall_gateway_service()
            assert result is False

    def test_uninstall_systemd_systemctl_missing(self, tmp_path, monkeypatch):
        """Linux 卸载时 systemctl 不可用应返回 False"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        from clawhermes.gateway import setup

        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("no systemctl")),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.uninstall_gateway_service()
            assert result is False

    def test_check_status_linux_active(self, tmp_path, monkeypatch):
        """Linux 上 systemctl is-active 返回 active 时 running=True"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        from clawhermes.gateway import setup

        unit_path = tmp_path / ".config" / "systemd" / "user" / "clawhermes-gateway.service"
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text("dummy")

        def _fake_run(cmd, **kw):
            m = MagicMock()
            if "is-active" in cmd:
                m.stdout = "active\n"
                m.returncode = 0
            else:
                m.returncode = 0
            return m

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", _fake_run)
            m.setattr(Path, "home", lambda: tmp_path)
            status = setup.check_gateway_service_status()
            assert status["installed"] is True
            assert status["running"] is True
            assert status["platform"] == "Linux"

    def test_check_status_linux_subprocess_error(self, tmp_path, monkeypatch):
        """Linux 上 systemctl 调用异常时不应抛错，running=False"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        import subprocess as sp

        from clawhermes.gateway import setup

        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(sp.CalledProcessError(1, [])),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            status = setup.check_gateway_service_status()
            assert status["installed"] is False
            assert status["running"] is False


# ============================================================
# launchd (macOS) 安装/卸载/状态测试
# ============================================================


class TestLaunchdService:
    """覆盖 install_launchd_service / uninstall_gateway_service / check_gateway_service_status 的 macOS 分支"""

    def test_install_launchd_localhost(self, tmp_path, monkeypatch):
        """macOS 上安装 launchd 服务（监听 127.0.0.1）不应包含 secret"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Darwin")

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_launchd_service(host="127.0.0.1", port=18789)
            assert result is True

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        assert plist_path.exists()
        content = plist_path.read_text()
        assert "CH_GATEWAY_SECRET" not in content
        assert "CH_DATA_DIR" in content

    def test_install_launchd_public_host_with_secret(self, tmp_path, monkeypatch):
        """macOS 上安装 launchd 服务（监听 0.0.0.0）应包含 secret"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Darwin")

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_launchd_service(host="0.0.0.0", port=18789)  # noqa: S104  公网监听测试
            assert result is True

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        content = plist_path.read_text()
        assert "CH_GATEWAY_SECRET" in content

    def test_install_launchd_load_failure(self, tmp_path, monkeypatch):
        """launchctl load 失败应返回 False"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Darwin")

        import subprocess as sp

        from clawhermes.gateway import setup

        call_count = {"n": 0}

        def _fake_run(cmd, **kw):
            call_count["n"] += 1
            # 第一次是 unload（不检查返回码），第二次是 load（检查）
            if call_count["n"] == 2:
                raise sp.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", _fake_run)
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_launchd_service(host="127.0.0.1")
            assert result is False

    def test_install_launchd_launchctl_missing(self, tmp_path, monkeypatch):
        """launchctl 不可用（FileNotFoundError）应返回 False"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("platform.system", lambda: "Darwin")

        from clawhermes.gateway import setup
        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("no launchctl")),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.install_launchd_service(host="127.0.0.1")
            assert result is False

    def test_install_launchd_wrong_platform(self, monkeypatch):
        """非 macOS 平台调用 install_launchd_service 应返回 False"""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        from clawhermes.gateway import setup
        result = setup.install_launchd_service()
        assert result is False

    def test_install_gateway_service_darwin_dispatch(self, monkeypatch):
        """install_gateway_service 在 Darwin 上应调用 install_launchd_service"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        from clawhermes.gateway import setup
        with patch.object(setup, "install_launchd_service", return_value=True) as mock_install:
            result = setup.install_gateway_service(host="127.0.0.1", port=18789)
            assert result is True
            mock_install.assert_called_once()

    def test_uninstall_launchd_success(self, tmp_path, monkeypatch):
        """macOS 卸载 launchd 服务成功路径"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        from clawhermes.gateway import setup

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text("dummy")

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.uninstall_gateway_service()
            assert result is True
            # plist 文件应被删除
            assert not plist_path.exists()

    def test_uninstall_launchd_no_plist(self, tmp_path, monkeypatch):
        """macOS 卸载时 plist 不存在也应返回 True"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        from clawhermes.gateway import setup

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.uninstall_gateway_service()
            assert result is True

    def test_uninstall_launchd_subprocess_failure(self, tmp_path, monkeypatch):
        """macOS 卸载时 launchctl unload 失败应返回 False"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        import subprocess as sp

        from clawhermes.gateway import setup

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text("dummy")

        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(sp.CalledProcessError(1, [])),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            result = setup.uninstall_gateway_service()
            assert result is False

    def test_check_status_darwin_installed_and_running(self, tmp_path, monkeypatch):
        """macOS 上 plist 存在且 launchctl list 含 PID 时 running=True"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        from clawhermes.gateway import setup

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text("dummy")

        def _fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 0
            m.stdout = '"PID" = 1234;'
            return m

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", _fake_run)
            m.setattr(Path, "home", lambda: tmp_path)
            status = setup.check_gateway_service_status()
            assert status["installed"] is True
            assert status["running"] is True
            assert status["platform"] == "Darwin"

    def test_check_status_darwin_installed_not_running(self, tmp_path, monkeypatch):
        """macOS 上 plist 存在但 launchctl list 不含 PID 时 running=False"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        from clawhermes.gateway import setup

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text("dummy")

        def _fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 0
            m.stdout = ""
            return m

        with monkeypatch.context() as m:
            m.setattr("subprocess.run", _fake_run)
            m.setattr(Path, "home", lambda: tmp_path)
            status = setup.check_gateway_service_status()
            assert status["installed"] is True
            assert status["running"] is False

    def test_check_status_darwin_subprocess_error(self, tmp_path, monkeypatch):
        """macOS 上 launchctl 调用异常时 running=False"""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        import subprocess as sp

        from clawhermes.gateway import setup

        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.clawhermes.gateway.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text("dummy")

        with monkeypatch.context() as m:
            m.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(sp.CalledProcessError(1, [])),
            )
            m.setattr(Path, "home", lambda: tmp_path)
            status = setup.check_gateway_service_status()
            assert status["installed"] is True
            assert status["running"] is False
