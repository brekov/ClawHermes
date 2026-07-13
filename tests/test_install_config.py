"""
配置模块测试 — corrupt backup, env var safety, get_data_dir
"""
from __future__ import annotations

import yaml


class TestGetDataDir:
    def test_default(self):
        from clawhermes.config import get_data_dir
        d = get_data_dir()
        assert d.name == ".clawhermes"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", "/tmp/test_clawhome")
        from clawhermes.config import get_data_dir
        assert str(get_data_dir()) == "/tmp/test_clawhome"


class TestEnvVarSafety:
    def test_safe_vars(self):
        from clawhermes.config import is_env_var_safe
        assert is_env_var_safe("DEEPSEEK_API_KEY") is True
        assert is_env_var_safe("FEISHU_APP_ID") is True
        assert is_env_var_safe("CH_LLM_DEFAULT_MODEL") is True
        assert is_env_var_safe("GATEWAY_SECRET") is True

    def test_blocked_vars(self):
        from clawhermes.config import is_env_var_safe
        assert is_env_var_safe("LD_PRELOAD") is False
        assert is_env_var_safe("LD_LIBRARY_PATH") is False
        assert is_env_var_safe("LD_AUDIT") is False
        assert is_env_var_safe("DYLD_INSERT_LIBRARIES") is False
        assert is_env_var_safe("DYLD_LIBRARY_PATH") is False
        assert is_env_var_safe("PYTHONPATH") is False
        assert is_env_var_safe("PYTHONHOME") is False
        assert is_env_var_safe("PATH") is False

    def test_case_insensitive(self):
        from clawhermes.config import is_env_var_safe
        assert is_env_var_safe("ld_preload") is False
        assert is_env_var_safe("Ld_Preload") is False


class TestYamlLoad:
    def test_valid_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.config import load_yaml
        cfg = {"llm": {"model": "deepseek/deepseek-chat"}, "gateway": {"host": "127.0.0.1"}}
        (tmp_path / "config.yaml").write_text(yaml.dump(cfg))
        loaded = load_yaml()
        assert loaded["llm"]["model"] == "deepseek/deepseek-chat"

    def test_corrupt_yaml_no_crash(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.config import load_yaml
        (tmp_path / "config.yaml").write_text("{bad: yaml: : [}")
        loaded = load_yaml()
        assert loaded == {}

    def test_corrupt_yaml_creates_backup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.config import load_yaml
        (tmp_path / "config.yaml").write_text("{bad: yaml: : [}")
        load_yaml()
        # A backup should have been created
        backups = list(tmp_path.glob("config.yaml.corrupt.*.bak"))
        assert len(backups) >= 1

    def test_empty_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.config import load_yaml
        (tmp_path / "config.yaml").write_text("")
        loaded = load_yaml()
        assert loaded == {}

    def test_missing_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path / "nonexist"))
        from clawhermes.config import load_yaml
        loaded = load_yaml()
        assert loaded == {}


class TestYamlSave:
    def test_save_and_reload(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        from clawhermes.config import load_yaml, save_yaml
        cfg = {"test": "hello", "nested": {"key": "value"}}
        save_yaml(cfg)
        loaded = load_yaml()
        assert loaded["test"] == "hello"
        assert loaded["nested"]["key"] == "value"

    def test_default_yaml_structure(self):
        from clawhermes.config import default_yaml
        cfg = default_yaml()
        assert "agent" in cfg
        assert "gateway" in cfg
        assert "llm" in cfg
        assert "tools" in cfg
        assert cfg["gateway"]["port"] == 18789
