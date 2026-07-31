"""
ClawHermes - 渠道配置加载器测试

覆盖 channel/config.py 全部分支：
- _resolve_env_ref() str/dict/list/其他类型
- ${VAR} / ${VAR:-default} 解析
- load_channel_config() 无运行时文件 / 有运行时文件 / 非 dict
- build_adapter_config() 移除元数据字段
- _CHANNEL_DEFAULTS 各渠道默认值
"""
from __future__ import annotations

from clawhermes.channel.config import (
    _CHANNEL_DEFAULTS,
    _resolve_env_ref,
    build_adapter_config,
    load_channel_config,
)

# ============================================================
# _resolve_env_ref — str 类型
# ============================================================


class TestResolveEnvRefString:
    def test_str_without_env_ref_returns_as_is(self):
        """无 ${VAR} 引用的字符串应原样返回"""
        assert _resolve_env_ref("plain text") == "plain text"

    def test_str_with_env_ref_resolves(self, monkeypatch):
        """${VAR} 引用应被环境变量值替换"""
        monkeypatch.setenv("MY_TEST_VAR", "resolved_value")
        assert _resolve_env_ref("${MY_TEST_VAR}") == "resolved_value"

    def test_str_with_env_ref_in_text(self, monkeypatch):
        """${VAR} 在文本中间应被替换"""
        monkeypatch.setenv("NAME", "world")
        assert _resolve_env_ref("hello ${NAME}!") == "hello world!"

    def test_str_with_multiple_env_refs(self, monkeypatch):
        """多个 ${VAR} 引用应都被替换"""
        monkeypatch.setenv("A", "foo")
        monkeypatch.setenv("B", "bar")
        assert _resolve_env_ref("${A}-${B}") == "foo-bar"

    def test_str_with_default_when_env_missing(self, monkeypatch):
        """${VAR:-default} 在 VAR 未设置时应使用 default"""
        monkeypatch.delenv("MISSING_VAR_XYZ", raising=False)
        assert _resolve_env_ref("${MISSING_VAR_XYZ:-fallback}") == "fallback"

    def test_str_with_default_when_env_set(self, monkeypatch):
        """${VAR:-default} 在 VAR 设置时应使用 VAR 值"""
        monkeypatch.setenv("EXISTING_VAR", "actual")
        assert _resolve_env_ref("${EXISTING_VAR:-fallback}") == "actual"

    def test_str_env_missing_no_default_returns_literal(self, monkeypatch):
        """${VAR} 在 VAR 未设置且无 default 时应保留原文字"""
        monkeypatch.delenv("TOTALLY_MISSING_VAR", raising=False)
        assert _resolve_env_ref("${TOTALLY_MISSING_VAR}") == "${TOTALLY_MISSING_VAR}"

    def test_str_default_with_spaces(self, monkeypatch):
        """${VAR:-default} 中 default 含空格应被 strip"""
        monkeypatch.delenv("MISSING_VAR_SP", raising=False)
        # 注意：default 部分在正则中是 \s*[^}]*  → 捕获时会包含前导空格
        # 实现 default.strip() 应去掉首尾空白
        assert _resolve_env_ref("${MISSING_VAR_SP:-  spaced_default  }") == "spaced_default"

    def test_str_default_empty_string(self, monkeypatch):
        """${VAR:-} default 为空字符串时应返回空"""
        monkeypatch.delenv("MISSING_VAR_EMPTY", raising=False)
        # ${VAR:-} → default = '' → 返回 ''
        # 但 default = None when group(2) matches '\s*[^}]*' 取空字符串 → 不是 None
        # 实际：default is not None 时 str(default).strip() = ''
        result = _resolve_env_ref("${MISSING_VAR_EMPTY:-}")
        assert result == ""


# ============================================================
# _resolve_env_ref — dict 类型
# ============================================================


class TestResolveEnvRefDict:
    def test_dict_recursively_resolves_values(self, monkeypatch):
        """dict 中的字符串值应被递归解析"""
        monkeypatch.setenv("K", "v")
        d = {"a": "${K}", "b": "plain"}
        result = _resolve_env_ref(d)
        assert result == {"a": "v", "b": "plain"}

    def test_dict_nested_dict(self, monkeypatch):
        """嵌套 dict 应递归解析"""
        monkeypatch.setenv("INNER", "value")
        d = {"outer": {"inner": "${INNER}"}}
        result = _resolve_env_ref(d)
        assert result == {"outer": {"inner": "value"}}

    def test_dict_with_non_string_values(self):
        """dict 中非字符串值应原样返回"""
        d = {"a": 123, "b": True, "c": None}
        result = _resolve_env_ref(d)
        assert result == {"a": 123, "b": True, "c": None}

    def test_empty_dict(self):
        """空 dict 应原样返回"""
        assert _resolve_env_ref({}) == {}


