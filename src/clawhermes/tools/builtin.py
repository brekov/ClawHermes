"""
ClawHermes - 内置工具集
"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

from clawhermes.agent.loop import ToolDef, ToolRegistry


def register_builtin_tools(registry: ToolRegistry):
    """注册所有内置工具"""

    # === 会话工具 ===
    registry.register(ToolDef(
        name="session_status",
        description="获取当前会话的状态信息",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=_session_status,
        parallel_safe=True,
    ))

    # === 文件工具 ===
    registry.register(ToolDef(
        name="read_file",
        description="读取文件内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
            },
            "required": ["path"],
        },
        handler=_read_file,
        parallel_safe=True,
    ))

    registry.register(ToolDef(
        name="write_file",
        description="写入文件内容（覆盖）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
        handler=_write_file,
    ))

    # === 终端工具 ===
    registry.register(ToolDef(
        name="exec",
        description="执行 shell 命令",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
            },
            "required": ["command"],
        },
        handler=_exec_command,
        require_confirm=True,
    ))

    # === 时间工具 ===
    registry.register(ToolDef(
        name="get_time",
        description="获取当前日期和时间",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=_get_time,
        parallel_safe=True,
    ))

    # === Web 搜索工具 ===
    registry.register(ToolDef(
        name="web_search",
        description="搜索互联网信息",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
        handler=_web_search,
        parallel_safe=True,
    ))

    # === 记忆工具 ===
    registry.register(ToolDef(
        name="memory_search",
        description="搜索记忆库中的相关记忆",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
        handler=_memory_search_stub,
        parallel_safe=True,
    ))

    registry.register(ToolDef(
        name="memory_save",
        description="保存一条记忆",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "记忆内容"},
            },
            "required": ["content"],
        },
        handler=_memory_save_stub,
    ))

    registry.register(ToolDef(
        name="delegate_task",
        description="委派子任务给子 Agent 并行执行（如代码审查、多文件分析等）",
        parameters={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "任务ID"},
                            "description": {"type": "string", "description": "任务描述"},
                            "instructions": {"type": "string", "description": "详细指令"},
                        },
                        "required": ["description"],
                    },
                },
            },
            "required": ["tasks"],
        },
        handler=_delegate_task_stub,
    ))


# ===== 工具实现 =====

def _session_status(**kwargs) -> dict:
    return {
        "status": "running",
        "timestamp": datetime.datetime.now().isoformat(),
    }


def _read_file(path: str, **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        if not p.exists():
            return {"error": f"文件不存在: {path}"}
        content = p.read_text(encoding="utf-8")
        return {"content": content, "path": str(p), "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


def _write_file(path: str, content: str, **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p), "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


def _exec_command(command: str, timeout: int = 30, **kwargs) -> dict:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout,
        )
        return {
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"命令超时 ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}


def _get_time(**kwargs) -> dict:
    now = datetime.datetime.now()
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": "Asia/Shanghai",
    }


def _web_search(query: str, **kwargs) -> dict:
    """简易搜索，使用 curl + 搜索引擎"""
    import urllib.parse
    try:
        encoded = urllib.parse.quote(query)
        result = subprocess.run(
            f'curl -sL "https://www.google.com/search?q={encoded}&num=5" 2>/dev/null | '
            f'grep -oP \'<h3[^>]*>.*?</h3>\' | head -5',
            shell=True, capture_output=True, text=True, timeout=10,
        )
        return {"results": result.stdout[:3000] or "（搜索结果为空）"}
    except Exception as e:
        return {"error": str(e)}


def _memory_search_stub(query: str, **kwargs) -> dict:
    """记忆搜索存根 - 完整实现在 M5"""
    return {"results": [], "note": "记忆系统开发中"}


def _memory_save_stub(content: str, **kwargs) -> dict:
    """记忆保存存根"""
    return {"success": True, "note": "记忆系统开发中（已暂存）"}


def _delegate_task_stub(tasks: list[dict], **kwargs) -> dict:
    """子 Agent 委派存根 - 需要 DelegateManager 实例"""
    result_text = []
    for t in tasks:
        result_text.append(f"任务 [{t.get('id', '?')}]: {t.get('description', '')}")
    return {"results": result_text, "note": "子 Agent 委派需要注入 DelegateManager"}
