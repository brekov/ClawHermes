"""Agent 子命令组 — list / create / show / switch / set。"""
from __future__ import annotations

import click

from clawhermes.cli import console


@click.group()
def agent():
    """管理 Agent"""
    pass


@agent.command("list")
def agent_list():
    from clawhermes.agent.agent_mgr import cmd_list
    cmd_list()


@agent.command()
@click.argument("name")
@click.option("--clone", default=None)
def create(name, clone):
    from clawhermes.agent.agent_mgr import cmd_create
    cmd_create(name, clone)


@agent.command()
@click.argument("name", required=False)
def show(name):
    from clawhermes.agent.agent_mgr import cmd_show
    cmd_show(name)


@agent.command()
@click.argument("name")
def switch(name):
    from clawhermes.agent.agent_mgr import agent_exists, set_default_agent
    if agent_exists(name):
        set_default_agent(name)
        console.print(f"✅ 已切换到 '{name}'")
    else:
        console.print(f"❌ Agent '{name}' 不存在")


@agent.command(name="set")
@click.argument("name", required=False)
def cmd_agent_set(name):
    from clawhermes.agent.agent_mgr import cmd_set_persona
    cmd_set_persona(name)
