"""
ClawHermes - 内置工具集
"""
from __future__ import annotations

import ast as _ast
import datetime
import gzip
import json
import logging
import math as _math
import operator as _operator
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

from clawhermes.agent.loop import ToolDef, ToolRegistry

MINIMAL_TOOLS = frozenset({
    "session_status", "read_file", "write_file", "exec", "get_time",
})

STANDARD_TOOLS = (MINIMAL_TOOLS - {"exec"}) | frozenset({
    "web_search", "memory_search", "memory_save", "delegate_task",
})

FULL_TOOLS = STANDARD_TOOLS | frozenset({
    "web_fetch", "list_dir", "patch_file", "grep", "search_replace", "code_eval",
    "compress_file", "http_request", "json_query", "git_status", "git_diff",
    "git_log", "env_list", "timer", "url_encode", "url_decode", "calc",
    "sqlite_query", "csv_parse", "hash_file", "disk_usage", "base64_codec",
    "process_list", "image_info", "pdf_extract", "markdown_render",
})

PROFILE_MAP = {
    "minimal": MINIMAL_TOOLS,
    "standard": STANDARD_TOOLS,
    "full": FULL_TOOLS,
}

# 文件大小上限
_MAX_READ_BYTES = 1024 * 1024  # 1MB
_MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10MB

# 系统目录黑名单 — workspace_root 未提供时回退到此清单
_BLOCKED_SYSTEM_DIRS = (
    "/etc", "/usr", "/bin", "/sbin", "/System", "/Library",
    "/dev", "/proc", "/sys", "/boot", "/root",
)


def _validate_workspace_path(path: str, workspace_root: Path | str | None = None) -> Path:
    """校验路径在 workspace root 内

    workspace_root 提供时严格校验路径必须在其下；
    未提供时回退到禁止系统目录的宽松校验（保护 /etc/passwd 等敏感路径）。
    """
    target = Path(path).resolve()
    if workspace_root is not None:
        root = Path(workspace_root).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"路径越界: {path} 不在 workspace {root} 内")
    else:
        for blocked in _BLOCKED_SYSTEM_DIRS:
            if target.is_relative_to(Path(blocked)):
                raise ValueError(f"路径越界: {path} 在系统目录 {blocked} 内")
    return target


def _validate_sqlite_path(db_path: str, data_dir: Path | str | None = None) -> Path:
    """校验 SQLite db 路径在 data_dir 内或不在系统目录中"""
    target = Path(db_path).resolve()
    if data_dir is not None:
        root = Path(data_dir).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"路径越界: {db_path} 不在 data_dir {root} 内")
    else:
        for blocked in _BLOCKED_SYSTEM_DIRS:
            if target.is_relative_to(Path(blocked)):
                raise ValueError(f"路径越界: {db_path} 在系统目录 {blocked} 内")
    return target


_SQLITE_DANGEROUS_KEYWORDS = ("DROP", "DELETE", "ATTACH", "DETACH")


def _sqlite_query(
    db_path: str,
    query: str,
    params: list | None = None,
    allow_write: bool = False,
    **kwargs,
) -> dict:
    """查询 SQLite 数据库

    默认只读模式连接；危险操作（DROP/DELETE/ATTACH/DETACH）需 allow_write=True。
    """
    import sqlite3
    try:
        target = _validate_sqlite_path(db_path, kwargs.get("data_dir"))

        query_upper = query.strip().upper()
        is_dangerous = any(kw in query_upper for kw in _SQLITE_DANGEROUS_KEYWORDS)
        if is_dangerous and not allow_write:
            return {"error": f"危险操作需 allow_write=True: {query}"}

        if allow_write:
            conn = sqlite3.connect(str(target))
        else:
            conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)

        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        if query_upper.startswith("SELECT") or query_upper.startswith("PRAGMA"):
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description] if cursor.description else []
            conn.close()
            return {"columns": columns, "rows": [list(r) for r in rows], "count": len(rows)}
        else:
            conn.commit()
            changes = conn.total_changes
            conn.close()
            return {"affected": changes}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"SQLite 查询失败: {e}"}