# ============================================================
# _resolve_env_ref — list 类型
# ============================================================


class TestResolveEnvRefList:
    def test_list_recursively_resolves_items(self, monkeypatch):
        """list 中的字符串项应被递归解析"""
        monkeypatch.setenv("ITEM", "resolved")
        lst = ["${ITEM}", "plain"]
        result = _resolve_env_ref(lst)
        assert result == ["resolved", "plain"]

    def test_list_with_nested_dict(self, monkeypatch):
        """list 中嵌套 dict 应递归解析"""
        monkeypatch.setenv("V", "val")
        lst = [{"k": "${V}"}, "plain"]
        result = _resolve_env_ref(lst)
        assert result == [{"k": "val"}, "plain"]

    def test_list_with_non_string_items(self):
        """list 中非字符串项应原样返回"""
        lst = [1, True, None]
        result = _resolve_env_ref(lst)
        assert result == [1, True, None]

    def test_empty_list(self):
        """空 list 应原样返回"""
        assert _resolve_env_ref([]) == []


# ============================================================
# _resolve_env_ref — 其他类型
# ============================================================


class TestResolveEnvRefOther:
    def test_int_returns_as_is(self):
        """int 类型应原样返回"""
        assert _resolve_env_ref(42) == 42

    def test_bool_returns_as_is(self):
        """bool 类型应原样返回"""
        assert _resolve_env_ref(True) is True

    def test_none_returns_as_is(self):
        """None 应原样返回"""
        assert _resolve_env_ref(None) is None

    def test_float_returns_as_is(self):
        """float 类型应原样返回"""
        assert _resolve_env_ref(3.14) == 3.14


# ============================================================
# _CHANNEL_DEFAULTS
# ============================================================


class TestChannelDefaults:
    def test_feishu_defaults(self):
        """feishu 渠道应有完整默认值"""
        feishu = _CHANNEL_DEFAULTS["feishu"]
        assert feishu["domain"] == "feishu"
        assert feishu["connection_mode"] == "websocket"
        assert feishu["group_policy"] == "open"
        assert feishu["require_mention"] is True
        assert feishu["webhook_port"] == 8080

    def test_wechat_defaults(self):
        """wechat 渠道应有 sub_type 默认值"""
        wechat = _CHANNEL_DEFAULTS["wechat"]
        assert wechat["sub_type"] == "personal"

    def test_qq_defaults(self):
        """qq 渠道应有 sandbox/auto_reconnect 默认值"""
        qq = _CHANNEL_DEFAULTS["qq"]
        assert qq["sandbox"] is True
        assert qq["auto_reconnect"] is True
        assert qq["max_retries"] == 3

    def test_unknown_channel_no_defaults(self):
        """未知渠道默认值为空 dict"""
        assert _CHANNEL_DEFAULTS.get("unknown_channel") is None


# ============================================================
# load_channel_config
# ============================================================


class TestLoadChannelConfig:
    def test_load_feishu_no_runtime_file_uses_defaults(self, tmp_path, monkeypatch):
        """无运行时配置文件时应使用内置默认值"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        config = load_channel_config("feishu")
        # 应包含默认值
        assert config["domain"] == "feishu"
        assert config["connection_mode"] == "websocket"
        # 无 app_id（默认值不包含）
        assert "app_id" not in config

    def test_load_unknown_channel_no_runtime_file(self, tmp_path, monkeypatch):
        """未知渠道无运行时文件时应返回空 dict"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        config = load_channel_config("unknown_channel")
        assert config == {}

    def test_load_with_runtime_file_overrides_defaults(self, tmp_path, monkeypatch):
        """运行时配置文件应覆盖默认值"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        # 写入 feishu.yaml 覆盖部分字段
        yaml_content = """
domain: lark
connection_mode: webhook
app_id: cli_xxx
app_secret: secret_xxx
"""
        (channels_dir / "feishu.yaml").write_text(yaml_content)
        config = load_channel_config("feishu")
        # 覆盖的字段
        assert config["domain"] == "lark"
        assert config["connection_mode"] == "webhook"
        assert config["app_id"] == "cli_xxx"
        # 未覆盖的字段保留默认值
        assert config["require_mention"] is True

    def test_load_with_env_var_interpolation(self, tmp_path, monkeypatch):
        """运行时配置文件中的 ${VAR} 应被环境变量替换"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("FEISHU_APP_ID", "env_app_id")
        monkeypatch.setenv("FEISHU_APP_SECRET", "env_secret")

        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        yaml_content = """
app_id: ${FEISHU_APP_ID}
app_secret: ${FEISHU_APP_SECRET}
"""
        (channels_dir / "feishu.yaml").write_text(yaml_content)
        config = load_channel_config("feishu")
        assert config["app_id"] == "env_app_id"
        assert config["app_secret"] == "env_secret"  # noqa: S105  测试用值

    def test_load_with_env_var_default(self, tmp_path, monkeypatch):
        """${VAR:-default} 在 VAR 未设置时应使用 default"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("UNSET_CFG_VAR", raising=False)

        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        yaml_content = """
