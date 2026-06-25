"""
ClawHermes CLI 测试。

覆盖所有 CLI 子命令的主路径：
- doctor（依赖检测）
- chat（one-shot 模式，agent 创建失败）
- gateway start（参数验证 + uvicorn mock）
- config show / config path
- agent list / create / show / switch / set
- setup（目录初始化）
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from clawhermes.cli import main


@pytest.fixture(autouse=True)
def _prevent_network(monkeypatch):
    """全局 mock：阻止 CLI 测试触发真实网络/IO。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-mock")
    monkeypatch.setenv("CH_DATA_DIR", os.path.join(os.getcwd(), ".test_cli_tmp"))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

class TestDoctor:
    def test_doctor_runs(self):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        assert "Python" in result.output

    def test_doctor_detects_api_keys(self, monkeypatch):
        monkeypatch.setenv("MOCK_API_KEY", "sk-xxx")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        assert "MOCK_API_KEY" in result.output

    def test_doctor_no_api_keys_warning(self, monkeypatch):
        # 清除所有 _API_KEY 环境变量
        for k in list(os.environ):
            if k.endswith("_API_KEY"):
                monkeypatch.delenv(k, raising=False)
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        assert "未设置 API Key" in result.output


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

class TestChat:
    def test_one_shot_success(self, monkeypatch, tmp_path):
        """one-shot 模式：创建 agent 成功并返回回复。"""
        fake_agent = MagicMock()
        fake_agent.chat.return_value = "Hello!"
        fake_agent.tools.list.return_value = []
        fake_agent.llm.model = "test-model"

        # mock 掉交互式 Prompt（one-shot 不应触发）
        with patch("clawhermes.cli._create_agent", return_value=(fake_agent, MagicMock())):
            runner = CliRunner()
            result = runner.invoke(main, ["chat", "--one-shot", "hi"])
        assert result.exit_code == 0
        fake_agent.chat.assert_called_once_with("hi")

    def test_one_shot_agent_creation_fails(self, monkeypatch):
        """agent 创建失败时应打印错误并退出。"""
        with patch("clawhermes.cli._create_agent", side_effect=RuntimeError("no key")):
            runner = CliRunner()
            result = runner.invoke(main, ["chat", "--one-shot", "hi"])
        assert result.exit_code == 0  # CLI 不 crash，只是打印错误
        assert "❌" in result.output

    def test_one_shot_chat_error(self, monkeypatch):
        """chat 调用异常时应打印错误。"""
        fake_agent = MagicMock()
        fake_agent.chat.side_effect = RuntimeError("LLM 不可用")
        fake_agent.tools.list.return_value = []
        fake_agent.llm.model = "test"

        with patch("clawhermes.cli._create_agent", return_value=(fake_agent, MagicMock())):
            runner = CliRunner()
            result = runner.invoke(main, ["chat", "--one-shot", "hi"])
        assert "❌" in result.output


# ---------------------------------------------------------------------------
# gateway start
# ---------------------------------------------------------------------------

class TestGateway:
    def test_start_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        runner = CliRunner()
        result = runner.invoke(main, ["gateway", "start"])
        assert result.exit_code == 0
        assert "DEEPSEEK_API_KEY" in result.output

    def test_start_launches_uvicorn(self):
        with patch("uvicorn.run"):
            runner = CliRunner()
            result = runner.invoke(main, ["gateway", "start", "--port", "9999"])
        assert result.exit_code == 0 or "9999" in result.output


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_path(self):
        runner = CliRunner()
        result = runner.invoke(main, ["config", "path"])
        assert result.exit_code == 0
        assert "📄" in result.output

    def test_config_show_empty(self, tmp_path, monkeypatch):
        """config.yaml 不存在时应提示运行 setup。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "nonexist"))
        runner = CliRunner()
        result = runner.invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "config.yaml" in result.output


# ---------------------------------------------------------------------------
# agent 子命令
# ---------------------------------------------------------------------------

class TestAgent:
    def test_agent_list(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.cmd_list") as mock_cmd:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "list"])
        assert result.exit_code == 0
        mock_cmd.assert_called_once()

    def test_agent_create(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.cmd_create") as mock_cmd:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "create", "myagent"])
        assert result.exit_code == 0
        mock_cmd.assert_called_once_with("myagent", None)

    def test_agent_create_with_clone(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.cmd_create") as mock_cmd:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "create", "new", "--clone", "old"])
        assert result.exit_code == 0
        mock_cmd.assert_called_once_with("new", "old")

    def test_agent_show(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.cmd_show") as mock_cmd:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "show", "default"])
        assert result.exit_code == 0
        mock_cmd.assert_called_once_with("default")

    def test_agent_show_no_name(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.cmd_show") as mock_cmd:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "show"])
        assert result.exit_code == 0
        mock_cmd.assert_called_once_with(None)

    def test_agent_switch_exists(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.agent_exists", return_value=True), \
             patch("clawhermes.agent.agent_mgr.set_default_agent") as mock_set:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "switch", "myagent"])
        assert result.exit_code == 0
        assert "已切换" in result.output
        mock_set.assert_called_once_with("myagent")

    def test_agent_switch_not_exists(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.agent_exists", return_value=False):
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "switch", "ghost"])
        assert result.exit_code == 0
        assert "不存在" in result.output

    def test_agent_set(self, monkeypatch):
        with patch("clawhermes.agent.agent_mgr.cmd_set_persona") as mock_cmd:
            runner = CliRunner()
            result = runner.invoke(main, ["agent", "set", "default"])
        assert result.exit_code == 0
        mock_cmd.assert_called_once_with("default")


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

class TestSetup:
    def test_setup_creates_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "clawhome"))
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            runner = CliRunner()
            result = runner.invoke(main, ["setup"])
        assert result.exit_code == 0
        assert "初始化完成" in result.output
        assert ".env 已生成" in result.output


# ---------------------------------------------------------------------------
# _create_agent 辅助函数
# ---------------------------------------------------------------------------

class TestCreateAgent:
    def test_create_agent_with_env_vars(self, monkeypatch, tmp_path):
        """验证 _create_agent 读取环境变量并正确构造 Agent。"""
        from clawhermes.cli import _create_agent
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        agent, memory = _create_agent(
            api_key="sk-test", model="deepseek/deepseek-chat",
        )
        assert agent is not None
        assert agent.llm.model == "deepseek/deepseek-chat"

    def test_create_agent_default_model(self, monkeypatch, tmp_path):
        from clawhermes.cli import _create_agent
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        agent, _ = _create_agent()
        assert agent is not None
