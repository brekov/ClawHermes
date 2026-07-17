"""ClawHermes - 安全测试套件（负例）

覆盖路径穿越、SQL 注入、配对绕过、CORS/Gateway 安全四大类负例场景。
对应 PR1-PR4 安全修复（H1/H3/H4/H8/C6/M14）。
"""
from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

import clawhermes.gateway.app as gw
from clawhermes.agent import agent_mgr
from clawhermes.agent.exceptions import ConfigValidationError
from clawhermes.channel.pairing import (
    DMPairingManager,
    PairingInvalidError,
    PairingRateLimitError,
)
from clawhermes.gateway.app import GatewayState, app
from clawhermes.skills.manager import SkillManager
from clawhermes.tools.builtin import _sqlite_query

# ============================================================
# 1. 路径穿越（Path Traversal）测试
# ============================================================


class TestPathTraversal:
    """ScopedPath 名称正则 + is_relative_to 双层校验（H1）"""

    def test_skill_create_rejects_path_traversal(self, tmp_path):
        """../../ 穿越 + 非法字符（/ 和 .）应被名称正则拦截"""
        sm = SkillManager(tmp_path / "skills")
        with pytest.raises(ConfigValidationError):
            sm.create("../../.ssh/authorized_keys", "content")

    def test_skill_create_rejects_absolute_path(self, tmp_path):
        """绝对路径含 / 应被名称正则拦截"""
        sm = SkillManager(tmp_path / "skills")
        with pytest.raises(ConfigValidationError):
            sm.create("/etc/passwd", "content")

    def test_skill_create_rejects_null_byte(self, tmp_path):
        """null 字节应被名称正则拦截"""
        sm = SkillManager(tmp_path / "skills")
        with pytest.raises(ConfigValidationError):
            sm.create("evil\x00.txt", "content")

    def test_agent_create_rejects_traversal(self, tmp_path, monkeypatch):
        """AgentManager.create_agent 同样走 ScopedPath 校验"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        with pytest.raises(ConfigValidationError):
            agent_mgr.create_agent("../../../tmp/evil")


# ============================================================
# 2. SQL 注入测试
# ============================================================


class TestSQLInjection:
    """SQLite 只读模式 + data_dir 限定 + 写操作显式开关（H3）"""

    def test_sqlite_query_rejects_dangerous_default(self, tmp_path):
        """DROP 等危险操作默认被拒，需 allow_write=True"""
        db = tmp_path / "test.db"
        result = _sqlite_query(str(db), "DROP TABLE x; --")
        assert "error" in result
        assert "allow_write" in result["error"]

    def test_sqlite_query_rejects_data_dir_escape(self, tmp_path):
        """db_path 指向 data_dir 外被拒"""
        result = _sqlite_query("/etc/passwd", "SELECT 1", data_dir=tmp_path)
        assert "error" in result
        assert "路径越界" in result["error"]

    def test_sqlite_query_write_requires_explicit_flag(self, tmp_path):
        """写操作（INSERT）默认被只读模式拒绝，需 allow_write=True"""
        db = tmp_path / "test.db"
        _sqlite_query(str(db), "CREATE TABLE t (id INTEGER)", allow_write=True)

        result = _sqlite_query(str(db), "INSERT INTO t VALUES (1)")
        assert "error" in result

        result2 = _sqlite_query(str(db), "INSERT INTO t VALUES (1)", allow_write=True)
        assert result2.get("affected") == 1


# ============================================================
# 3. 配对绕过测试
# ============================================================


class TestPairingBypass:
    """user_id 必填 + 绑定校验 + 漏桶限流 + code 长度（C6/H8）"""

    @pytest.fixture
    def manager(self):
        return DMPairingManager()

    def test_pairing_verify_missing_user_id_raises(self, manager):
        """verify_code 缺 user_id 必填参数 → TypeError"""
        req = manager.generate_code("user_missing", "feishu")
        response = manager._compute_challenge_response(req.challenge)
        with pytest.raises(TypeError):
            manager.verify_code(req.code, response)

    def test_pairing_verify_wrong_user_id_raises(self, manager):
        """verify_code user_id 与配对码绑定不匹配 → PairingInvalidError"""
        req = manager.generate_code("user_correct", "feishu")
        response = manager._compute_challenge_response(req.challenge)
        with pytest.raises(PairingInvalidError):
            manager.verify_code(req.code, response, "wrong_user")

    def test_pairing_rate_limit_triggered(self):
        """10 次/分钟错误尝试后，第 11 次触发 PairingRateLimitError"""
        manager = DMPairingManager()
        for _ in range(10):
            with pytest.raises(PairingInvalidError):
                manager.verify_code("00000000", "bad_response", "user_rl")
        with pytest.raises(PairingRateLimitError):
            manager.verify_code("00000000", "bad_response", "user_rl")

    def test_pairing_code_length_is_8(self, manager):
        """生成的配对码长度为 8（H8: 6→8 扩大搜索空间）"""
        req = manager.generate_code("user_len", "feishu")
        assert len(req.code) == 8


# ============================================================
# 4. CORS / Gateway 安全测试
# ============================================================


@pytest.fixture
def fresh_gateway_state(monkeypatch):
    """每个测试前重置 gateway _state，隔离 CH_DATA_DIR 和 API key 环境变量"""
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("CH_DATA_DIR", tmp)
    monkeypatch.delenv("CH_GW_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old_state = gw._state
    gw._state = GatewayState()
    yield gw._state
    for task in gw._state._bg_tasks:
        if not task.done():
            task.cancel()
    gw._state = old_state


class TestCORSGatewaySecurity:
    """CORS 互斥校验 + secret 恒定时间比较 + 初始化失败 503（H4/M14）"""

    def test_cors_wildcard_with_credentials_rejected(self):
        """CORS allow_origins=['*'] + allow_credentials=True 互斥 → sys.exit(1)"""
        with pytest.raises(SystemExit):
            gw._validate_cors_config(["*"], True)

    def test_gateway_secret_uses_compare_digest(self, fresh_gateway_state):
        """网关 secret 比较走 hmac.compare_digest 恒定时间路径"""
        with patch("clawhermes.gateway.app._gateway_secret", "topsecret"), \
             patch("hmac.compare_digest", return_value=True) as mock_cd:
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/tools", headers={"X-Gateway-Secret": "topsecret"})
            mock_cd.assert_called_once_with("topsecret", "topsecret")

    def test_gateway_init_failure_returns_503(self, fresh_gateway_state):
        """_auto_init 失败后 /health 返回 degraded，非 health 端点返回 503"""
        fresh_gateway_state._init_error = "auto-init boom"
        with patch("clawhermes.gateway.app._gateway_secret", ""):
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 503
            assert resp.json()["status"] == "degraded"

            resp2 = client.get("/tools")
            assert resp2.status_code == 503
