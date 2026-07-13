"""
ClawHermes - agent_mgr 模块测试

覆盖 AgentManager 的注册、查询、删除、多 agent 管理、CLI 命令等功能。
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from clawhermes.agent import agent_mgr


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """每个测试使用独立的数据目录，避免污染真实 ~/.clawhermes"""
    monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
    yield


class TestAgentsDir:
    def test_get_agents_dir_creates_directory(self, tmp_path):
        agents_dir = agent_mgr.get_agents_dir()
        assert agents_dir.exists()
        assert agents_dir.name == "agents"

    def test_get_agents_dir_under_data_dir(self, tmp_path):
        agents_dir = agent_mgr.get_agents_dir()
        assert agents_dir.parent == tmp_path


class TestDefaultAgent:
    def test_get_default_agent_returns_default_when_no_file(self):
        assert agent_mgr.get_default_agent() == "default"

    def test_set_and_get_default_agent(self):
        agent_mgr.set_default_agent("custom_agent")
        assert agent_mgr.get_default_agent() == "custom_agent"

    def test_set_default_agent_overwrites(self):
        agent_mgr.set_default_agent("first")
        agent_mgr.set_default_agent("second")
        assert agent_mgr.get_default_agent() == "second"


class TestListAgents:
    def test_list_agents_empty(self):
        assert agent_mgr.list_agents() == []

    def test_list_agents_after_create(self):
        agent_mgr.create_agent("alpha")
        agent_mgr.create_agent("beta")
        agents = agent_mgr.list_agents()
        assert agents == ["alpha", "beta"]

    def test_list_agents_sorted(self):
        agent_mgr.create_agent("zeta")
        agent_mgr.create_agent("alpha")
        agent_mgr.create_agent("mid")
        agents = agent_mgr.list_agents()
        assert agents == ["alpha", "mid", "zeta"]


class TestAgentPath:
    def test_agent_path(self):
        path = agent_mgr.agent_path("test_agent")
        assert path.name == "test_agent"
        assert path.parent.name == "agents"

    def test_agent_exists_false(self):
        assert agent_mgr.agent_exists("nope") is False

    def test_agent_exists_true_after_create(self):
        agent_mgr.create_agent("real")
        assert agent_mgr.agent_exists("real") is True


class TestCreateAgent:
    def test_create_agent_new(self):
        path = agent_mgr.create_agent("newbie")
        assert path.exists()
        assert (path / "SOUL.md").exists()
        assert (path / "AGENTS.md").exists()
        assert (path / "USER.md").exists()
        assert (path / "config.json").exists()

    def test_create_agent_persona_content(self):
        path = agent_mgr.create_agent("persona_test")
        soul = (path / "SOUL.md").read_text()
        assert "persona_test" in soul

    def test_create_agent_instructions_content(self):
        path = agent_mgr.create_agent("instr_test")
        agents_md = (path / "AGENTS.md").read_text()
        assert "中文" in agents_md

    def test_create_agent_config_json(self):
        path = agent_mgr.create_agent("cfg_test")
        cfg = json.loads((path / "config.json").read_text())
        assert cfg["model"] == "deepseek/deepseek-chat"
        assert cfg["temperature"] == 0.7
        assert cfg["max_iterations"] == 50

    def test_create_agent_config_uses_env_model(self, monkeypatch):
        monkeypatch.setenv("CH_DEFAULT_MODEL", "custom/model-x")
        path = agent_mgr.create_agent("env_model_test")
        cfg = json.loads((path / "config.json").read_text())
        assert cfg["model"] == "custom/model-x"

    def test_create_agent_already_exists_returns_same_path(self):
        path1 = agent_mgr.create_agent("dup")
        path2 = agent_mgr.create_agent("dup")
        assert path1 == path2

    def test_create_agent_clone_from(self):
        agent_mgr.create_agent("source")
        agent_mgr.write_persona("source", "源身份")
        agent_mgr.write_instructions("source", "源指令")

        clone_path = agent_mgr.create_agent("copy", clone_from="source")
        assert clone_path.exists()
        assert "源身份" in (clone_path / "SOUL.md").read_text()
        assert "源指令" in (clone_path / "AGENTS.md").read_text()

    def test_create_agent_clone_from_nonexistent_fallback(self):
        """clone_from 指向不存在的 agent → 走新建分支"""
        path = agent_mgr.create_agent("orphan", clone_from="ghost")
        assert path.exists()
        assert (path / "SOUL.md").exists()


class TestDeleteAgent:
    def test_delete_agent_not_exists(self):
        # 不存在时不应抛异常
        agent_mgr.delete_agent("ghost")

    def test_delete_agent_default_protected(self):
        agent_mgr.create_agent("default")
        # default 不能删除（Confirm 不会触发 rmtree）
        with patch("rich.prompt.Confirm.ask", return_value=True):
            agent_mgr.delete_agent("default")
        assert agent_mgr.agent_exists("default") is True

    def test_delete_agent_confirmed(self):
        agent_mgr.create_agent("deletable")
        with patch("rich.prompt.Confirm.ask", return_value=True):
            agent_mgr.delete_agent("deletable")
        assert agent_mgr.agent_exists("deletable") is False

    def test_delete_agent_declined(self):
        agent_mgr.create_agent("keepme")
        with patch("rich.prompt.Confirm.ask", return_value=False):
            agent_mgr.delete_agent("keepme")
        assert agent_mgr.agent_exists("keepme") is True

    def test_delete_agent_resets_default(self):
        agent_mgr.create_agent("todelete")
        agent_mgr.set_default_agent("todelete")
        with patch("rich.prompt.Confirm.ask", return_value=True):
            agent_mgr.delete_agent("todelete")
        assert agent_mgr.get_default_agent() == "default"

    def test_delete_agent_keeps_default_if_unrelated(self):
        agent_mgr.create_agent("alpha")
        agent_mgr.set_default_agent("alpha")
        agent_mgr.create_agent("beta")
        with patch("rich.prompt.Confirm.ask", return_value=True):
            agent_mgr.delete_agent("beta")
        assert agent_mgr.get_default_agent() == "alpha"


class TestReadPersona:
    def test_read_persona_existing(self):
        agent_mgr.create_agent("p")
        agent_mgr.write_persona("p", "我的身份描述")
        assert agent_mgr.read_persona("p") == "我的身份描述"

    def test_read_persona_missing_agent(self):
        result = agent_mgr.read_persona("no_agent")
        assert "无身份设定" in result


class TestReadInstructions:
    def test_read_instructions_existing(self):
        agent_mgr.create_agent("i")
        agent_mgr.write_instructions("i", "我的行为指令")
        assert agent_mgr.read_instructions("i") == "我的行为指令"

    def test_read_instructions_missing_agent(self):
        result = agent_mgr.read_instructions("no_agent")
        assert "无行为指令" in result


class TestReadUserInfo:
    def test_read_user_info_existing(self):
        agent_mgr.create_agent("u")
        agent_mgr.write_user_info("u", "用户信息内容")
        assert agent_mgr.read_user_info("u") == "用户信息内容"

    def test_read_user_info_missing_agent(self):
        result = agent_mgr.read_user_info("no_agent")
        assert "无用户信息" in result


class TestWriteFunctions:
    def test_write_persona_overwrites(self):
        agent_mgr.create_agent("w")
        agent_mgr.write_persona("w", "第一版")
        agent_mgr.write_persona("w", "第二版")
        assert agent_mgr.read_persona("w") == "第二版"

    def test_write_instructions_overwrites(self):
        agent_mgr.create_agent("w")
        agent_mgr.write_instructions("w", "指令A")
        agent_mgr.write_instructions("w", "指令B")
        assert agent_mgr.read_instructions("w") == "指令B"

    def test_write_user_info_overwrites(self):
        agent_mgr.create_agent("w")
        agent_mgr.write_user_info("w", "信息A")
        agent_mgr.write_user_info("w", "信息B")
        assert agent_mgr.read_user_info("w") == "信息B"


class TestGetAgentConfig:
    def test_get_agent_config_existing(self):
        agent_mgr.create_agent("cfg")
        cfg = agent_mgr.get_agent_config("cfg")
        assert isinstance(cfg, dict)
        assert "model" in cfg
        assert "temperature" in cfg

    def test_get_agent_config_missing_agent(self):
        cfg = agent_mgr.get_agent_config("nope")
        assert cfg == {}

    def test_get_agent_config_invalid_json(self):
        agent_mgr.create_agent("bad")
        (agent_mgr.agent_path("bad") / "config.json").write_text("not json{")
        cfg = agent_mgr.get_agent_config("bad")
        assert cfg == {}

    def test_get_agent_config_not_a_dict(self):
        agent_mgr.create_agent("listcfg")
        (agent_mgr.agent_path("listcfg") / "config.json").write_text("[1, 2, 3]")
        cfg = agent_mgr.get_agent_config("listcfg")
        assert cfg == {}


class TestBuildPersonaPrompt:
    def test_build_persona_prompt_includes_name(self):
        agent_mgr.create_agent("named")
        prompt = agent_mgr.build_persona_prompt("named")
        assert "named" in prompt

    def test_build_persona_prompt_includes_sections(self):
        agent_mgr.create_agent("sec")
        agent_mgr.write_persona("sec", "身份段")
        agent_mgr.write_instructions("sec", "指令段")
        agent_mgr.write_user_info("sec", "用户段")
        prompt = agent_mgr.build_persona_prompt("sec")
        assert "身份段" in prompt
        assert "指令段" in prompt
        assert "用户段" in prompt
        assert "行为指令" in prompt
        assert "用户信息" in prompt

    def test_build_persona_prompt_missing_agent(self):
        prompt = agent_mgr.build_persona_prompt("ghost")
        assert "ghost" in prompt
        assert "无身份设定" in prompt


class TestCmdList:
    def test_cmd_list_empty(self):
        # 没有 agent 时不应抛异常
        agent_mgr.cmd_list()

    def test_cmd_list_with_agents(self):
        agent_mgr.create_agent("a1")
        agent_mgr.create_agent("a2")
        agent_mgr.cmd_list()


class TestCmdCreate:
    def test_cmd_create_with_switch(self):
        with patch("rich.prompt.Confirm.ask", return_value=True):
            agent_mgr.cmd_create("newcli")
        assert agent_mgr.agent_exists("newcli")
        assert agent_mgr.get_default_agent() == "newcli"

    def test_cmd_create_without_switch(self):
        with patch("rich.prompt.Confirm.ask", return_value=False):
            agent_mgr.cmd_create("noswitch")
        assert agent_mgr.agent_exists("noswitch")
        assert agent_mgr.get_default_agent() == "default"

    def test_cmd_create_with_clone(self):
        agent_mgr.create_agent("origin")
        with patch("rich.prompt.Confirm.ask", return_value=True):
            agent_mgr.cmd_create("cloned", clone="origin")
        assert agent_mgr.agent_exists("cloned")


def _make_input_fn(lines: list[str]):
    """生成 input() mock：依次返回 lines，耗尽后返回空串（避免 StopIteration）。

    cmd_set_persona/instructions 的输入循环在连续两个空行时终止，
    因此内容后需要补两个空行才会触发 break。
    """
    it = iter(lines)

    def fake_input(*_args, **_kwargs):
        try:
            return next(it)
        except StopIteration:
            return ""

    return fake_input


class TestCmdSetPersona:
    def test_cmd_set_persona_nonexistent_agent(self):
        # 不存在时直接返回，不抛异常
        agent_mgr.cmd_set_persona("ghost")

    def test_cmd_set_persona_with_input(self):
        agent_mgr.create_agent("edit")
        with patch("builtins.input", side_effect=_make_input_fn(["新身份描述", "", ""])), \
                patch("rich.prompt.Confirm.ask", return_value=False):
            agent_mgr.cmd_set_persona("edit")
        assert "新身份描述" in agent_mgr.read_persona("edit")

    def test_cmd_set_persona_empty_input_skips(self):
        agent_mgr.create_agent("edit2")
        agent_mgr.write_persona("edit2", "原身份")
        with patch("builtins.input", side_effect=_make_input_fn(["", ""])):
            agent_mgr.cmd_set_persona("edit2")
        assert agent_mgr.read_persona("edit2") == "原身份"

    def test_cmd_set_persona_uses_default_when_no_name(self):
        agent_mgr.create_agent("default_agent_x")
        agent_mgr.set_default_agent("default_agent_x")
        with patch("builtins.input", side_effect=_make_input_fn(["默认身份", "", ""])), \
                patch("rich.prompt.Confirm.ask", return_value=False):
            agent_mgr.cmd_set_persona()
        assert "默认身份" in agent_mgr.read_persona("default_agent_x")


class TestCmdSetInstructions:
    def test_cmd_set_instructions_nonexistent_agent(self):
        agent_mgr.cmd_set_instructions("ghost")

    def test_cmd_set_instructions_with_input(self):
        agent_mgr.create_agent("instr")
        with patch("builtins.input", side_effect=_make_input_fn(["新指令内容", "", ""])):
            agent_mgr.cmd_set_instructions("instr")
        assert "新指令内容" in agent_mgr.read_instructions("instr")

    def test_cmd_set_instructions_empty_input_skips(self):
        agent_mgr.create_agent("instr2")
        agent_mgr.write_instructions("instr2", "原指令")
        with patch("builtins.input", side_effect=_make_input_fn(["", ""])):
            agent_mgr.cmd_set_instructions("instr2")
        assert agent_mgr.read_instructions("instr2") == "原指令"

    def test_cmd_set_instructions_uses_default_when_no_name(self):
        agent_mgr.create_agent("def_instr")
        agent_mgr.set_default_agent("def_instr")
        with patch("builtins.input", side_effect=_make_input_fn(["默认指令", "", ""])):
            agent_mgr.cmd_set_instructions()
        assert "默认指令" in agent_mgr.read_instructions("def_instr")


class TestCmdShow:
    def test_cmd_show_nonexistent_agent(self):
        agent_mgr.cmd_show("ghost")

    def test_cmd_show_existing_agent(self):
        agent_mgr.create_agent("showcase")
        agent_mgr.write_persona("showcase", "展示身份")
        agent_mgr.cmd_show("showcase")

    def test_cmd_show_uses_default_when_no_name(self):
        agent_mgr.create_agent("defshow")
        agent_mgr.set_default_agent("defshow")
        agent_mgr.cmd_show()
