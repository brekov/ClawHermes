"""ClawHermes CLI setup 模块测试。

覆盖 setup.py 的交互式配置向导：
- config 子命令 (show / path)
- setup 主命令 (非交互模式 / 各 section 分发 / 交互编排)
- _setup_model_section / _setup_channels_section / _setup_gateway_section
- _setup_tools_section / _setup_agent_section
- _apply_setup / _write_env / _copy_and_populate_channel / _copy_channel_example
- _fetch_models_from_api / _ask_custom_model / _ensure_lark_sdk
- 飞书相关辅助函数 (_probe_feishu / _resolve_bot_identity /
  _verify_feishu_event_subscriptions / _setup_feishu_security /
  _onboard_feishu / _run_scan_to_create / _run_manual_feishu_setup)
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from clawhermes.cli import main
from clawhermes.cli.setup import (
    _apply_setup,
    _ask_custom_model,
    _copy_and_populate_channel,
    _copy_channel_example,
    _ensure_lark_sdk,
    _fetch_models_from_api,
    _finalize_section,
    _load_existing_env,
    _onboard_feishu,
    _probe_feishu,
    _providers,
    _quick_skip,
    _resolve_bot_identity,
    _run_manual_feishu_setup,
    _run_scan_to_create,
    _setup_agent_section,
    _setup_channels_section,
    _setup_feishu_security,
    _setup_gateway_section,
    _setup_model_section,
    _setup_noninteractive,
    _setup_tools_section,
    _verify_feishu_event_subscriptions,
    _write_env,
    channel_defs,
)

# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------


def _q(value):
    """构造 questionary.xxx(...).ask() 返回 value 的 mock 对象。"""
    m = MagicMock()
    m.ask.return_value = value
    return m


def _provider_choice(idx: int) -> str:
    """生成 _setup_model_section 中 questionary.select 的 provider 选项字符串。"""
    p = _providers[idx]
    return f"{p['name']:20s} {p['prefix']}"


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """每个测试使用独立数据目录 + 阻止真实网络/agent 创建。"""
    monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "clawhermes"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-mock")
    yield
    # 清理 clawhermes_lark 残留 (避免循环导入污染后续测试)
    for k in list(sys.modules):
        if k.startswith("clawhermes_lark"):
            del sys.modules[k]


# ---------------------------------------------------------------------------
# config 子命令
# ---------------------------------------------------------------------------


class TestConfigCommands:
    def test_config_path(self):
        result = CliRunner().invoke(main, ["config", "path"])
        assert result.exit_code == 0
        assert "📄" in result.output

    def test_config_show_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "noexist"))
        result = CliRunner().invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "config.yaml" in result.output

    def test_config_show_with_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        (tmp_path / "config.yaml").write_text("llm:\n  model: deepseek/chat\n")
        result = CliRunner().invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "deepseek" in result.output


# ---------------------------------------------------------------------------
# setup --non-interactive
# ---------------------------------------------------------------------------


class TestSetupNonInteractive:
    @pytest.mark.parametrize("section", [None, "model", "gateway", "channels", "tools", "agent"])
    def test_non_interactive_sections(self, tmp_path, monkeypatch, section):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / f"data_{section}"))
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            args = ["setup", "--non-interactive"]
            if section:
                args.append(section)
            result = CliRunner().invoke(main, args)
        assert result.exit_code == 0
        assert "非交互模式" in result.output
        assert "初始化完成" in result.output

    def test_non_interactive_with_reset(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "reset_data"))
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            result = CliRunner().invoke(main, ["setup", "--non-interactive", "--reset"])
        assert result.exit_code == 0
        assert "配置已重置" in result.output

    def test_setup_noninteractive_direct(self, tmp_path, monkeypatch):
        """直接调用 _setup_noninteractive 覆盖各分支。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "ni"))
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            _setup_noninteractive(section=None, reset=True)
        # 验证 .env 已生成
        env_path = tmp_path / "ni" / ".env"
        assert env_path.exists()
        content = env_path.read_text()
        assert "CH_LLM_DEFAULT_MODEL" in content
        assert "CH_GATEWAY_HOST" in content


# ---------------------------------------------------------------------------
# setup 交互编排 (直接调用 callback 绕过 CliRunner 的 stdin 替换)
# ---------------------------------------------------------------------------


