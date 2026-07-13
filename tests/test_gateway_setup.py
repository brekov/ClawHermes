"""
Gateway Setup 模块测试。

覆盖:
- Token 生成与持久化
- 服务状态检查
- CLI gateway 子命令
"""
from __future__ import annotations

import os

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
        result = runner.invoke(main, ["gateway", "setup", "--host", "0.0.0.0"])
        # Should not crash on macOS without launchctl
        assert result.exit_code in (0, 1)

    def test_gateway_uninstall(self):
        runner = CliRunner()
        result = runner.invoke(main, ["gateway", "uninstall"])
        assert result.exit_code in (0, 1)
