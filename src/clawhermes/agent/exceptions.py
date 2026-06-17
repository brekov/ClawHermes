"""
ClawHermes - 自定义异常类层次
"""
from __future__ import annotations


class ClawHermesError(Exception):
    """ClawHermes 基础异常"""

    def __init__(self, message: str = "", *, detail: str = ""):
        self.detail = detail
        super().__init__(message)


class LLMError(ClawHermesError):
    """LLM 调用相关异常"""


class LLMConnectionError(LLMError):
    """LLM 连接失败"""


class LLMRateLimitError(LLMError):
    """LLM 速率限制"""

    def __init__(self, message: str = "", *, retry_after: float = 0, detail: str = ""):
        self.retry_after = retry_after
        super().__init__(message, detail=detail)


class LLMResponseError(LLMError):
    """LLM 响应解析失败"""


class ToolError(ClawHermesError):
    """工具系统相关异常"""


class ToolNotFoundError(ToolError):
    """工具未找到"""


class ToolExecutionError(ToolError):
    """工具执行失败"""

    def __init__(self, message: str = "", *, tool_name: str = "", detail: str = ""):
        self.tool_name = tool_name
        super().__init__(message, detail=detail)


class ToolBlockedError(ToolError):
    """工具被钩子/策略阻止"""

    def __init__(self, message: str = "", *, tool_name: str = "", reason: str = "", detail: str = ""):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(message, detail=detail)


class MemoryError(ClawHermesError):
    """记忆系统相关异常"""


class MemoryStorageError(MemoryError):
    """记忆存储失败"""

    def __init__(self, message: str = "", *, provider: str = "", detail: str = ""):
        self.provider = provider
        super().__init__(message, detail=detail)


class MemorySearchError(MemoryError):
    """记忆搜索失败"""

    def __init__(self, message: str = "", *, provider: str = "", detail: str = ""):
        self.provider = provider
        super().__init__(message, detail=detail)


class ConfigError(ClawHermesError):
    """配置相关异常"""


class ConfigValidationError(ConfigError):
    """配置校验失败"""

    def __init__(self, message: str = "", *, field: str = "", detail: str = ""):
        self.field = field
        super().__init__(message, detail=detail)


class ConfigNotFoundError(ConfigError):
    """配置文件未找到"""


class SessionError(ClawHermesError):
    """会话相关异常"""


class SessionNotFoundError(SessionError):
    """会话未找到"""

    def __init__(self, message: str = "", *, session_id: str = "", detail: str = ""):
        self.session_id = session_id
        super().__init__(message, detail=detail)


class SessionExpiredError(SessionError):
    """会话已过期"""

    def __init__(self, message: str = "", *, session_id: str = "", detail: str = ""):
        self.session_id = session_id
        super().__init__(message, detail=detail)