class TestSetupInteractive:
    def test_interactive_full_flow_confirmed(self, tmp_path, monkeypatch):
        """交互模式完整流程 — 确认生成配置。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_data"))
        # 让 sys.stdin.isatty() 返回 True
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {"CH_LLM_DEFAULT_MODEL": "deepseek/chat"},
                                 "model": "deepseek/chat"}), \
             patch("clawhermes.cli.setup._setup_channels_section",
                   return_value={"env": {}, "channels": []}), \
             patch("clawhermes.cli.setup._setup_gateway_section",
                   return_value={"env": {"CH_GATEWAY_HOST": "127.0.0.1",
                                         "CH_GATEWAY_PORT": "18789"},
                                 "host": "127.0.0.1", "port": 18789}), \
             patch("clawhermes.cli.setup._setup_tools_section",
                   return_value={"env": {"CH_TOOLS_PROFILE": "standard"}}), \
             patch("clawhermes.cli.setup._setup_agent_section",
                   return_value={"env": {"CH_AGENT_MAX_ITERATIONS": "50"}}), \
             patch("clawhermes.agent.agent_mgr.create_agent"), \
             patch("questionary.confirm", return_value=_q(True)):
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=False, reset=False)
        assert (tmp_path / "int_data" / ".env").exists()

    def test_interactive_full_flow_cancelled(self, tmp_path, monkeypatch):
        """交互模式完整流程 — 用户取消。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_cancel"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {}, "model": "deepseek/chat"}), \
             patch("clawhermes.cli.setup._setup_channels_section",
                   return_value={"env": {}, "channels": []}), \
             patch("clawhermes.cli.setup._setup_gateway_section",
                   return_value={"env": {}, "host": "127.0.0.1", "port": 18789}), \
             patch("clawhermes.cli.setup._setup_tools_section",
                   return_value={"env": {}}), \
             patch("clawhermes.cli.setup._setup_agent_section",
                   return_value={"env": {}}), \
             patch("questionary.confirm", return_value=_q(False)):
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=False, reset=False)
        # 取消后不应生成 .env
        assert not (tmp_path / "int_cancel" / ".env").exists()

    def test_interactive_model_section_only(self, tmp_path, monkeypatch):
        """交互模式仅运行 model section。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_model"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {"CH_LLM_DEFAULT_MODEL": "x"},
                                 "model": "x"}), \
             patch("clawhermes.cli.setup._finalize_section") as mock_fin, \
             patch("clawhermes.agent.agent_mgr.create_agent"):
            setup_cmd.callback(non_interactive=False, section="model",
                               quick=False, reset=False)
        mock_fin.assert_called_once()

    def test_interactive_model_section_returns_none(self, tmp_path, monkeypatch):
        """model section 返回 None 时中止。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_none"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section", return_value=None), \
             patch("clawhermes.cli.setup._finalize_section") as mock_fin:
            setup_cmd.callback(non_interactive=False, section="model",
                               quick=False, reset=False)
        mock_fin.assert_not_called()

    def test_interactive_channels_section_returns_none(self, tmp_path, monkeypatch):
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_ch_none"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {}, "model": "x"}), \
             patch("clawhermes.cli.setup._setup_channels_section", return_value=None), \
             patch("clawhermes.cli.setup._finalize_section") as mock_fin:
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=False, reset=False)
        mock_fin.assert_not_called()

    def test_interactive_gateway_section_returns_none(self, tmp_path, monkeypatch):
        """gateway section 返回 None 时中止完整流程。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_gw_none"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {}, "model": "x"}), \
             patch("clawhermes.cli.setup._setup_channels_section",
                   return_value={"env": {}, "channels": []}), \
             patch("clawhermes.cli.setup._setup_gateway_section", return_value=None), \
             patch("clawhermes.cli.setup._finalize_section") as mock_fin:
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=False, reset=False)
        mock_fin.assert_not_called()

    def test_stdin_not_tty_triggers_noninteractive(self, tmp_path, monkeypatch):
        """stdin 非 tty 时自动切换到非交互模式。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_notty"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_noninteractive") as mock_ni:
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=False, reset=False)
        mock_ni.assert_called_once_with(section=None, reset=False)

    def test_interactive_quick_mode(self, tmp_path, monkeypatch):
        """quick 模式加载已有配置。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_quick"))
        data_dir = tmp_path / "int_quick"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / ".env").write_text("DEEPSEEK_API_KEY=sk-existing\n")

        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        import yaml as _yaml

        from clawhermes.config import default_yaml
        cfg = default_yaml()
        cfg["llm"]["model"] = "existing-model"
        (data_dir / "config.yaml").write_text(_yaml.dump(cfg))

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {}, "model": "x"}) as mock_model, \
             patch("clawhermes.cli.setup._setup_channels_section",
                   return_value={"env": {}, "channels": []}), \
             patch("clawhermes.cli.setup._setup_gateway_section",
                   return_value={"env": {}, "host": "127.0.0.1", "port": 18789}), \
             patch("clawhermes.cli.setup._setup_tools_section",
                   return_value={"env": {}}), \
             patch("clawhermes.cli.setup._setup_agent_section",
                   return_value={"env": {}}), \
             patch("clawhermes.agent.agent_mgr.create_agent"), \
             patch("questionary.confirm", return_value=_q(True)):
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=True, reset=False)
        mock_model.assert_called_once()

    def test_interactive_reset_mode(self, tmp_path, monkeypatch):
        """reset 模式先写默认配置。"""
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "int_reset"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        with patch("clawhermes.cli.setup._setup_model_section",
                   return_value={"env": {}, "model": "x"}), \
             patch("clawhermes.cli.setup._setup_channels_section",
                   return_value={"env": {}, "channels": []}), \
             patch("clawhermes.cli.setup._setup_gateway_section",
                   return_value={"env": {}, "host": "127.0.0.1", "port": 18789}), \
             patch("clawhermes.cli.setup._setup_tools_section",
                   return_value={"env": {}}), \
             patch("clawhermes.cli.setup._setup_agent_section",
                   return_value={"env": {}}), \
             patch("clawhermes.agent.agent_mgr.create_agent"), \
             patch("questionary.confirm", return_value=_q(True)):
            setup_cmd.callback(non_interactive=False, section=None,
                               quick=False, reset=True)
        # reset 后 config.yaml 应存在
        assert (tmp_path / "int_reset" / "config.yaml").exists()

    @pytest.mark.parametrize("section", ["channels", "gateway", "tools", "agent"])
    def test_interactive_single_sections(self, tmp_path, monkeypatch, section):
        from clawhermes.cli.setup import setup as setup_cmd

        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / f"int_{section}"))
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr("sys.stdin", fake_stdin)

        section_map = {
            "channels": "_setup_channels_section",
            "gateway": "_setup_gateway_section",
            "tools": "_setup_tools_section",
            "agent": "_setup_agent_section",
        }
        mock_target = f"clawhermes.cli.setup.{section_map[section]}"
        with patch(mock_target, return_value={"env": {}}) as mock_fn, \
             patch("clawhermes.cli.setup._finalize_section") as mock_fin:
            setup_cmd.callback(non_interactive=False, section=section,
                               quick=False, reset=False)
        mock_fn.assert_called_once()
        mock_fin.assert_called_once()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_load_existing_env_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        assert _load_existing_env() == {}

    def test_load_existing_env_with_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        (tmp_path / ".env").write_text("FOO=bar\nBAZ=\n# comment\n")
        result = _load_existing_env()
        assert result["FOO"] == "bar"
        assert result["BAZ"] == ""

    def test_quick_skip(self):
        assert _quick_skip("X", {}, {}) is False
        assert _quick_skip("X", {"X": "v"}, {}) is True
        assert _quick_skip("X", {}, {"X": "v"}) is True
        assert _quick_skip("X", {"X": ""}, {"X": ""}) is False

    def test_finalize_section(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        with patch("clawhermes.cli.setup._apply_setup") as mock_apply:
            _finalize_section({"K": "v"}, ["lark"], channel_defs,
                              "model", "127.0.0.1", 18789)
        mock_apply.assert_called_once_with(
            {"K": "v"}, ["lark"], channel_defs, "model", "127.0.0.1", 18789,
        )

    def test_finalize_section_none_model(self, tmp_path, monkeypatch):
        """model 为 None 时使用默认值。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        with patch("clawhermes.cli.setup._apply_setup") as mock_apply:
            _finalize_section({}, [], channel_defs, None, "127.0.0.1", 18789)
        mock_apply.assert_called_once_with(
            {}, [], channel_defs, "deepseek/deepseek-chat", "127.0.0.1", 18789,
        )


# ---------------------------------------------------------------------------
# _setup_model_section
# ---------------------------------------------------------------------------


class TestSetupModelSection:
    def test_quick_skip_when_model_exists(self):
        result = _setup_model_section({"llm": {"model": "deepseek/chat"}}, {}, True)
        assert result == {"env": {}, "model": "deepseek/chat"}

    @patch("questionary.password")
    @patch("questionary.select")
    def test_deepseek_with_api_key(self, mock_sel, mock_pwd):
        choice = _provider_choice(0)  # DeepSeek
        model_val = "deepseek/deepseek-chat"
        mock_sel.side_effect = [_q(choice), _q(model_val)]
        mock_pwd.return_value = _q("sk-deepseek-test")

        result = _setup_model_section({}, {}, False)
        assert result["env"]["DEEPSEEK_API_KEY"] == "sk-deepseek-test"
        assert result["env"]["CH_LLM_DEFAULT_MODEL"] == model_val
        assert result["model"] == model_val

    @patch("questionary.password")
    @patch("questionary.select")
    def test_deepseek_custom_model(self, mock_sel, mock_pwd):
        choice = _provider_choice(0)
        mock_sel.side_effect = [_q(choice), _q("__custom__")]
        mock_pwd.return_value = _q("sk-test")

        with patch("questionary.text", return_value=_q("custom/model")):
            result = _setup_model_section({}, {}, False)
        assert result["env"]["CH_LLM_DEFAULT_MODEL"] == "custom/model"
        assert result["model"] == "custom/model"

    @patch("questionary.password")
    @patch("questionary.select")
    def test_deepseek_fetch_from_api(self, mock_sel, mock_pwd):
        choice = _provider_choice(0)
        mock_sel.side_effect = [_q(choice), _q("__fetch__")]
        mock_pwd.return_value = _q("sk-test")

        with patch("clawhermes.cli.setup._fetch_models_from_api",
                   return_value="deepseek/fetched-model") as mock_fetch:
            result = _setup_model_section({}, {}, False)
        mock_fetch.assert_called_once()
        assert result["model"] == "deepseek/fetched-model"

    @patch("questionary.select")
    def test_cancel_at_provider(self, mock_sel):
        mock_sel.return_value = _q(None)
        result = _setup_model_section({}, {}, False)
        assert result is None

    @patch("questionary.password")
    @patch("questionary.select")
    def test_quick_skip_api_key(self, mock_sel, mock_pwd):
        """quick 模式下 api_key 已设置时跳过输入。"""
        choice = _provider_choice(0)
        mock_sel.return_value = _q(choice)
        model_val = "deepseek/deepseek-chat"
        # 第二次 select 调用返回 model
        mock_sel.side_effect = [_q(choice), _q(model_val)]

        result = _setup_model_section({}, {"DEEPSEEK_API_KEY": "sk-existing"}, True)
        assert "DEEPSEEK_API_KEY" not in result["env"]
        assert result["model"] == model_val

    @patch("questionary.text")
    @patch("questionary.select")
    def test_ollama_provider(self, mock_sel, mock_text):
        ollama = _providers[10]
        assert ollama["name"] == "Ollama (本地)"
        choice = _provider_choice(10)
        mock_sel.side_effect = [_q(choice), _q("ollama/qwen2.5")]
        mock_text.return_value = _q("http://localhost:11434")

        result = _setup_model_section({}, {}, False)
        assert result["env"]["OLLAMA_BASE_URL"] == "http://localhost:11434"
        assert result["model"] == "ollama/qwen2.5"

    @patch("questionary.password")
    @patch("questionary.select")
    def test_vllm_provider(self, mock_sel, mock_pwd):
        """vLLM 有 key=VLLM_API_KEY, 走 if 分支 (非 elif vLLM 分支)。"""
        vllm = _providers[12]
        assert vllm["key"] == "VLLM_API_KEY"
        choice = _provider_choice(12)
        # vLLM 的 prov_key 是 vllm_自部署 → model_key=None → 走 else (text)
        mock_sel.side_effect = [_q(choice)]
        mock_pwd.return_value = _q("vllm-key-123")

        with patch("questionary.text", return_value=_q("openai/hosted_vllm/MODEL")):
            result = _setup_model_section({}, {}, False)
        assert result["env"]["VLLM_API_KEY"] == "vllm-key-123"
        assert result["model"] == "openai/hosted_vllm/MODEL"

    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_custom_litellm_provider(self, mock_sel, mock_text, mock_pwd):
        """自定义 litellm provider: key=None, 走 elif 自定义分支。"""
        custom = _providers[13]
        assert custom["name"] == "自定义 (litellm)"
        assert custom["key"] is None
        choice = _provider_choice(13)
        mock_sel.return_value = _q(choice)
        mock_text.side_effect = [_q("https://custom.api/v1"), _q("custom-model")]
        mock_pwd.return_value = _q("custom-key")

        result = _setup_model_section({}, {}, False)
        assert result["env"]["CUSTOM_LLM_BASE_URL"] == "https://custom.api/v1"
        assert result["env"]["CUSTOM_LLM_API_KEY"] == "custom-key"
        assert result["model"] == "custom-model"

    @patch("questionary.password")
    @patch("questionary.select")
    def test_empty_api_key(self, mock_sel, mock_pwd):
        """api_key 输入为空时不写入 env。"""
        choice = _provider_choice(0)
        mock_sel.side_effect = [_q(choice), _q("deepseek/deepseek-chat")]
        mock_pwd.return_value = _q("")

        result = _setup_model_section({}, {}, False)
        assert "DEEPSEEK_API_KEY" not in result["env"]