def _csv_parse(path: str, delimiter: str = ",", has_header: bool = True, max_rows: int = 100, **kwargs) -> dict:
    """解析 CSV 文件"""
    import csv
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = []
            headers = None
            for i, row in enumerate(reader):
                if i == 0 and has_header:
                    headers = row
                    continue
                if i >= max_rows + (1 if has_header else 0):
                    break
                rows.append(row)
            return {"headers": headers, "rows": rows, "count": len(rows)}
    except Exception as e:
        return {"error": f"CSV 解析失败: {e}"}


def _hash_file(path: str, algorithm: str = "sha256", **kwargs) -> dict:
    """计算文件哈希值"""
    import hashlib
    try:
        p = _validate_workspace_path(path, kwargs.get("workspace_root"))
        h = hashlib.new(algorithm)
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return {"algorithm": algorithm, "hash": h.hexdigest()}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"哈希计算失败: {e}"}


def _disk_usage(path: str = ".", **kwargs) -> dict:
    """检查磁盘使用情况"""
    import shutil
    try:
        usage = shutil.disk_usage(path)
        return {
            "path": path,
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception as e:
        return {"error": f"磁盘检查失败: {e}"}


def _base64_codec(action: str, text: str, **kwargs) -> dict:
    """Base64 编解码"""
    import base64
    try:
        if action == "encode":
            result = base64.b64encode(text.encode()).decode()
            return {"action": "encode", "result": result}
        elif action == "decode":
            result = base64.b64decode(text.encode()).decode()
            return {"action": "decode", "result": result}
        else:
            return {"error": f"不支持的操作: {action}，仅支持 encode/decode"}
    except Exception as e:
        return {"error": f"Base64 处理失败: {e}"}


def _process_list(**kwargs) -> dict:
    """列出运行中的进程"""
    import platform
    import subprocess
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10)
        else:
            result = subprocess.run(["ps", "aux", "--no-headers"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split("\n")[:50]
        return {"platform": platform.system(), "processes": lines, "count": len(lines)}
    except Exception as e:
        return {"error": f"进程列表获取失败: {e}"}


def _image_info(path: str, **kwargs) -> dict:
    """获取图片信息（宽高、格式、大小）"""
    import os
    try:
        from PIL import Image
        img = Image.open(path)
        size_bytes = os.path.getsize(path)
        return {
            "format": img.format,
            "mode": img.mode,
            "width": img.width,
            "height": img.height,
            "size_bytes": size_bytes,
            "size_kb": round(size_bytes / 1024, 1),
        }
    except ImportError:
        return {"error": "Pillow 未安装 (pip install Pillow)"}
    except Exception as e:
        return {"error": f"图片读取失败: {e}"}


def _pdf_extract(path: str, max_pages: int = 10, **kwargs) -> dict:
    """提取 PDF 文本内容"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = []
        for i, page in enumerate(reader.pages[:max_pages]):
            text = page.extract_text()
            if text:
                pages.append({"page": i + 1, "text": text[:2000]})
        return {"total_pages": len(reader.pages), "extracted": len(pages), "pages": pages}
    except ImportError:
        return {"error": "pypdf 未安装 (pip install pypdf)"}
    except Exception as e:
        return {"error": f"PDF 提取失败: {e}"}


def _markdown_render(text: str, **kwargs) -> dict:
    """将 Markdown 渲染为 HTML"""
    try:
        import markdown
        html = markdown.markdown(text, extensions=["fenced_code", "tables"])
        return {"html": html}
    except ImportError:
        # Fallback: basic markdown-like conversion
        html = text.replace("\n\n", "</p><p>").replace("\n", "<br>")
        return {"html": f"<p>{html}</p>", "note": "markdown 库未安装，使用基础转换"}
    except Exception as e:
        return {"error": f"Markdown 渲染失败: {e}"}


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
            require_confirm=True,
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
            description=(
                "对文件执行一次搜索-替换：仅查找 search 文本的第一处出现并替换为 replace 文本。"
                "若未匹配到则返回失败，不做任何修改。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "search": {"type": "string", "description": "要搜索的文本（仅替换第一处匹配）"},
                    "replace": {"type": "string", "description": "替换为的新文本"},
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
        ToolDef(
            name="compress_file",
            description="使用 gzip 压缩文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "源文件路径"},
                    "output": {"type": "string", "description": "输出文件路径（默认源文件路径 + .gz）"},
                },
                "required": ["path"],
            },
            handler=_compress_file,
            parallel_safe=True,
        ),
        ToolDef(
            name="http_request",
            description="发送 HTTP GET/POST 请求",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "请求 URL"},
                    "method": {"type": "string", "description": "请求方法 GET/POST", "default": "GET", "enum": ["GET", "POST"]},
                    "data": {"type": "string", "description": "POST 请求体数据"},
                    "headers": {"type": "object", "description": "自定义请求头"},
                },
                "required": ["url"],
            },
            handler=_http_request,
            require_confirm=True,
        ),
        ToolDef(
            name="json_query",
            description="从 JSON 数据中查询/提取字段",
            parameters={
                "type": "object",
                "properties": {
                    "json_str": {"type": "string", "description": "JSON 字符串"},
                    "path": {"type": "string", "description": "查询路径，用点号分隔，如 a.b.0.name"},
                },
                "required": ["json_str"],
            },
            handler=_json_query,
        ),
        ToolDef(
            name="git_status",
            description="显示 Git 工作区状态",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "仓库路径", "default": "."},
                },
            },
            handler=_git_status,
            parallel_safe=True,
        ),
        ToolDef(
            name="git_diff",
            description="显示 Git 差异",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "仓库路径", "default": "."},
                    "staged": {"type": "boolean", "description": "是否查看暂存区差异", "default": False},
                },
            },
            handler=_git_diff,
            require_confirm=True,
        ),
        ToolDef(
            name="git_log",
            description="显示最近 Git 提交记录",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "仓库路径", "default": "."},
                    "count": {"type": "integer", "description": "显示条数", "default": 10},
                },
            },
            handler=_git_log,
            parallel_safe=True,
        ),
        ToolDef(
            name="env_list",
            description="列出环境变量（敏感值已脱敏）",
            parameters={
                "type": "object",
                "properties": {
                    "prefix": {"type": "string", "description": "按前缀过滤环境变量"},
                },
            },
            handler=_env_list,
            parallel_safe=True,
        ),
        ToolDef(
            name="timer",
            description="定时器/秒表：启动计时或查看已用时间",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "start=启动计时, elapsed=查看已用时间", "enum": ["start", "elapsed"]},
                    "timer_id": {"type": "string", "description": "计时器 ID（elapsed 时需提供）"},
                },
                "required": ["action"],
            },
            handler=_timer,
        ),
        ToolDef(
            name="url_encode",
            description="对字符串进行 URL 编码",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要编码的文本"},
                },
                "required": ["text"],
            },
            handler=_url_encode,
            parallel_safe=True,
        ),
        ToolDef(
            name="url_decode",
            description="对 URL 编码的字符串进行解码",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要解码的文本"},
                },
                "required": ["text"],
            },
            handler=_url_decode,
            parallel_safe=True,
        ),
        ToolDef(
            name="calc",
            description="计算数学表达式",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，如 2+3*4 或 sqrt(16)"},
                },
                "required": ["expression"],
            },
            handler=_calc,
            parallel_safe=True,
        ),
        ToolDef(
            name="sqlite_query",
            description="查询 SQLite 数据库，支持 SELECT 和 DML 语句",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "SQLite 数据库文件路径"},
                    "query": {"type": "string", "description": "SQL 查询语句"},
                    "params": {"type": "array", "items": {"type": "string"}, "description": "查询参数"},
                },
                "required": ["db_path", "query"],
            },
            handler=_sqlite_query,
            group="data",
        ),
        ToolDef(
            name="csv_parse",
            description="解析 CSV 文件，返回表头和行数据",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "CSV 文件路径"},
                    "delimiter": {"type": "string", "description": "分隔符，默认逗号"},
                    "has_header": {"type": "boolean", "description": "是否有表头行"},
                    "max_rows": {"type": "integer", "description": "最大读取行数，默认 100"},
                },
                "required": ["path"],
            },
            handler=_csv_parse,
            group="data",
        ),
        ToolDef(
            name="hash_file",
            description="计算文件哈希值（md5/sha1/sha256/sha512）",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "algorithm": {"type": "string", "description": "哈希算法，默认 sha256"},
                },
                "required": ["path"],
            },
            handler=_hash_file,
            parallel_safe=True,
            group="file",
        ),
        ToolDef(
            name="disk_usage",
            description="检查磁盘使用情况，返回总容量/已用/可用",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "检查路径，默认当前目录"},
                },
                "required": [],
            },
            handler=_disk_usage,
            parallel_safe=True,
            group="system",
        ),
        ToolDef(
            name="base64_codec",
            description="Base64 编码或解码文本",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "encode 或 decode"},
                    "text": {"type": "string", "description": "要处理的文本"},
                },
                "required": ["action", "text"],
            },
            handler=_base64_codec,
            parallel_safe=True,
            group="util",
        ),
        ToolDef(
            name="process_list",
            description="列出系统运行中的进程",
            parameters={"type": "object", "properties": {}},
            handler=_process_list,
            parallel_safe=True,
            group="system",
        ),
        ToolDef(
            name="image_info",
            description="获取图片信息（格式、尺寸、大小），需要 Pillow",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "图片文件路径"},
                },
                "required": ["path"],
            },
            handler=_image_info,
            parallel_safe=True,
            group="media",
        ),
        ToolDef(
            name="pdf_extract",
            description="提取 PDF 文件文本内容，需要 pypdf",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PDF 文件路径"},
                    "max_pages": {"type": "integer", "description": "最大提取页数，默认 10"},
                },
                "required": ["path"],
            },
            handler=_pdf_extract,
            group="media",
        ),
        ToolDef(
            name="markdown_render",
            description="将 Markdown 文本渲染为 HTML",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Markdown 文本"},
                },
                "required": ["text"],
            },
            handler=_markdown_render,
            parallel_safe=True,
            group="util",
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
        p = _validate_workspace_path(path, kwargs.get("workspace_root"))
        if not p.exists():
            return {"error": f"文件不存在: {path}"}
        raw = p.read_bytes()
        truncated = False
        if len(raw) > _MAX_READ_BYTES:
            raw = raw[:_MAX_READ_BYTES]
            truncated = True
        content = raw.decode("utf-8", errors="ignore")
        return {
            "content": content,
            "path": str(p),
            "size": len(content),
            "truncated": truncated,
        }
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def _write_file(path: str, content: str, **kwargs) -> dict:
    try:
        p = _validate_workspace_path(path, kwargs.get("workspace_root"))
        if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
            return {"error": f"内容超过 {_MAX_WRITE_BYTES // (1024 * 1024)}MB 上限"}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p), "size": len(content)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# 危险命令模式 — 仅审计日志，无内建阻拦；主防线为 require_confirm + DockerSandbox
# 当前实现仍保留兜底阻拦（命中即拒绝），以覆盖无 Docker 环境的回退路径
_EXEC_DANGEROUS_PATTERNS = (
    "rm -rf /", "rm -rf ~", "rm -rf *", "rm -rf .",
    "mkfs", "dd of=/dev/sd", "dd of=/dev/nvme",
    ":(){:|:&};:",  # fork bomb
    "> /dev/sda", "> /dev/nvme",
    "shutdown", "reboot", "halt", "poweroff",
    "chmod -R 777 /",
)


def _exec_command(command: str, timeout: int = 30, **kwargs) -> dict:
    """执行 shell 命令 — 优先 Docker 沙箱，回退 subprocess（非沙箱模式）。"""
    _logger = logging.getLogger("clawhermes.tools.exec")

    # 危险命令检测（大小写不敏感）— 兜底阻拦
    cmd_lower = command.lower().strip()
    for pattern in _EXEC_DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            _logger.warning("BLOCKED dangerous command: %r (matched %r)", command, pattern)
            return {
                "error": f"命令被安全策略拒绝（匹配危险模式: {pattern}）",
                "command": command,
                "blocked": True,
            }

    # 审计日志（无论成功失败都记录）
    _logger.warning("exec_command: %r (timeout=%ds)", command, timeout)

    # 优先使用 Docker 沙箱
    try:
        from clawhermes.tools.sandbox import DockerSandbox
        if DockerSandbox.is_available():
            sandbox = DockerSandbox()
            result = sandbox.run_command(command, timeout=timeout)
            if result.exit_code != -1:
                return {
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:2000],
                    "return_code": result.exit_code,
                    "command": command,
                    "sandbox": True,
                }
            _logger.warning("Sandbox execution failed (exit=-1), falling back to subprocess")
    except Exception as e:
        _logger.warning("Docker sandbox unavailable, falling back to subprocess: %s", e)

    # 回退：非沙箱模式执行
    _logger.warning("非沙箱模式执行: %r", command)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout,
        )
        return {
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "return_code": result.returncode,
            "command": command,
            "sandbox": False,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"命令超时 ({timeout}s)", "command": command}
    except Exception as e:
        return {"error": str(e), "command": command}


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
    search_engine = os.getenv("CH_SEARCH_ENGINE", "duckduckgo")
    try:
        if search_engine == "searxng":
            return _web_search_searxng(query)
        elif search_engine == "serpapi":
            return _web_search_serpapi(query)
        elif search_engine == "tavily":
            return _web_search_tavily(query)
        else:
            return _web_search_duckduckgo(query)
    except Exception as e:
        return {"error": str(e)}


def _web_search_duckduckgo(query: str) -> dict:
    try:
        import httpx
    except ImportError:
        return _web_search_fallback(query)
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; ClawHermes/1.0)"},
            )
            resp.raise_for_status()
            results = _parse_ddg_html(resp.text)
            if not results:
                return {"results": [], "note": "搜索结果为空"}
            return {"results": results, "engine": "duckduckgo"}
    except Exception as e:
        fallback = _web_search_fallback(query)
        fallback["engine"] = "fallback"
        fallback["error_detail"] = str(e)
        return fallback


def _parse_ddg_html(html: str) -> list[dict]:
    import re
    results = []
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    ):
        url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        if title:
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= 8:
            break
    return results


def _web_search_searxng(query: str) -> dict:
    base_url = os.getenv("CH_SEARXNG_URL", "http://localhost:8888")
    try:
        import httpx
    except ImportError:
        return {"error": "httpx 未安装，无法使用 SearXNG 搜索"}
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{base_url}/search",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("results", [])[:8]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                })
            return {"results": results, "engine": "searxng"}
    except Exception as e:
        return {"error": f"SearXNG 连接失败: {e}", "results": []}


def _web_search_serpapi(query: str) -> dict:
    api_key = os.getenv("CH_SERPAPI_KEY", "")
    if not api_key:
        return {"error": "CH_SERPAPI_KEY 未设置"}
    try:
        import httpx
    except ImportError:
        return {"error": "httpx 未安装"}
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": api_key, "engine": "google", "num": 5},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic_results", [])[:5]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return {"results": results, "engine": "serpapi"}


def _web_search_tavily(query: str) -> dict:
    api_key = os.getenv("CH_TAVILY_KEY", "")
    if not api_key:
        return {"error": "CH_TAVILY_KEY 未设置"}
    try:
        import httpx
    except ImportError:
        return {"error": "httpx 未安装"}
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": 5},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:5]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            })
        return {"results": results, "engine": "tavily"}


def _web_search_fallback(query: str) -> dict:
    """Google 搜索 fallback — 纯 httpx + 正则解析，无 shell 调用"""
    try:
        import httpx
    except ImportError:
        return {"results": [], "note": "httpx 未安装，无法执行搜索 fallback"}

    encoded = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded}&num=5"
    try:
        with httpx.Client(timeout=10, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception as e:
        return {"results": [], "note": f"搜索请求失败: {e}"}

    # 用正则提取 <h3> 标题（Google 搜索结果标题在 h3 中）
    results: list[dict[str, str]] = []
    for match in re.finditer(r"<h3[^>]*>(.*?)</h3>", resp.text, re.DOTALL):
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if title:
            results.append({"title": title, "url": "", "snippet": ""})
        if len(results) >= 5:
            break

    return {"results": results, "engine": "google_fallback"}


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
    """抓取网页内容并转为纯文本 — 纯 httpx + 正则，无 shell 调用"""
    try:
        import httpx
    except ImportError:
        return {"error": "httpx 未安装，无法执行 web_fetch"}

    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        return {"error": f"HTTP 请求失败: {e}"}
    except Exception as e:
        return {"error": str(e)}

    # 用正则剥离 HTML 标签 + 压缩空行，等价于原 sed 流程
    text = resp.text
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    content = "\n".join(lines[:200])
    return {"content": content[:8000] or "（内容为空）", "url": url}


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
        p = _validate_workspace_path(path, kwargs.get("workspace_root"))
        if not p.exists():
            return {"error": f"文件不存在: {path}"}
        content = p.read_text(encoding="utf-8")
        if search not in content:
            return {"error": "未找到搜索内容", "path": str(p)}
        new_content = content.replace(search, replace, 1)
        p.write_text(new_content, encoding="utf-8")
        return {"success": True, "path": str(p), "replacements": 1}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def _grep(pattern: str, path: str = ".", file_pattern: str = "*.py", **kwargs) -> dict:
    """在文件中搜索匹配的文本行 — 纯 Python 正则 + pathlib，无 shell 调用"""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"error": f"正则表达式无效: {e}"}

    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"路径不存在: {path}"}

    matches: list[str] = []
    # 排除常见非源码目录，避免大项目超时
    _skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".ruff_cache"}
    try:
        for file_path in root.rglob(file_pattern):
            if not file_path.is_file():
                continue
            # 跳过排除目录下的文件
            if any(part in _skip_dirs for part in file_path.relative_to(root).parts):
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            rel = file_path.relative_to(root) if root.is_dir() else file_path.name
            for line_no, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{rel}:{line_no}:{line[:200]}")
                    if len(matches) >= 50:
                        return {"matches": matches, "count": len(matches)}
        return {"matches": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}


def _search_replace(path: str, search: str, replace: str, all: bool = False, **kwargs) -> dict:
    try:
        p = _validate_workspace_path(path, kwargs.get("workspace_root"))
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
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def _code_eval(code: str, timeout: int = 10, **kwargs) -> dict:
    """执行 Python 代码 — 优先 Docker 沙箱，回退 subprocess（非沙箱模式）。"""
    _logger = logging.getLogger("clawhermes.tools.code_eval")

    # 优先使用 Docker 沙箱
    try:
        from clawhermes.tools.sandbox import DockerSandbox
        if DockerSandbox.is_available():
            sandbox = DockerSandbox()
            result = sandbox.run_python(code, timeout=timeout)
            if result.exit_code != -1:
                return {
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:2000],
                    "return_code": result.exit_code,
                    "sandbox": True,
                }
            _logger.warning("Sandbox execution failed (exit=-1), falling back to subprocess")
    except Exception as e:
        _logger.warning("Docker sandbox unavailable, falling back to subprocess: %s", e)

    # 回退：非沙箱模式执行
    _logger.warning("非沙箱模式执行 code_eval")
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "return_code": result.returncode,
            "sandbox": False,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"代码执行超时 ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}


def _compress_file(path: str, output: str = "", **kwargs) -> dict:
    try:
        src = _validate_workspace_path(path, kwargs.get("workspace_root"))
        if not src.exists():
            return {"error": f"文件不存在: {path}"}
        if output:
            dst = _validate_workspace_path(output, kwargs.get("workspace_root"))
        else:
            dst = src.with_suffix(src.suffix + ".gz")
        with open(src, "rb") as f_in:
            with gzip.open(dst, "wb") as f_out:
                f_out.writelines(f_in)
        return {"success": True, "source": str(src), "output": str(dst), "size": dst.stat().st_size}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def _http_request(url: str, method: str = "GET", data: str = "", headers: dict | None = None, **kwargs) -> dict:
    """发送 HTTP GET/POST 请求 — 纯 httpx 实现，无子进程依赖"""
    import httpx
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.request(method, url, headers=headers, content=data if data else None)
            return {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text[:5000],
            }
    except Exception as e:
        return {"error": f"HTTP 请求失败: {e}"}


def _json_query(json_str: str, path: str = "", **kwargs) -> dict:
    try:
        data = json.loads(json_str)
        if not path:
            return {"result": data}
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, list):
                idx = int(part)
                current = current[idx]
            elif isinstance(current, dict):
                current = current[part]
            else:
                return {"error": f"无法访问路径 '{part}'，当前值不是容器类型"}
        return {"result": current}
    except json.JSONDecodeError as e:
        return {"error": f"JSON 解析失败: {e}"}
    except (KeyError, IndexError, ValueError) as e:
        return {"error": f"路径查询失败: {e}"}
    except Exception as e:
        return {"error": str(e)}


def _git_status(path: str = ".", **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        result = subprocess.run(
            ["git", "-C", str(p), "status", "--short"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {"path": str(p), "changes": lines[:100], "count": len(lines)}
    except Exception as e:
        return {"error": str(e)}


def _git_diff(path: str = ".", staged: bool = False, **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        cmd = ["git", "-C", str(p), "diff"]
        if staged:
            cmd.append("--staged")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return {"path": str(p), "diff": result.stdout[:8000] or "（无差异）"}
    except Exception as e:
        return {"error": str(e)}


def _git_log(path: str = ".", count: int = 10, **kwargs) -> dict:
    try:
        p = Path(path).resolve()
        result = subprocess.run(
            ["git", "-C", str(p), "log", f"-{count}", "--oneline", "--decorate"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {"path": str(p), "log": lines, "count": len(lines)}
    except Exception as e:
        return {"error": str(e)}


def _env_list(prefix: str = "", **kwargs) -> dict:
    sensitive_keys = {"SECRET", "KEY", "TOKEN", "PASSWORD", "PASSWD", "AUTH", "PRIVATE", "CREDENTIAL"}
    env_vars = {}
    for key, value in sorted(os.environ.items()):
        if prefix and not key.startswith(prefix):
            continue
        upper_key = key.upper()
        if any(s in upper_key for s in sensitive_keys):
            env_vars[key] = "***（已脱敏）***"
        else:
            env_vars[key] = value
    return {"variables": env_vars, "count": len(env_vars)}


_TIMERS: dict[str, float] = {}


def _timer(action: str, timer_id: str = "", **kwargs) -> dict:
    if action == "start":
        tid = timer_id or f"timer_{len(_TIMERS) + 1}"
        _TIMERS[tid] = time.time()
        return {"action": "started", "timer_id": tid, "timestamp": _TIMERS[tid]}
    elif action == "elapsed":
        if not timer_id or timer_id not in _TIMERS:
            return {"error": f"计时器不存在: {timer_id or '（未提供）'}"}
        elapsed = time.time() - _TIMERS[timer_id]
        return {"action": "elapsed", "timer_id": timer_id, "seconds": round(elapsed, 3)}
    return {"error": f"未知操作: {action}"}


def _url_encode(text: str, **kwargs) -> dict:
    return {"result": urllib.parse.quote(text, safe="")}


def _url_decode(text: str, **kwargs) -> dict:
    return {"result": urllib.parse.unquote(text)}


# ===== 安全表达式求值器（替代 eval，避免 RCE）=====
# 仅允许以下 AST 节点类型与白名单函数/常量，杜绝 __import__/().__class__ 等逃逸路径
_CALC_ALLOWED_FUNCS: dict[str, Any] = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": _math.sqrt, "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
    "log": _math.log, "log10": _math.log10, "log2": _math.log2,
    "pow": pow, "ceil": _math.ceil, "floor": _math.floor,
    "int": int, "float": float,
}
_CALC_ALLOWED_CONSTS: dict[str, Any] = {
    "pi": _math.pi, "e": _math.e, "tau": _math.tau,
}
_CALC_BIN_OPS: dict[type, Any] = {
    _ast.Add: _operator.add,
    _ast.Sub: _operator.sub,
    _ast.Mult: _operator.mul,
    _ast.Div: _operator.truediv,
    _ast.FloorDiv: _operator.floordiv,
    _ast.Mod: _operator.mod,
    _ast.Pow: _operator.pow,
}
_CALC_UNARY_OPS: dict[type, Any] = {
    _ast.UAdd: _operator.pos,
    _ast.USub: _operator.neg,
}

class _CalcUnsafeError(ValueError):
    """表达式包含不允许的节点或名字"""


def _calc_eval_node(node: _ast.AST) -> Any:
    """递归求值 AST 节点，遇到非白名单节点立即抛错"""
    if isinstance(node, _ast.Expression):
        return _calc_eval_node(node.body)
    if isinstance(node, _ast.Constant):
        # 仅允许数字常量（int/float/complex/bool）
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise _CalcUnsafeError(f"不允许的常量类型: {type(node.value).__name__}")
    if isinstance(node, _ast.BinOp):
        op_fn = _CALC_BIN_OPS.get(type(node.op))
        if op_fn is None:
            raise _CalcUnsafeError(f"不允许的二元运算: {type(node.op).__name__}")
        return op_fn(_calc_eval_node(node.left), _calc_eval_node(node.right))
    if isinstance(node, _ast.UnaryOp):
        op_fn = _CALC_UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise _CalcUnsafeError(f"不允许的一元运算: {type(node.op).__name__}")
        return op_fn(_calc_eval_node(node.operand))
    if isinstance(node, _ast.Name):
        if node.id in _CALC_ALLOWED_CONSTS:
            return _CALC_ALLOWED_CONSTS[node.id]
        raise _CalcUnsafeError(f"不允许的名字: {node.id}")
    if isinstance(node, _ast.Call):
        if not isinstance(node.func, _ast.Name):
            raise _CalcUnsafeError("仅支持直接函数调用")
        fn = _CALC_ALLOWED_FUNCS.get(node.func.id)
        if fn is None:
            raise _CalcUnsafeError(f"不允许的函数: {node.func.id}")
        if node.keywords:
            raise _CalcUnsafeError("不支持关键字参数")
        args = [_calc_eval_node(a) for a in node.args]
        return fn(*args)
    raise _CalcUnsafeError(f"不允许的语法节点: {type(node).__name__}")


def _calc(expression: str, **kwargs) -> dict:
    """计算数学表达式（安全 AST 求值，禁止属性访问/导入/类反射）"""
    try:
        tree = _ast.parse(expression, mode="eval")
        result = _calc_eval_node(tree)
        return {"expression": expression, "result": result}
    except _CalcUnsafeError as e:
        return {"error": f"表达式不安全: {e}"}
    except Exception as e:
        return {"error": f"计算失败: {e}"}
