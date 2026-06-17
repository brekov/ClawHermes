"""
ClawHermes - Agent 设定与多 Agent 管理

类似 OpenClaw 的 SOUL.md + AGENTS.md + USER.md 机制，
支持创建/切换/配置多个 Agent，每个有独立身份和行为指令。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

console = Console()


def get_agents_dir() -> Path:
    data_dir = Path(os.getenv("CH_DATA_DIR", Path.home() / ".clawhermes"))
    agents_dir = data_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


def get_default_agent() -> str:
    """获取默认 Agent 名称"""
    data_dir = Path(os.getenv("CH_DATA_DIR", Path.home() / ".clawhermes"))
    default_file = data_dir / "default_agent.txt"
    if default_file.exists():
        return default_file.read_text().strip()
    return "default"


def set_default_agent(name: str):
    data_dir = Path(os.getenv("CH_DATA_DIR", Path.home() / ".clawhermes"))
    (data_dir / "default_agent.txt").write_text(name)


def list_agents() -> list[str]:
    """列出所有 Agent"""
    agents_dir = get_agents_dir()
    return sorted([d.name for d in agents_dir.iterdir() if d.is_dir()])


def agent_path(name: str) -> Path:
    return get_agents_dir() / name


def agent_exists(name: str) -> bool:
    return agent_path(name).exists()


def create_agent(name: str, clone_from: str | None = None) -> Path:
    """创建新 Agent"""
    path = agent_path(name)
    if path.exists():
        console.print(f"[yellow]⚠️ Agent '{name}' 已存在[/yellow]")
        return path

    if clone_from and agent_exists(clone_from):
        shutil.copytree(agent_path(clone_from), path)
        console.print(f"[green]✅ 已从 '{clone_from}' 克隆创建 Agent '{name}'[/green]")
    else:
        path.mkdir(parents=True)
        # 创建默认文件
        (path / "SOUL.md").write_text(f"# {name} 的身份\n\n你是一个智能 AI 助手。\n")
        (path / "AGENTS.md").write_text("# 行为指令\n\n- 用中文回答\n- 简洁明了\n- 不确定时如实告知\n")
        (path / "USER.md").write_text("# 用户信息\n\n无\n")
        (path / "config.json").write_text(json.dumps({
            "model": os.getenv("CH_DEFAULT_MODEL", "deepseek/deepseek-chat"),
            "temperature": 0.7,
            "max_iterations": 50,
        }, indent=2))
        console.print(f"[green]✅ 已创建 Agent '{name}'[/green]")

    return path


def delete_agent(name: str):
    """删除 Agent"""
    if not agent_exists(name):
        console.print(f"[red]❌ Agent '{name}' 不存在[/red]")
        return
    if name == "default":
        console.print("[red]❌ 不能删除默认 Agent[/red]")
        return

    if Confirm.ask(f"确定删除 Agent '{name}'？"):
        shutil.rmtree(agent_path(name))
        if get_default_agent() == name:
            set_default_agent("default")
        console.print(f"[green]✅ 已删除 Agent '{name}'[/green]")


def read_persona(name: str) -> str:
    """读取 Agent 身份设定"""
    path = agent_path(name) / "SOUL.md"
    if path.exists():
        return path.read_text()
    return "# 无身份设定\n"


def read_instructions(name: str) -> str:
    """读取 Agent 行为指令"""
    path = agent_path(name) / "AGENTS.md"
    if path.exists():
        return path.read_text()
    return "# 无行为指令\n"


def read_user_info(name: str) -> str:
    """读取用户信息"""
    path = agent_path(name) / "USER.md"
    if path.exists():
        return path.read_text()
    return "# 无用户信息\n"


def write_persona(name: str, content: str):
    (agent_path(name) / "SOUL.md").write_text(content)
    console.print(f"[green]✅ '{name}' 的身份设定已更新[/green]")


def write_instructions(name: str, content: str):
    (agent_path(name) / "AGENTS.md").write_text(content)


def write_user_info(name: str, content: str):
    (agent_path(name) / "USER.md").write_text(content)


def get_agent_config(name: str) -> dict:
    """获取 Agent 配置"""
    cfg_file = agent_path(name) / "config.json"
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text())
            assert isinstance(cfg, dict)
            return cfg
        except Exception:
            return {}
    return {}


def build_persona_prompt(name: str) -> str:
    """组装 Agent 设定 prompt（供 StableLayer 使用）"""
    parts = [f"你是 {name}。"]
    parts.append(read_persona(name))
    parts.append("## 行为指令\n" + read_instructions(name))
    parts.append("## 用户信息\n" + read_user_info(name))
    return "\n\n".join(parts)


# ===== CLI 命令实现 =====

def cmd_list():
    """clawhermes agent list"""
    agents = list_agents()
    default = get_default_agent()

    if not agents:
        console.print("⚠️  没有 Agent，运行 [bold]clawhermes agent create <name>[/bold] 创建")
        return

    table = Table(title="可用 Agent")
    table.add_column("名称", style="cyan")
    table.add_column("默认", style="green")
    table.add_column("身份摘要")
    table.add_column("指令摘要")

    for name in agents:
        is_default = "✅" if name == default else ""
        persona = read_persona(name).split("\n")[0][:40] if read_persona(name) else ""
        instr = read_instructions(name).split("\n")[1][:40] if read_instructions(name) else ""
        table.add_row(name, is_default, persona, instr)

    console.print(table)


def cmd_create(name: str, clone: str | None = None):
    """clawhermes agent create"""
    create_agent(name, clone)
    if Confirm.ask(f"切换到 '{name}'？", default=True):
        set_default_agent(name)


def cmd_set_persona(name: str | None = None):
    """clawhermes agent set-persona — 交互式设定身份"""
    if name is None:
        name = get_default_agent()

    if not agent_exists(name):
        console.print(f"[red]❌ Agent '{name}' 不存在[/red]")
        return

    console.clear()
    console.print(Panel.fit(f"[bold]设定 '{name}' 的身份[/bold]", border_style="blue"))
    console.print("\n[dim]当前身份:[/dim]")
    console.print(Markdown(read_persona(name)))

    console.print("\n[bold cyan]请输入新的身份描述[/bold cyan]")
    console.print("[dim]（用 Markdown 格式，描述你是谁、你的语气、个性等。多行输入，输入空行结束）[/dim]")

    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "" and lines and lines[-1] == "":
            break
        lines.append(line)

    content = "\n".join(lines).strip()
    if content:
        write_persona(name, content)
        console.print(f"[green]✅ '{name}' 的身份已更新[/green]")

        if Confirm.ask("是否也设置行为指令？", default=False):
            cmd_set_instructions(name)


def cmd_set_instructions(name: str | None = None):
    """clawhermes agent set-instructions"""
    if name is None:
        name = get_default_agent()
    if not agent_exists(name):
        console.print(f"[red]❌ Agent '{name}' 不存在[/red]")
        return

    console.print(Panel.fit(f"[bold]设定 '{name}' 的行为指令[/bold]", border_style="green"))
    console.print("\n[dim]当前指令:[/dim]")
    console.print(Markdown(read_instructions(name)))

    console.print("\n[bold cyan]请输入行为指令[/bold cyan]")
    console.print("[dim]（多行输入，空行结束）[/dim]")

    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "" and lines and lines[-1] == "":
            break
        lines.append(line)

    content = "\n".join(lines).strip()
    if content:
        write_instructions(name, content)
        console.print(f"[green]✅ '{name}' 的行为指令已更新[/green]")


def cmd_show(name: str | None = None):
    """clawhermes agent show — 查看 Agent 详情"""
    if name is None:
        name = get_default_agent()
    if not agent_exists(name):
        console.print(f"[red]❌ Agent '{name}' 不存在[/red]")
        return

    console.print(Panel.fit(f"[bold]Agent: {name}[/bold]", border_style="cyan"))
    console.print(f"默认: {'✅' if name == get_default_agent() else '❌'}")

    config = get_agent_config(name)
    console.print(f"模型: {config.get('model', '默认')}")
    console.print("\n[bold]身份设定:[/bold]")
    console.print(Markdown(read_persona(name)))
    console.print("\n[bold]行为指令:[/bold]")
    console.print(Markdown(read_instructions(name)))
    console.print("\n[bold]用户信息:[/bold]")
    console.print(Markdown(read_user_info(name)))