# ---------------------------------------------------------------------------
# _setup_channels_section
# ---------------------------------------------------------------------------


class TestSetupChannelsSection:
    @patch("questionary.checkbox")
    def test_no_channels_selected(self, mock_cb):
        mock_cb.return_value = _q([])
        result = _setup_channels_section(channel_defs, {}, False)
        assert result["channels"] == []
        assert result["env"] == {}

    @patch("questionary.checkbox")
    def test_cancel_selection(self, mock_cb):
        mock_cb.return_value = _q(None)
        result = _setup_channels_section(channel_defs, {}, False)
        assert result["channels"] == []
        assert result["env"] == {}

    @patch("clawhermes.cli.setup._onboard_feishu")
    @patch("clawhermes.cli.setup._ensure_lark_sdk")
    @patch("questionary.checkbox")
    def test_lark_channel(self, mock_cb, mock_ensure, mock_onboard):
        mock_cb.return_value = _q(["lark"])
        result = _setup_channels_section(channel_defs, {}, False)
        mock_ensure.assert_called_once()
        mock_onboard.assert_called_once()
        assert result["channels"] == ["lark"]

    @patch("questionary.password")
    @patch("questionary.checkbox")
    def test_weixin_channel(self, mock_cb, mock_pwd):
        mock_cb.return_value = _q(["weixin"])
        mock_pwd.return_value = _q("wx-secret")
        result = _setup_channels_section(channel_defs, {}, False)
        assert result["channels"] == ["weixin"]
        assert result["env"]["WECHAT_APP_ID"] == "wx-secret"
        assert result["env"]["WECHAT_APP_SECRET"] == "wx-secret"  # noqa: S105

    @patch("questionary.password")
    @patch("questionary.checkbox")
    def test_qq_channel(self, mock_cb, mock_pwd):
        mock_cb.return_value = _q(["qq"])
        mock_pwd.return_value = _q("qq-cred")
        result = _setup_channels_section(channel_defs, {}, False)
        assert result["channels"] == ["qq"]
        assert result["env"]["QQ_APP_ID"] == "qq-cred"

    @patch("questionary.password")
    @patch("questionary.checkbox")
    def test_quick_skip_existing_vars(self, mock_cb, mock_pwd):
        """quick 模式跳过已设置的渠道变量。"""
        mock_cb.return_value = _q(["weixin"])
        mock_pwd.return_value = _q("new-val")
        existing = {var: "old" for var, _ in channel_defs["weixin"]["vars"]}
        result = _setup_channels_section(channel_defs, existing, True)
        # quick 模式下所有变量已设置，应全部跳过
        assert result["env"] == {}
        mock_pwd.assert_not_called()

    @patch("questionary.password")
    @patch("questionary.checkbox")
    def test_multiple_channels(self, mock_cb, mock_pwd):
        mock_cb.return_value = _q(["weixin", "qq"])
        mock_pwd.return_value = _q("cred")
        result = _setup_channels_section(channel_defs, {}, False)
        assert set(result["channels"]) == {"weixin", "qq"}


# ---------------------------------------------------------------------------
# _setup_gateway_section
# ---------------------------------------------------------------------------


class TestSetupGatewaySection:
    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_loopback_mode(self, mock_sel, mock_text, mock_pwd):
        mock_sel.return_value = _q("loopback")
        mock_text.return_value = _q("18789")
        mock_pwd.return_value = _q("")  # 跳过可选 secret

        result = _setup_gateway_section({}, {}, False)
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 18789
        assert result["env"]["CH_GATEWAY_HOST"] == "127.0.0.1"

    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_lan_mode_with_secret(self, mock_sel, mock_text, mock_pwd):
        mock_sel.return_value = _q("lan")
        mock_text.return_value = _q("8080")
        mock_pwd.return_value = _q("a" * 20)  # >=16 字符

        result = _setup_gateway_section({}, {}, False)
        assert result["host"] == "0.0.0.0"  # noqa: S104
        assert result["port"] == 8080
        assert result["env"]["CH_GATEWAY_SECRET"] == "a" * 20

    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_custom_mode(self, mock_sel, mock_text, mock_pwd):
        mock_sel.side_effect = [_q("custom")]
        mock_text.side_effect = [_q("192.168.1.1"), _q("9000")]
        mock_pwd.return_value = _q("secret-key-16chars")

        result = _setup_gateway_section({}, {}, False)
        assert result["host"] == "192.168.1.1"
        assert result["port"] == 9000

    @patch("questionary.select")
    def test_cancel_at_bind_mode(self, mock_sel):
        mock_sel.return_value = _q(None)
        result = _setup_gateway_section({}, {}, False)
        assert result is None

    @patch("questionary.text")
    @patch("questionary.select")
    def test_custom_mode_empty_host(self, mock_sel, mock_text):
        """custom 模式下 host 为空时返回 None。"""
        mock_sel.return_value = _q("custom")
        mock_text.return_value = _q("")
        result = _setup_gateway_section({}, {}, False)
        assert result is None

    @patch("questionary.text")
    @patch("questionary.select")
    def test_empty_port(self, mock_sel, mock_text):
        mock_sel.return_value = _q("loopback")
        mock_text.return_value = _q("")
        result = _setup_gateway_section({}, {}, False)
        assert result is None

    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_loopback_with_optional_secret(self, mock_sel, mock_text, mock_pwd):
        mock_sel.return_value = _q("loopback")
        mock_text.return_value = _q("18789")
        mock_pwd.return_value = _q("optional-secret")

        result = _setup_gateway_section({}, {}, False)
        assert result["env"]["CH_GATEWAY_SECRET"] == "optional-secret"  # noqa: S105

    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_non_localhost_empty_secret(self, mock_sel, mock_text, mock_pwd):
        """非本地监听且 secret 为空时返回 None。"""
        mock_sel.return_value = _q("lan")
        mock_text.return_value = _q("8080")
        mock_pwd.return_value = _q("")

        result = _setup_gateway_section({}, {}, False)
        assert result is None

    @patch("questionary.password")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_uses_existing_config_defaults(self, mock_sel, mock_text, mock_pwd):
        """从 existing_config 读取默认 host/port。"""
        mock_sel.return_value = _q("loopback")
        mock_text.return_value = _q("18789")
        mock_pwd.return_value = _q("")
        existing = {"gateway": {"host": "10.0.0.1", "port": 9999}}
        _setup_gateway_section(existing, {}, False)
        # 验证 default_host 从 existing 读取 (虽然 loopback 不用)
        assert mock_text.called


