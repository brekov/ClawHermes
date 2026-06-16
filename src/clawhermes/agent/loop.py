"""
ClawHermes - Agent 核心循环（思考-行动）
融合 Hermes 的三层 Prompt 和 OpenClaw 的钩子体系
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from clawhermes.agent.prompt import SystemPrompt
from clawhermes.llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


# ===== 钩子系统（来自 OpenClaw） =====

class HookPoint:
    """钩子定义"""
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    BEFORE_AGENT_RUN = "before_agent_run"
    BEFORE_AGENT_REPLY = "before_agent_reply"
    AFTER_AGENT_END = "after_agent_end"
    MODEL_CALL_STARTED = "model_call_started"
    MODEL_CALL_ENDED = "model_call_ended"


class HookManager:
    """钩子管理器 - 注册和触发"""

    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def register(self, point: str, handler: Callable):
        """注册钩子"""
        if point not in self._hooks:
            self._hooks[point] = []
        self._hooks[point].append(handler)

    def trigger(self, point: str, **kwargs) -> dict[str, Any]:
        """触发钩子，返回所有 handler 的返回值和改写"""
        results = {}
        for handler in self._hooks.get(point, []):
            try:
                result = handler(**kwargs)
                if result:
                    results.update(result)
            except Exception as e:
                logger.warning(f"Hook {point} failed: {e}")
        return results


# ===== 工具注册与调度 =====

@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    parameters: dict
    handler: Callable
    group: str = "core"
    parallel_safe: bool = False
    timeout_ms: int = 30000
    require_confirm: bool = False


class ToolRegistry:
    """工具注册中心 - 自动发现 + 手动注册"""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDef]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        """生成 OpenAI-compatible tool schemas"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]


class ToolDispatcher:
    """工具调度器 - 支持并行/串行规则"""

    NEVER_PARALLEL = frozenset({"clarify", "confirm"})
    PARALLEL_SAFE = frozenset({
        "web_search", "web_fetch", "read_file",
        "memory_search", "skills_list",
    })
    PATH_SCOPED = frozenset({"write_file", "patch", "read_file"})

    def __init__(self, registry: ToolRegistry, hook_manager: HookManager):
        self.registry = registry
        self.hooks = hook_manager

    def execute(self, tool_calls: list[dict], context: dict) -> list[dict]:
        """执行一组工具调用，自动判断并行/串行"""
        results = []

        # 按类型分组
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            args_str = tc.get("function", {}).get("arguments", "{}")
            tool_id = tc.get("id", "")

            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}

            tool_def = self.registry.get(name)
            if not tool_def:
                results.append(self._error_result(tool_id, name, f"未知工具: {name}"))
                continue

            # before_tool_call 钩子
            hook_result = self.hooks.trigger(
                HookPoint.BEFORE_TOOL_CALL,
                tool_name=name,
                tool_args=args,
                context=context,
            )
            if hook_result.get("blocked"):
                results.append(self._error_result(
                    tool_id, name, hook_result.get("reason", "被钩子阻止")
                ))
                continue
            if hook_result.get("override_args"):
                args = hook_result["override_args"]

            # 执行
            try:
                result = tool_def.handler(**args)
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            except Exception as e:
                results.append(self._error_result(tool_id, name, str(e)))

            # after_tool_call 钩子
            self.hooks.trigger(
                HookPoint.AFTER_TOOL_CALL,
                tool_name=name,
                tool_args=args,
                tool_result=result,
                duration_ms=0,
            )

        return results

    def _error_result(self, tool_id, name, error):
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "name": name,
            "content": json.dumps({"error": error}, ensure_ascii=False),
        }


# ===== Agent 核心 =====

@dataclass
class AgentConfig:
    """Agent 配置"""
    max_iterations: int = 20
    max_tool_calls_per_round: int = 10
    queue_mode: str = "steer"


class Agent:
    """Agent 核心 - 思考-行动循环"""

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        config: AgentConfig | None = None,
    ):
        self.llm = llm_provider
        self.prompt = SystemPrompt()
        self.tools = tool_registry or ToolRegistry()
        self.hooks = HookManager()
        self.dispatcher = ToolDispatcher(self.tools, self.hooks)
        self.config = config or AgentConfig()
        self._interrupt = threading.Event()

    def chat(self, user_message: str, session_id: str = "") -> str:
        """简单接口：输入用户消息，返回最终响应"""
        messages = []
        messages.append({
            "role": "system",
            "content": self.prompt.build(),
        })
        messages.append({"role": "user", "content": user_message})

        for iteration in range(self.config.max_iterations):
            # before_agent_run 钩子
            hook_result = self.hooks.trigger(
                HookPoint.BEFORE_AGENT_RUN,
                messages=messages,
                iteration=iteration,
            )
            if hook_result.get("abort"):
                return hook_result.get("response", "")

            if self._interrupt.is_set():
                return "（已中断）"

            # 调用 LLM
            self.hooks.trigger(HookPoint.MODEL_CALL_STARTED)
            try:
                response: LLMResponse = self.llm.chat(
                    messages,
                    tools=self.tools.schemas() if self.tools.list() else None,
                )
            except Exception as e:
                return f"LLM 调用失败: {e}"

            self.hooks.trigger(HookPoint.MODEL_CALL_ENDED, response=response)

            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            })

            # 没有 tool_calls → 返回最终响应
            if not response.tool_calls:
                # before_agent_reply 钩子
                hook_result = self.hooks.trigger(
                    HookPoint.BEFORE_AGENT_REPLY,
                    response=response.content or "",
                )
                final = hook_result.get("override_response", response.content or "")
                return final

            # 执行工具调用
            tool_results = self.dispatcher.execute(
                response.tool_calls,
                context={"session_id": session_id, "iteration": iteration},
            )
            messages.extend(tool_results)

        return "（已达最大迭代次数）"

    def interrupt(self):
        """中断当前对话"""
        self._interrupt.set()
