"""
ClawHermes - 子 Agent 委派系统（F12）
支持并行子任务，防死锁，深度限制
"""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from clawhermes.agent.loop import Agent, AgentConfig
from clawhermes.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# 子 Agent 禁止使用的工具（防止副作用）
DELEGATE_BLOCKED_TOOLS = frozenset({
    "delegate_task",    # 禁止递归委派
    "clarify",          # 禁止用户交互
    "memory_save",      # 禁止写共享记忆
    "exec",             # 禁止执行命令（安全）
})

MAX_DEPTH = 2       # 最大嵌套深度
MAX_CONCURRENT = 3  # 最大并发子 Agent 数


class DelegateManager:
    """子 Agent 委派管理器"""

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry,
        memory_manager=None,
        skill_manager=None,
    ):
        self.llm = llm_provider
        self.tool_registry = tool_registry
        self.memory = memory_manager
        self.skills = skill_manager
        self._pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)
        self._paused = threading.Event()

    def delegate(
        self,
        tasks: list[dict],
        parent_depth: int = 0,
        context: dict | None = None,
    ) -> list[dict]:
        """
        委派任务给子 Agent
        :param tasks: [{"id": str, "description": str, "instructions": str}]
        :param parent_depth: 父 Agent 深度
        :param context: 上下文信息
        :return: [{"task_id": str, "result": str, "error": str}]
        """
        depth = parent_depth + 1
        if depth > MAX_DEPTH:
            return [{
                "task_id": t.get("id", ""),
                "result": "",
                "error": f"超过最大委派深度 ({MAX_DEPTH})",
            } for t in tasks]

        results = []
        with self._pool as executor:
            future_map = {}
            for task in tasks:
                if self._paused.is_set():
                    results.append({
                        "task_id": task.get("id", ""),
                        "result": "",
                        "error": "委派已暂停",
                    })
                    continue

                future = executor.submit(
                    self._run_sub_agent, task, depth, context or {},
                )
                future_map[future] = task.get("id", "")

            for future in as_completed(future_map):
                task_id = future_map[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({
                        "task_id": task_id,
                        "result": "",
                        "error": str(e),
                    })

        return results

    def _run_sub_agent(
        self, task: dict, depth: int, context: dict
    ) -> dict:
        """运行单个子 Agent"""
        task_id = task.get("id", uuid.uuid4().hex[:8])
        description = task.get("description", "")
        instructions = task.get("instructions", description)

        # 构建子 Agent（继承父配置，禁用危险工具）
        sub_config = AgentConfig(max_iterations=15)
        sub_agent = Agent(
            llm_provider=self.llm,
            tool_registry=self.tool_registry,
            config=sub_config,
            memory_manager=None,  # 子 Agent 不写共享记忆
            skill_manager=None,
        )

        # 注入禁止工具集的钩子
        def block_tools(**kw) -> dict:
            tool_name = kw.get("tool_name", "")
            if tool_name in DELEGATE_BLOCKED_TOOLS:
                return {"blocked": True, "reason": f"子 Agent 禁止使用 {tool_name}"}
            return {}

        sub_agent.hooks.register("before_tool_call", block_tools)

        try:
            result = sub_agent.chat(
                instructions,
                session_id=f"sub_{task_id}",
            )
            return {"task_id": task_id, "result": result, "error": ""}
        except Exception as e:
            return {"task_id": task_id, "result": "", "error": str(e)}

    def pause(self):
        """暂停新的委派（已有子 Agent 不受影响）"""
        self._paused.set()

    def resume(self):
        """恢复委派"""
        self._paused.clear()