app_id: ${UNSET_CFG_VAR:-default_app_id}
"""
        (channels_dir / "feishu.yaml").write_text(yaml_content)
        config = load_channel_config("feishu")
        assert config["app_id"] == "default_app_id"

    def test_load_with_empty_runtime_file_uses_defaults(self, tmp_path, monkeypatch):
        """空的运行时配置文件应使用默认值"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        (channels_dir / "feishu.yaml").write_text("")
        config = load_channel_config("feishu")
        # 空文件 → loaded = {} → 不 update → 保留默认值
        assert config["domain"] == "feishu"

    def test_load_with_non_dict_runtime_file_uses_defaults(self, tmp_path, monkeypatch):
        """非 dict 的运行时配置文件应使用默认值"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        # 写入 list 而非 dict
        (channels_dir / "feishu.yaml").write_text("- item1\n- item2\n")
        config = load_channel_config("feishu")
        # 非 dict → 跳过 update → 保留默认值
        assert config["domain"] == "feishu"

    def test_load_unknown_channel_with_runtime_file(self, tmp_path, monkeypatch):
        """未知渠道但有运行时文件时应使用文件内容"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        yaml_content = """
custom_field: custom_value
"""
        (channels_dir / "custom_channel.yaml").write_text(yaml_content)
        config = load_channel_config("custom_channel")
        assert config.get("custom_field") == "custom_value"


# ============================================================
# build_adapter_config
# ============================================================


class TestBuildAdapterConfig:
    def test_build_removes_metadata_fields(self, tmp_path, monkeypatch):
        """build_adapter_config 应移除 channel_type/enabled/routing/comment 字段"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        yaml_content = """
channel_type: feishu
enabled: true
routing: direct
comment: this is a comment
app_id: cli_xxx
"""
        (channels_dir / "feishu.yaml").write_text(yaml_content)
        adapter_cfg = build_adapter_config("feishu")
        # 元数据字段应被移除
        assert "channel_type" not in adapter_cfg
        assert "enabled" not in adapter_cfg
        assert "routing" not in adapter_cfg
        assert "comment" not in adapter_cfg
        # 业务字段应保留
        assert adapter_cfg["app_id"] == "cli_xxx"

    def test_build_keeps_business_fields(self, tmp_path, monkeypatch):
        """build_adapter_config 应保留业务字段"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        adapter_cfg = build_adapter_config("feishu")
        # 默认值中的业务字段应保留
        assert "domain" in adapter_cfg
        assert "connection_mode" in adapter_cfg
        assert "webhook_port" in adapter_cfg

    def test_build_with_env_interpolation(self, tmp_path, monkeypatch):
        """build_adapter_config 应支持 ${VAR} 插值"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("APP_ID_ENV", "from_env")
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        yaml_content = """
app_id: ${APP_ID_ENV}
"""
        (channels_dir / "feishu.yaml").write_text(yaml_content)
        adapter_cfg = build_adapter_config("feishu")
        assert adapter_cfg["app_id"] == "from_env"

    def test_build_unknown_channel_returns_empty(self, tmp_path, monkeypatch):
        """未知渠道的 build_adapter_config 应返回空 dict（无元数据字段可移除）"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        adapter_cfg = build_adapter_config("totally_unknown")
        # 未知渠道无默认值，无运行时文件 → 空 dict
        assert adapter_cfg == {}


# ============================================================
# load_channel_config TypeError 路径
# ============================================================


class TestLoadChannelConfigTypeError:
    def test_load_returns_dict_type_check_passes(self, tmp_path, monkeypatch):
        """load_channel_config 返回 dict 时不抛 TypeError"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        # 正常情况下 resolved 是 dict，不会抛 TypeError
        config = load_channel_config("feishu")
        assert isinstance(config, dict)

    def test_load_with_corrupted_yaml_uses_defaults(self, tmp_path, monkeypatch):
        """损坏的 YAML 文件应使用默认值（load_yaml 容错返回空 dict）"""
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        channels_dir = tmp_path / "channels"
        channels_dir.mkdir()
        # 写入语法错误的 YAML
        (channels_dir / "feishu.yaml").write_text("{invalid yaml: [unclosed")
        config = load_channel_config("feishu")
        # load_yaml 容错返回 {} → 不 update → 保留默认值
        assert config["domain"] == "feishu"