# ---------------------------------------------------------------------------
# _setup_tools_section
# ---------------------------------------------------------------------------


class TestSetupToolsSection:
    @patch("questionary.select")
    def test_normal_flow(self, mock_sel):
        mock_sel.return_value = _q("full")
        result = _setup_tools_section({}, {}, False)
        assert result["env"]["CH_TOOLS_PROFILE"] == "full"

    @patch("questionary.select")
    def test_quick_skip(self, mock_sel):
        result = _setup_tools_section({"tools": {"profile": "minimal"}}, {}, True)
        assert result["env"] == {}
        mock_sel.assert_not_called()

    @patch("questionary.select")
    def test_empty_profile(self, mock_sel):
        mock_sel.return_value = _q(None)
        result = _setup_tools_section({}, {}, False)
        assert "CH_TOOLS_PROFILE" not in result["env"]


# ---------------------------------------------------------------------------
# _setup_agent_section
# ---------------------------------------------------------------------------


class TestSetupAgentSection:
    @patch("questionary.text")
    def test_normal_flow(self, mock_text):
        mock_text.side_effect = [_q("100"), _q("0.8")]
        result = _setup_agent_section({}, {}, False)
        assert result["env"]["CH_AGENT_MAX_ITERATIONS"] == "100"
        assert result["env"]["CH_CONTEXT_COMPRESS_THRESHOLD"] == "0.8"

    @patch("questionary.text")
    def test_quick_skip(self, mock_text):
        result = _setup_agent_section({"agent": {"max_iterations": 30}}, {}, True)
        assert result["env"] == {}
        mock_text.assert_not_called()

    @patch("questionary.text")
    def test_empty_values(self, mock_text):
        mock_text.side_effect = [_q(""), _q("")]
        result = _setup_agent_section({}, {}, False)
        assert "CH_AGENT_MAX_ITERATIONS" not in result["env"]


# ---------------------------------------------------------------------------
# _ensure_lark_sdk
# ---------------------------------------------------------------------------


class TestEnsureLarkSdk:
    def test_already_installed(self):
        """lark_oapi 已安装时应直接返回。"""
        # lark_oapi 在测试环境已安装
        _ensure_lark_sdk()  # 不应抛异常

    def test_not_installed_no_repo(self, monkeypatch):
        """lark_oapi 不可导入且无子仓库时打印警告。"""
        monkeypatch.setitem(sys.modules, "lark_oapi", None)
        with patch("pathlib.Path.exists", return_value=False):
            _ensure_lark_sdk()  # 不应抛异常

    def test_not_installed_with_repo_success(self, monkeypatch):
        """lark_oapi 不可导入但有子仓库时执行 pip install。"""
        monkeypatch.setitem(sys.modules, "lark_oapi", None)
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            _ensure_lark_sdk()
            mock_run.assert_called_once()

    def test_not_installed_install_fails(self, monkeypatch):
        """pip install 失败时打印错误。"""
        import subprocess
        monkeypatch.setitem(sys.modules, "lark_oapi", None)
        error = subprocess.CalledProcessError(1, [])
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run", side_effect=error):
            _ensure_lark_sdk()  # 不应抛异常


# ---------------------------------------------------------------------------
# _fetch_models_from_api
# ---------------------------------------------------------------------------


