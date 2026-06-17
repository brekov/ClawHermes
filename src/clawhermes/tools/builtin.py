"""
ClawHermes - 内置工具集
"""
from __future__ import annotations

import datetime
import subprocess
import urllib.parse
from pathlib import Path

from clawhermes.agent.loop import ToolDef, ToolRegistry

MINIMAL_TOOLS = frozenset({
    "session_status", "read_file", "write_file", "exec", "get_time",
})

STANDARD_TOOLS = MINIMAL_TOOLS | frozenset({
    "web_search", "memory_search", "memory_save", "delegate_task",
})

FULL_TOOLS = STANDARD_TOOLS | frozenset({
    "web_fetch", "list_dir", "patch_file", "grep", "search_replace", "code_eval",
})

PROFILE_MAP = {
    "minimal": MINIMAL_TOOLS,
    "standard": STANDARD_TOOLS,
    "full": FULL_TOOLS,
}


def register_builtin_tools(registry: ToolRegistry, profile: str = "standard"):
    """注册内置工具，支持 profile 分级"""
    allowed = PROFILE_MAP.get(profile, STANDARD_TOOLS)

    all_tools = [
        ToolDef(
            name="session_status",
            description="获取当前会话的状态信息",
            parameters={"type": "object", "properties": {}},
            handler=_session_status,
            parallel_safe=True,
        ),
        ToolDef(
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
        ),
        ToolDef(
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
        ),
        ToolDef(
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
        ),
        ToolDef(
            name="get_time",
            description="获取当前日期和时间",
            parameters={"type": "object", "properties": {}},
            handler=_get_time,
            parallel_safe=True,
        ),
        ToolDef(
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
        ),
        ToolDef(
            name="memory_search",
            description="搜索记忆库中的相关记忆",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
            handler=_memory_search,
            parallel_safe=True,
        ),
        ToolDef(
            name="memory_save",
            description="保存一条记忆",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "记忆内容"},
                },
                "required": ["content"],
            },
            handler=_memory_save,
        ),
        ToolDef(
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
            handler=_delegate_task,
        ),
        ToolDef(
            name="web_fetch",
            description="获取网页内容并转换为文本",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "网页 URL"},
                },
                "required": ["url"],
            },
            handler=_web_fetch,
            parallel_safe=True,
        ),
        ToolDef(
            name="list_dir",
            description="列出目录内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径", "default": "."},
                    "pattern": {"type": "string", "description": "glob 过滤模式", "default": "*"},
                },
            },
            handler=_list_dir,
            parallel_safe=True,
        ),
        ToolDef(
            name="patch_file",
            description="对文件应用差异补丁（搜索旧内容并替换为新内容）",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "search": {"type": "string", "description": "要搜索的旧内容"},
                    "replace": {"type": "string", "description": "替换的新内容"},
                },
                "required": ["path", "search", "replace"],
            },
            handler=_patch_file,
        ),
        ToolDef(
            name="grep",
            description="在文件中搜索匹配的文本行",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式模式"},
                    "path": {"type": "string", "description": "搜索路径", "default": "."},
                    "file_pattern": {"type": "string", "description": "文件名 glob 模式", "default": "*.py"},
                },
                "required": ["pattern"],
            },
            handler=_grep,
            parallel_safe=True,
        ),
        ToolDef(
            name="search_replace",
            description="在文件中执行搜索替换操作",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "search": {"type": "string", "description": "搜索文本"},
                    "replace": {"type": "string", "description": "替换文本"},
                    "all": {"type": "boolean", "description": "是否替换所有匹配", "default": False},
                },
                "required": ["path", "search", "replace"],
            },
            handler=_search_replace,
        ),
        ToolDef(
            name="code_eval",
            description="执行 Python 代码片段并返回结果",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码"},
                    "timeout": {"type": "integer", "description": "超时秒数", "default": 10},
                },
                "required": ["code"],
            },
            handler=_code_eval,
            require_confirm=True,
        ),
    ]

    for tool in all_tools:
        if tool.name in allowed:
            registry.register(tool)


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


def _memory_search(query: str, **kwargs) -> dict:
    memory_manager = kwargs.get("_memory_manager")
    if memory_manager is None:
        return {"results": [], "note": "记忆管理器未初始化"}
    try:
        items = memory_manager.search(query, limit=5)
        return {
            "results": [
                {"content": item.content, "importance": item.importance}
                for item in items
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def _memory_save(content: str, **kwargs) -> dict:
    memory_manager = kwargs.get("_memory_manager")
    if memory_manager is None:
        return {"success": False, "note": "记忆管理器未初始化"}
    try:
        from clawhermes.types import MemoryScope
        memory_manager.save(content, MemoryScope.USER, 0.5)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


def _delegate_task(tasks: list[dict], **kwargs) -> dict:
    delegate_manager = kwargs.get("_delegate_manager")
    if delegate_manager is None:
        result_text = []
        for t in tasks:
            result_text.append(f"任务 [{t.get('id', '?')}]: {t.get('description', '')}")
        return {"results": result_text, "note": "委派管理器未初始化"}
    try:
        results = delegate_manager.delegate(tasks)
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}


def _web_fetch(url: str, **kwargs) -> dict:
    try:
        result = subprocess.run(
            f'curl -sL -A "Mozilla/5.0" "{url}" 2>/dev/null | '
            f'sed -e "s/<[^>]*>//g" | sed "/^$/d" | head -200',
            shell=True, capture_output=True, text=True, timeout=15,
        )
        return {"content": result.stdout[:8000] or "（内容为空）", "url": url}
    except Exception as e:
        return {"error": str(e)}


def _list_dir(path: str = ".", pattern: str = "*", **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        if not p.is_dir():
            return {"error": f"不是目录: {path}"}
        entries = []
        for entry in sorted(p.glob(pattern)):
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return {"path": str(p), "entries": entries[:100], "count": len(entries)}
    except Exception as e:
        return {"error": str(e)}


def _patch_file(path: str, search: str, replace: str, **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        if not p.exists():
            return {"error": f"文件不存在: {path}"}
        content = p.read_text(encoding="utf-8")
        if search not in content:
            return {"error": "未找到搜索内容", "path": str(p)}
        new_content = content.replace(search, replace, 1)
        p.write_text(new_content, encoding="utf-8")
        return {"success": True, "path": str(p), "replacements": 1}
    except Exception as e:
        return {"error": str(e)}


def _grep(pattern: str, path: str = ".", file_pattern: str = "*.py", **kwargs) -> dict:
    try:
        result = subprocess.run(
            f'grep -rn --include="{file_pattern}" "{pattern}" "{path}" 2>/dev/null | head -50',
            shell=True, capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {"matches": lines[:50], "count": len(lines)}
    except Exception as e:
        return {"error": str(e)}


def _search_replace(path: str, search: str, replace: str, all: bool = False, **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        if not p.exists():
            return {"error": f"文件不存在: {path}"}
        content = p.read_text(encoding="utf-8")
        count = content.count(search)
        if count == 0:
            return {"error": "未找到搜索文本", "path": str(p)}
        if all:
            new_content = content.replace(search, replace)
        else:
            new_content = content.replace(search, replace, 1)
        p.write_text(new_content, encoding="utf-8")
        return {"success": True, "path": str(p), "replacements": count if all else 1}
    except Exception as e:
        return {"error": str(e)}


def _code_eval(code: str, timeout: int = 10, **kwargs) -> dict:
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"代码执行超时 ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}