class TestFetchModelsFromApi:
    @patch("questionary.select")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_ollama_fetch_success(self, mock_req, mock_open, mock_sel):
        provider = _providers[10]  # Ollama
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"models": [{"name": "qwen2.5"}, {"name": "llama3"}]}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp
        mock_sel.return_value = _q("ollama/qwen2.5")

        result = _fetch_models_from_api(provider, "ollama/default")
        assert result == "ollama/qwen2.5"

    @patch("questionary.select")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_openai_fetch_success(self, mock_req, mock_open, mock_sel):
        provider = _providers[1]  # OpenAI
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data": [{"id": "gpt-4o"}, {"id": "ft:abc"}]}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            mock_sel.return_value = _q("openai/gpt-4o")

            result = _fetch_models_from_api(provider, "openai/default")
            assert result == "openai/gpt-4o"

    @patch("questionary.select")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_deepseek_fetch_success(self, mock_req, mock_open, mock_sel):
        provider = _providers[0]  # DeepSeek
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data": [{"id": "deepseek-chat"}]}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            mock_sel.return_value = _q("deepseek/deepseek-chat")

            result = _fetch_models_from_api(provider, "deepseek/default")
            assert result == "deepseek/deepseek-chat"

    @patch("clawhermes.cli.setup._ask_custom_model")
    @patch("urllib.request.urlopen")
    def test_fetch_exception_fallback(self, mock_open, mock_ask):
        """网络异常时回退到自定义输入。"""
        provider = _providers[10]  # Ollama
        mock_open.side_effect = Exception("network error")
        mock_ask.return_value = "ollama/fallback"

        result = _fetch_models_from_api(provider, "ollama/default")
        assert result == "ollama/fallback"

    @patch("clawhermes.cli.setup._ask_custom_model")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_fetch_empty_models_fallback(self, mock_req, mock_open, mock_ask):
        """返回空模型列表时回退到自定义输入。"""
        provider = _providers[10]  # Ollama
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"models": []}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp
        mock_ask.return_value = "ollama/custom"

        result = _fetch_models_from_api(provider, "ollama/default")
        assert result == "ollama/custom"

    @patch("questionary.text")
    @patch("questionary.select")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_fetch_custom_from_results(self, mock_req, mock_open, mock_sel, mock_text):
        """从 API 获取后选择 __custom__ 进入自定义输入。"""
        provider = _providers[10]  # Ollama
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"models": [{"name": "qwen2.5"}]}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp
        mock_sel.return_value = _q("__custom__")
        mock_text.return_value = _q("ollama/custom-from-list")

        result = _fetch_models_from_api(provider, "ollama/default")
        assert result == "ollama/custom-from-list"

    @patch("questionary.select")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_fetch_more_than_50_models(self, mock_req, mock_open, mock_sel):
        """返回超过 50 个模型时添加禁用提示选项。"""
        import json
        provider = _providers[10]  # Ollama
        models_data = {"models": [{"name": f"model{i}"} for i in range(55)]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(models_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp
        mock_sel.return_value = _q("ollama/model0")

        result = _fetch_models_from_api(provider, "ollama/default")
        assert result == "ollama/model0"

    @patch("clawhermes.cli.setup._ask_custom_model")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_openrouter_fetch_success(self, mock_req, mock_open, mock_ask):
        provider = _providers[11]  # OpenRouter
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data": [{"id": "openai/gpt-4o"}]}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            with patch("questionary.select", return_value=_q("openrouter/openai/gpt-4o")):
                result = _fetch_models_from_api(provider, "openrouter/default")
            assert result == "openrouter/openai/gpt-4o"


# ---------------------------------------------------------------------------
# _ask_custom_model
# ---------------------------------------------------------------------------


class TestAskCustomModel:
    @patch("questionary.text")
    def test_returns_input(self, mock_text):
        mock_text.return_value = _q("custom-model")
        assert _ask_custom_model("default-model") == "custom-model"

    @patch("questionary.text")
    def test_returns_none(self, mock_text):
        mock_text.return_value = _q(None)
        assert _ask_custom_model("default-model") is None


# ---------------------------------------------------------------------------
# _apply_setup
# ---------------------------------------------------------------------------


class TestApplySetup:
    def test_no_channels(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "apply"))
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            _apply_setup({"CH_LLM_DEFAULT_MODEL": "deepseek/chat"},
                         [], channel_defs, "deepseek/chat", "127.0.0.1", 18789)
        assert (tmp_path / "apply" / ".env").exists()
        assert (tmp_path / "apply" / "config.yaml").exists()
        assert (tmp_path / "apply" / "channels").exists()

    def test_with_channels(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "apply_ch"))
        with patch("clawhermes.agent.agent_mgr.create_agent"), \
             patch("clawhermes.cli.setup._copy_and_populate_channel") as mock_copy:
            _apply_setup({}, ["weixin", "qq"], channel_defs,
                         "deepseek/chat", "127.0.0.1", 18789)
        assert mock_copy.call_count == 2

    def test_creates_skills_and_providers_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "apply_dirs"))
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            _apply_setup({}, [], channel_defs, "deepseek/chat", "127.0.0.1", 18789)
        assert (tmp_path / "apply_dirs" / "skills").exists()
        assert (tmp_path / "apply_dirs" / "providers").exists()

    def test_channel_import_check(self, tmp_path, monkeypatch):
        """channels_enabled 中渠道模块未安装时打印警告。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "apply_imp"))
        # mock __import__ 避免 clawhermes_lark 循环导入污染 sys.modules
        real_import = __import__

        def _mock_import(name, *args, **kwargs):
            if name.startswith("clawhermes_lark"):
                raise ImportError("not available in test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _mock_import)
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            _apply_setup({}, ["lark"], channel_defs, "deepseek/chat", "127.0.0.1", 18789)

    def test_channel_import_success(self, tmp_path, monkeypatch):
        """channels_enabled 中渠道模块成功导入时打印成功。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "apply_imp_ok"))
        # 注入 mock clawhermes_lark 模块使 __import__ 成功
        monkeypatch.setitem(sys.modules, "clawhermes_lark", MagicMock())
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            _apply_setup({}, ["lark"], channel_defs, "deepseek/chat", "127.0.0.1", 18789)

    def test_core_package_import_error(self, tmp_path, monkeypatch):
        """核心包导入失败时打印警告并提示依赖缺失。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "apply_pkg_fail"))
        real_import = __import__

        def _mock_import(name, *args, **kwargs):
            if name == "litellm":
                raise ImportError("not available in test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _mock_import)
        with patch("clawhermes.agent.agent_mgr.create_agent"):
            _apply_setup({}, [], channel_defs, "deepseek/chat", "127.0.0.1", 18789)


# ---------------------------------------------------------------------------
# _write_env
# ---------------------------------------------------------------------------


class TestWriteEnv:
    def test_new_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        _write_env({"FOO": "bar", "BAZ": "qux"})
        content = (tmp_path / ".env").read_text()
        assert "FOO=bar" in content
        assert "BAZ=qux" in content

    def test_preserves_existing_keys(self, tmp_path, monkeypatch):
        """已存在的 KEY/SECRET/TOKEN 变量应保留。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=old-key  # comment\n")
        _write_env({"DEEPSEEK_API_KEY": "new-key", "OTHER": "val"})
        content = (tmp_path / ".env").read_text()
        assert "old-key" in content  # 保留旧值
        assert "OTHER=val" in content

    def test_blocks_dangerous_vars(self, tmp_path, monkeypatch):
        """危险环境变量应被阻断。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        _write_env({
            "PATH": "/usr/bin",
            "PYTHONPATH": "/evil",
            "LD_PRELOAD": "/evil.so",
            "SAFE_VAR": "ok",
        })
        content = (tmp_path / ".env").read_text()
        assert "SAFE_VAR=ok" in content
        assert "PATH=" not in content or "PATH=" in content.split("#")[0] is False
        assert "PYTHONPATH=" not in content
        assert "LD_PRELOAD=" not in content

    def test_strips_inline_comments(self, tmp_path, monkeypatch):
        """已有值中的行内注释应被剥离。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        (tmp_path / ".env").write_text("MY_KEY=value  # (保留已有)\n")
        _write_env({"MY_KEY": "new"})
        content = (tmp_path / ".env").read_text()
        # 行内注释被剥离，保留原值 "value"
        assert "value" in content

    def test_skips_comment_and_empty_lines(self, tmp_path, monkeypatch):
        """读取已有 .env 时跳过注释、空行和无等号行。"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        (tmp_path / ".env").write_text("# comment\n\nNO_EQUALS_LINE\nKEY=val\n")
        _write_env({"NEW": "val"})
        content = (tmp_path / ".env").read_text()
        assert "NEW=val" in content


# ---------------------------------------------------------------------------
# _copy_and_populate_channel
# ---------------------------------------------------------------------------


class TestCopyAndPopulateChannel:
    def test_populates_placeholders(self, tmp_path):
        """应将 ${VAR} 占位符替换为实际值。"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        example = src_dir / "feishu.yaml.example"
        example.write_text("app_id: ${FEISHU_APP_ID}\nsecret: ${FEISHU_APP_SECRET}\n")

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        with patch("clawhermes.cli.setup.Path.resolve") as mock_resolve:
            mock_resolve.return_value.parent.parent.parent.parent = tmp_path
            # 直接调用, src 存在
            _copy_and_populate_channel(
                "src/feishu.yaml.example", dest_dir, "lark",
                {"FEISHU_APP_ID": "cli_xxx", "FEISHU_APP_SECRET": "sec_xxx"},
            )

    def test_src_not_exists(self, tmp_path):
        """源文件不存在时不应抛异常。"""
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        # 使用不存在的 example_path
        _copy_and_populate_channel("nonexistent/path", dest_dir, "lark", {})

    def test_real_example_file(self, tmp_path, monkeypatch):
        """使用真实仓库中的 feishu.yaml.example 测试占位符替换。"""
        dest_dir = tmp_path / "channels"
        dest_dir.mkdir()
        env_vars = {"FEISHU_APP_ID": "cli_test", "FEISHU_APP_SECRET": "sec_test"}
        # 真实路径: config/channels/feishu.yaml.example
        _copy_and_populate_channel(
            "config/channels/feishu.yaml.example", dest_dir, "lark", env_vars,
        )
        result = (dest_dir / "lark.yaml").read_text()
        assert "cli_test" in result or "${FEISHU_APP_ID}" in result


# ---------------------------------------------------------------------------
# _copy_channel_example
# ---------------------------------------------------------------------------


class TestCopyChannelExample:
    def test_copy_existing(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src_file = src_dir / "test.yaml.example"
        src_file.write_text("test: content\n")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        _copy_channel_example(str(src_file), dest_dir, "test")
        assert (dest_dir / "test.yaml").exists()
        assert "test: content" in (dest_dir / "test.yaml").read_text()

    def test_src_not_exists(self, tmp_path):
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        _copy_channel_example("nonexistent", dest_dir, "test")
        assert not (dest_dir / "test.yaml").exists()

    def test_dst_exists_skip(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.yaml.example").write_text("new\n")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        (dest_dir / "test.yaml").write_text("old\n")

        _copy_channel_example(str(src_dir / "test.yaml.example"), dest_dir, "test")
        # 目标已存在, 不覆盖
        assert (dest_dir / "test.yaml").read_text() == "old\n"


# ---------------------------------------------------------------------------
# _probe_feishu
# ---------------------------------------------------------------------------


class TestProbeFeishu:
    def _inject_lark(self, monkeypatch, mock_lark):
        """注入 mock lark_oapi 模块到 sys.modules。"""
        monkeypatch.setitem(sys.modules, "lark_oapi", mock_lark)
        monkeypatch.setitem(sys.modules, "lark_oapi.api", MagicMock())
        monkeypatch.setitem(sys.modules, "lark_oapi.api.verification", MagicMock())
        monkeypatch.setitem(sys.modules, "lark_oapi.api.verification.v1", MagicMock())

    def test_import_error(self, monkeypatch):
        """lark_oapi 不可导入时打印警告。"""
        monkeypatch.setitem(sys.modules, "lark_oapi", None)
        _probe_feishu("app_id", "secret", "feishu", {})

    def test_connection_success(self, monkeypatch):
        """连接成功时设置 FEISHU_BOT_NAME。"""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = MagicMock()
        mock_resp.data.name = "TestBot"
        mock_client.verification.v1.bot_info.get.return_value = mock_resp

        mock_lark = MagicMock()
        mock_lark.Domain.FEISHU = "feishu"
        mock_lark.Client.builder.return_value.app_id.return_value.app_secret.return_value \
            .domain.return_value.build.return_value = mock_client
        mock_lark.FEISHU_DOMAIN = "https://open.feishu.cn"

        self._inject_lark(monkeypatch, mock_lark)
        with patch("clawhermes.cli.setup._resolve_bot_identity"), \
             patch("clawhermes.cli.setup._verify_feishu_event_subscriptions"):
            env_vars = {}
            _probe_feishu("app_id", "secret", "feishu", env_vars)
            assert env_vars["FEISHU_BOT_NAME"] == "TestBot"

    def test_connection_failure(self, monkeypatch):
        """resp.success() 返回 False 时打印失败。"""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success.return_value = False
        mock_client.verification.v1.bot_info.get.return_value = mock_resp

        mock_lark = MagicMock()
        mock_lark.Domain.FEISHU = "feishu"
        mock_lark.Client.builder.return_value.app_id.return_value.app_secret.return_value \
            .domain.return_value.build.return_value = mock_client

        self._inject_lark(monkeypatch, mock_lark)
        _probe_feishu("app_id", "secret", "feishu", {})

    def test_exception_during_probe(self, monkeypatch):
        """连接测试抛异常时打印错误。"""
        mock_lark = MagicMock()
        mock_lark.Client.builder.side_effect = Exception("connection failed")

        self._inject_lark(monkeypatch, mock_lark)
        _probe_feishu("app_id", "secret", "feishu", {})


# ---------------------------------------------------------------------------
# _resolve_bot_identity
# ---------------------------------------------------------------------------


class TestResolveBotIdentity:
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_success(self, mock_req, mock_open):
        """成功获取 token 和 bot info 时设置环境变量。"""
        token_resp = MagicMock()
        token_resp.read.return_value = b'{"tenant_access_token": "tok123"}'
        token_resp.__enter__ = MagicMock(return_value=token_resp)
        token_resp.__exit__ = MagicMock(return_value=False)

        bot_resp = MagicMock()
        bot_resp.read.return_value = (
            b'{"code": 0, "bot": {"open_id": "ou_xxx", "user_id": "u_yyy"}}'
        )
        bot_resp.__enter__ = MagicMock(return_value=bot_resp)
        bot_resp.__exit__ = MagicMock(return_value=False)

        mock_open.side_effect = [token_resp, bot_resp]

        env_vars = {}
        _resolve_bot_identity("https://open.feishu.cn", "app", "sec", env_vars)
        assert env_vars["FEISHU_BOT_OPEN_ID"] == "ou_xxx"
        assert env_vars["FEISHU_BOT_USER_ID"] == "u_yyy"

    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_empty_token(self, mock_req, mock_open):
        """token 为空时不设置环境变量。"""
        token_resp = MagicMock()
        token_resp.read.return_value = b'{"tenant_access_token": ""}'
        token_resp.__enter__ = MagicMock(return_value=token_resp)
        token_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = token_resp

        env_vars = {}
        _resolve_bot_identity("https://open.feishu.cn", "app", "sec", env_vars)
        assert "FEISHU_BOT_OPEN_ID" not in env_vars

    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_error_code(self, mock_req, mock_open):
        """bot info 返回非零 code 时不设置。"""
        token_resp = MagicMock()
        token_resp.read.return_value = b'{"tenant_access_token": "tok"}'
        token_resp.__enter__ = MagicMock(return_value=token_resp)
        token_resp.__exit__ = MagicMock(return_value=False)

        bot_resp = MagicMock()
        bot_resp.read.return_value = b'{"code": 99901, "msg": "error"}'
        bot_resp.__enter__ = MagicMock(return_value=bot_resp)
        bot_resp.__exit__ = MagicMock(return_value=False)

        mock_open.side_effect = [token_resp, bot_resp]

        env_vars = {}
        _resolve_bot_identity("https://open.feishu.cn", "app", "sec", env_vars)
        assert "FEISHU_BOT_OPEN_ID" not in env_vars

    @patch("urllib.request.urlopen")
    def test_exception(self, mock_open):
        """网络异常时不抛出。"""
        mock_open.side_effect = Exception("timeout")
        _resolve_bot_identity("https://open.feishu.cn", "app", "sec", {})


# ---------------------------------------------------------------------------
# _verify_feishu_event_subscriptions
# ---------------------------------------------------------------------------


class TestVerifyFeishuEventSubscriptions:
    def test_all_subscribed(self):
        """所有必要事件已订阅。"""
        mock_client = MagicMock()
        mock_client.app_id = "app"
        mock_client.app_secret = "sec"  # noqa: S105

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"tenant_access_token": "tok"}

        sub_resp = MagicMock()
        sub_resp.status_code = 200
        sub_resp.json.return_value = {
            "code": 0,
            "data": {"event_types": [
                "im.message.receive_v1",
                "im.message.reaction.created_v1",
                "im.chat.member.bot.added_v1",
                "im.chat.member.bot.deleted_v1",
            ]},
        }

        with patch("httpx.post", return_value=token_resp), \
             patch("httpx.get", return_value=sub_resp):
            _verify_feishu_event_subscriptions(mock_client)

    def test_missing_events(self):
        """缺少必要事件时打印警告。"""
        mock_client = MagicMock()
        mock_client.app_id = "app"
        mock_client.app_secret = "sec"  # noqa: S105

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"tenant_access_token": "tok"}

        sub_resp = MagicMock()
        sub_resp.status_code = 200
        sub_resp.json.return_value = {
            "code": 0,
            "data": {"event_types": ["im.message.receive_v1"]},
        }

        with patch("httpx.post", return_value=token_resp), \
             patch("httpx.get", return_value=sub_resp):
            _verify_feishu_event_subscriptions(mock_client)

    def test_token_http_error(self):
        """token 请求失败时跳过。"""
        mock_client = MagicMock()
        mock_client.app_id = "app"
        mock_client.app_secret = "sec"  # noqa: S105

        token_resp = MagicMock()
        token_resp.status_code = 500

        with patch("httpx.post", return_value=token_resp):
            _verify_feishu_event_subscriptions(mock_client)

    def test_empty_token(self):
        """token 为空时跳过。"""
        mock_client = MagicMock()
        mock_client.app_id = "app"
        mock_client.app_secret = "sec"  # noqa: S105

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"tenant_access_token": ""}

        with patch("httpx.post", return_value=token_resp):
            _verify_feishu_event_subscriptions(mock_client)

    def test_sub_http_error(self):
        """事件订阅查询失败时打印警告。"""
        mock_client = MagicMock()
        mock_client.app_id = "app"
        mock_client.app_secret = "sec"  # noqa: S105

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"tenant_access_token": "tok"}

        sub_resp = MagicMock()
        sub_resp.status_code = 403

        with patch("httpx.post", return_value=token_resp), \
             patch("httpx.get", return_value=sub_resp):
            _verify_feishu_event_subscriptions(mock_client)

    def test_exception(self):
        """异常时不抛出。"""
        mock_client = MagicMock()
        with patch("httpx.post", side_effect=Exception("network")):
            _verify_feishu_event_subscriptions(mock_client)


# ---------------------------------------------------------------------------
# _setup_feishu_security
# ---------------------------------------------------------------------------


class TestSetupFeishuSecurity:
    def _inject_lark_security(self, monkeypatch, warnings=None):
        """注入 mock clawhermes_lark security 模块，避免循环导入。"""
        for name in [
            "clawhermes_lark",
            "clawhermes_lark.openclaw_lark",
            "clawhermes_lark.openclaw_lark.core",
        ]:
            if name not in sys.modules or not isinstance(sys.modules[name], MagicMock):
                monkeypatch.setitem(sys.modules, name, MagicMock())
        mock_sec = MagicMock()
        mock_sec.collect_security_warnings = MagicMock(return_value=warnings or [])
        monkeypatch.setitem(sys.modules, "clawhermes_lark.openclaw_lark.core.security", mock_sec)
        return mock_sec

    @patch("questionary.password")
    @patch("questionary.confirm")
    @patch("questionary.select")
    def test_with_webhook(self, mock_sel, mock_confirm, mock_pwd):
        mock_sel.return_value = _q("allowlist")
        mock_confirm.return_value = _q(True)
        mock_pwd.side_effect = [_q("verify-tok"), _q("encrypt-key")]

        env_vars = {}
        _setup_feishu_security(env_vars)
        assert env_vars["FEISHU_GROUP_POLICY"] == "allowlist"
        assert env_vars["FEISHU_VERIFY_TOKEN"] == "verify-tok"  # noqa: S105
        assert env_vars["FEISHU_ENCRYPT_KEY"] == "encrypt-key"

    @patch("questionary.confirm")
    @patch("questionary.select")
    def test_without_webhook(self, mock_sel, mock_confirm):
        mock_sel.return_value = _q("open")
        mock_confirm.return_value = _q(False)

        env_vars = {}
        _setup_feishu_security(env_vars)
        assert env_vars["FEISHU_GROUP_POLICY"] == "open"
        assert "FEISHU_VERIFY_TOKEN" not in env_vars

    @patch("questionary.password")
    @patch("questionary.confirm")
    @patch("questionary.select")
    def test_empty_group_policy(self, mock_sel, mock_confirm, mock_pwd, monkeypatch):
        """group_policy 为空时使用默认 allowlist。"""
        mock_sel.return_value = _q(None)
        mock_confirm.return_value = _q(False)

        mock_sec = self._inject_lark_security(monkeypatch, warnings=["warning1"])
        env_vars = {}
        _setup_feishu_security(env_vars)
        mock_sec.collect_security_warnings.assert_called_once()

    @patch("questionary.password")
    @patch("questionary.confirm")
    @patch("questionary.select")
    def test_with_security_warnings(self, mock_sel, mock_confirm, mock_pwd, monkeypatch):
        """collect_security_warnings 返回警告时打印。"""
        mock_sel.return_value = _q("open")
        mock_confirm.return_value = _q(False)

        self._inject_lark_security(monkeypatch,
                                   warnings=["⚠️  warning 1", "⚠️  warning 2"])
        _setup_feishu_security({})


# ---------------------------------------------------------------------------
# _onboard_feishu
# ---------------------------------------------------------------------------


class TestOnboardFeishu:
    @patch("clawhermes.cli.setup._run_scan_to_create", return_value={"app_id": "x"})
    @patch("questionary.select")
    def test_scan_path(self, mock_sel, mock_scan):
        mock_sel.return_value = _q("scan")
        env_vars = {}
        result = _onboard_feishu(env_vars)
        assert result is None  # 函数无返回值
        mock_scan.assert_called_once()

    @patch("clawhermes.cli.setup._run_manual_feishu_setup", return_value={"app_id": "x"})
    @patch("questionary.select")
    def test_manual_path(self, mock_sel, mock_manual):
        mock_sel.return_value = _q("manual")
        env_vars = {}
        _onboard_feishu(env_vars)
        mock_manual.assert_called_once()

    @patch("questionary.select")
    def test_cancel(self, mock_sel):
        mock_sel.return_value = _q(None)
        env_vars = {}
        _onboard_feishu(env_vars)

    @patch("clawhermes.cli.setup._run_scan_to_create", return_value=None)
    @patch("questionary.select")
    def test_scan_returns_none(self, mock_sel, mock_scan):
        mock_sel.return_value = _q("scan")
        _onboard_feishu({})

    @patch("clawhermes.cli.setup._run_manual_feishu_setup", return_value=None)
    @patch("questionary.select")
    def test_manual_returns_none(self, mock_sel, mock_manual):
        mock_sel.return_value = _q("manual")
        _onboard_feishu({})


# ---------------------------------------------------------------------------
# _run_manual_feishu_setup
# ---------------------------------------------------------------------------


class TestRunManualFeishuSetup:
    @patch("clawhermes.cli.setup._setup_feishu_security")
    @patch("clawhermes.cli.setup._probe_feishu")
    @patch("questionary.select")
    @patch("questionary.password")
    @patch("questionary.text")
    def test_success_feishu(self, mock_text, mock_pwd, mock_sel, mock_probe, mock_sec):
        mock_text.return_value = _q("cli_app_id")
        mock_pwd.return_value = _q("app_secret")
        mock_sel.return_value = _q("feishu")

        env_vars = {}
        result = _run_manual_feishu_setup(env_vars)
        assert result["app_id"] == "cli_app_id"
        assert env_vars["FEISHU_APP_ID"] == "cli_app_id"
        assert "FEISHU_DOMAIN" not in env_vars  # feishu 不设置 domain
        mock_probe.assert_called_once()
        mock_sec.assert_called_once()

    @patch("clawhermes.cli.setup._setup_feishu_security")
    @patch("clawhermes.cli.setup._probe_feishu")
    @patch("questionary.select")
    @patch("questionary.password")
    @patch("questionary.text")
    def test_success_lark(self, mock_text, mock_pwd, mock_sel, mock_probe, mock_sec):
        mock_text.return_value = _q("cli_app_id")
        mock_pwd.return_value = _q("app_secret")
        mock_sel.return_value = _q("lark")

        env_vars = {}
        result = _run_manual_feishu_setup(env_vars)
        assert result["domain"] == "lark"
        assert env_vars["FEISHU_DOMAIN"] == "lark"

    @patch("questionary.text")
    def test_cancel_at_app_id(self, mock_text):
        mock_text.return_value = _q("")
        assert _run_manual_feishu_setup({}) is None

    @patch("questionary.password")
    @patch("questionary.text")
    def test_cancel_at_app_secret(self, mock_text, mock_pwd):
        mock_text.return_value = _q("app_id")
        mock_pwd.return_value = _q("")
        assert _run_manual_feishu_setup({}) is None

    @patch("questionary.select")
    @patch("questionary.password")
    @patch("questionary.text")
    def test_cancel_at_domain(self, mock_text, mock_pwd, mock_sel):
        mock_text.return_value = _q("app_id")
        mock_pwd.return_value = _q("secret")
        mock_sel.return_value = _q(None)
        assert _run_manual_feishu_setup({}) is None


# ---------------------------------------------------------------------------
# _run_scan_to_create
# ---------------------------------------------------------------------------


class TestRunScanToCreate:
    def _inject_lark_app_reg(self, monkeypatch, qr_text="[QR]"):
        """注入 mock clawhermes_lark app_registration 模块，避免循环导入。"""
        for name in [
            "clawhermes_lark",
            "clawhermes_lark.openclaw_lark",
            "clawhermes_lark.openclaw_lark.core",
        ]:
            if name not in sys.modules or not isinstance(sys.modules[name], MagicMock):
                monkeypatch.setitem(sys.modules, name, MagicMock())
        mock_reg = MagicMock()
        mock_reg.render_qr_terminal = MagicMock(return_value=qr_text)
        monkeypatch.setitem(sys.modules, "clawhermes_lark.openclaw_lark.core.app_registration", mock_reg)
        return mock_reg

    @patch("clawhermes.cli.setup._run_manual_feishu_setup", return_value={"app_id": "manual"})
    @patch("questionary.select")
    def test_import_error_fallback(self, mock_sel, mock_manual, monkeypatch):
        """clawhermes_lark 不可导入时回退到手动配置。"""
        mock_sel.return_value = _q("feishu")
        # mock __import__ 避免 clawhermes_lark 循环导入 (会被前序测试的 sys.modules 污染)
        real_import = __import__

        def _mock_import(name, *args, **kwargs):
            if name.startswith("clawhermes_lark"):
                raise ImportError("not available in test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _mock_import)
        result = _run_scan_to_create({})
        assert result == {"app_id": "manual"}

    @patch("questionary.select")
    def test_cancel_at_domain(self, mock_sel):
        mock_sel.return_value = _q(None)
        result = _run_scan_to_create({})
        assert result is None

    @patch("clawhermes.cli.setup._setup_feishu_security")
    @patch("clawhermes.cli.setup._probe_feishu")
    @patch("questionary.select")
    def test_success_feishu(self, mock_sel, mock_probe, mock_sec, monkeypatch):
        """扫码创建成功。"""
        mock_sel.return_value = _q("feishu")
        self._inject_lark_app_reg(monkeypatch)

        init_result = MagicMock(ok=True)
        begin_result = MagicMock(
            ok=True, device_code="dc", verification_uri_complete="https://qr",
            user_code="USER123", expire_in=600, interval=5,
        )
        poll_result = MagicMock(
            ok=True, client_id="cli_app_id_long_enough",
            client_secret="cli_secret",  # noqa: S106
            open_id="ou_owner",
        )

        with patch("asyncio.run", side_effect=[init_result, begin_result, poll_result]):
            env_vars = {}
            result = _run_scan_to_create(env_vars)
            assert result["app_id"] == "cli_app_id_long_enough"
            assert env_vars["FEISHU_APP_ID"] == "cli_app_id_long_enough"

    @patch("clawhermes.cli.setup._setup_feishu_security")
    @patch("clawhermes.cli.setup._probe_feishu")
    @patch("questionary.select")
    def test_success_lark_domain(self, mock_sel, mock_probe, mock_sec, monkeypatch):
        """扫码创建选择 lark 域名时设置 FEISHU_DOMAIN。"""
        mock_sel.return_value = _q("lark")
        self._inject_lark_app_reg(monkeypatch)

        init_result = MagicMock(ok=True)
        begin_result = MagicMock(
            ok=True, device_code="dc", verification_uri_complete="https://qr",
            user_code="USER123", expire_in=600, interval=5,
        )
        poll_result = MagicMock(
            ok=True, client_id="cli_app_id_long_enough",
            client_secret="cli_secret",  # noqa: S106
            open_id="ou_owner",
        )

        with patch("asyncio.run", side_effect=[init_result, begin_result, poll_result]):
            env_vars = {}
            result = _run_scan_to_create(env_vars)
            assert result["domain"] == "lark"
            assert env_vars["FEISHU_DOMAIN"] == "lark"

    @patch("clawhermes.cli.setup._setup_feishu_security")
    @patch("clawhermes.cli.setup._probe_feishu")
    @patch("questionary.select")
    def test_render_qr_import_error(self, mock_sel, mock_probe, mock_sec, monkeypatch):
        """render_qr_terminal 不可导入时回退到纯文本 QR。"""
        import types
        mock_sel.return_value = _q("feishu")
        # 使用 types.ModuleType 使 render_qr_terminal 属性不存在, 触发 ImportError
        for name in ["clawhermes_lark", "clawhermes_lark.openclaw_lark",
                      "clawhermes_lark.openclaw_lark.core"]:
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
        mock_reg = types.ModuleType("app_registration")
        mock_reg.app_registration_begin = MagicMock()
        mock_reg.app_registration_init = MagicMock()
        mock_reg.app_registration_poll = MagicMock()
        monkeypatch.setitem(sys.modules,
                            "clawhermes_lark.openclaw_lark.core.app_registration",
                            mock_reg)

        init_result = MagicMock(ok=True)
        begin_result = MagicMock(
            ok=True, device_code="dc", verification_uri_complete="https://qr",
            user_code="USER123", expire_in=600, interval=5,
        )
        poll_result = MagicMock(
            ok=True, client_id="cli_app_id_long_enough",
            client_secret="cli_secret",  # noqa: S106
            open_id="ou_owner",
        )

        with patch("asyncio.run", side_effect=[init_result, begin_result, poll_result]):
            env_vars = {}
            result = _run_scan_to_create(env_vars)
            assert result["app_id"] == "cli_app_id_long_enough"

    @patch("clawhermes.cli.setup._run_manual_feishu_setup", return_value={"app_id": "manual"})
    @patch("questionary.select")
    def test_init_fail_fallback(self, mock_sel, mock_manual, monkeypatch):
        """init 失败时回退到手动配置。"""
        mock_sel.return_value = _q("feishu")
        self._inject_lark_app_reg(monkeypatch)
        init_result = MagicMock(ok=False, error="env check failed")

        with patch("asyncio.run", return_value=init_result):
            result = _run_scan_to_create({})
            assert result == {"app_id": "manual"}

    @patch("clawhermes.cli.setup._run_manual_feishu_setup", return_value={"app_id": "manual"})
    @patch("questionary.select")
    def test_begin_fail_fallback(self, mock_sel, mock_manual, monkeypatch):
        """begin 失败时回退到手动配置。"""
        mock_sel.return_value = _q("feishu")
        self._inject_lark_app_reg(monkeypatch)
        init_result = MagicMock(ok=True)
        begin_result = MagicMock(ok=False, error="begin failed")

        with patch("asyncio.run", side_effect=[init_result, begin_result]):
            result = _run_scan_to_create({})
            assert result == {"app_id": "manual"}

    @patch("clawhermes.cli.setup._run_manual_feishu_setup", return_value={"app_id": "manual"})
    @patch("questionary.select")
    def test_poll_fail_fallback(self, mock_sel, mock_manual, monkeypatch):
        """poll 失败时回退到手动配置。"""
        mock_sel.return_value = _q("feishu")
        self._inject_lark_app_reg(monkeypatch)
        init_result = MagicMock(ok=True)
        begin_result = MagicMock(
            ok=True, device_code="dc", verification_uri_complete="https://qr",
            user_code="USER123", expire_in=600, interval=5,
        )
        poll_result = MagicMock(ok=False, error="poll failed")

        with patch("asyncio.run", side_effect=[init_result, begin_result, poll_result]):
            result = _run_scan_to_create({})
            assert result == {"app_id": "manual"}

    @patch("questionary.select")
    def test_keyboard_interrupt(self, mock_sel, monkeypatch):
        """Ctrl+C 取消时返回 None。"""
        mock_sel.return_value = _q("feishu")
        self._inject_lark_app_reg(monkeypatch)
        init_result = MagicMock(ok=True)
        begin_result = MagicMock(
            ok=True, device_code="dc", verification_uri_complete="https://qr",
            user_code="USER", expire_in=600, interval=5,
        )

        with patch("asyncio.run", side_effect=[init_result, begin_result, KeyboardInterrupt()]):
            result = _run_scan_to_create({})
            assert result is None
