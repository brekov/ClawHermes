"""
Mock LLM Provider - 用于测试，不依赖真实 API
"""
import asyncio

from clawhermes.llm.provider import LLMProvider, LLMResponse, StreamChunk


class MockProvider(LLMProvider):
    """模拟 LLM，返回预设响应"""

    def __init__(self, responses: list[str] | None = None):
        super().__init__(model="mock", api_key="mock")
        self.responses = responses or ["这是一个模拟响应。"]
        self.call_index = 0

    def chat(self, messages, tools=None):
        resp = self.responses[self.call_index % len(self.responses)]
        self.call_index += 1

        # 检测是否要触发工具调用
        if tools and any("get_time" in str(t) for t in tools):
            last_msg = messages[-1]["content"].lower() if messages else ""
            if "几点了" in last_msg or "时间" in last_msg:
                return LLMResponse(
                    content=None,
                    tool_calls=[{
                        "id": "call_mock_1",
                        "function": {
                            "name": "get_time",
                            "arguments": "{}",
                        }
                    }],
                    model="mock",
                )

        return LLMResponse(content=resp, model="mock")

    async def chat_async(self, messages, tools=None):
        """异步聊天接口，模拟异步行为"""
        await asyncio.sleep(0)  # 让出控制权，模拟异步操作
        return self.chat(messages, tools)

    async def chat_stream(self, messages, tools=None):
        """流式聊天 — 模拟分块返回文本，最后 yield done"""
        # 检测是否要触发工具调用
        if tools and any("get_time" in str(t) for t in tools):
            last_msg = messages[-1]["content"].lower() if messages else ""
            if "几点了" in last_msg or "时间" in last_msg:
                yield StreamChunk(
                    kind="tool_calls",
                    tool_calls=[{
                        "id": "call_stream_1",
                        "type": "function",
                        "function": {
                            "name": "get_time",
                            "arguments": "{}",
                        },
                    }],
                    model="mock-stream",
                )
                yield StreamChunk(kind="done", usage={"total_tokens": 50})
                return

        resp = self.responses[self.call_index % len(self.responses)]
        self.call_index += 1

        # 模拟分块：每 10 个字符一块
        for i in range(0, len(resp), 10):
            chunk_text = resp[i:i + 10]
            yield StreamChunk(kind="text", content=chunk_text, model="mock-stream")
            await asyncio.sleep(0)

        yield StreamChunk(kind="done", usage={"total_tokens": len(resp)})
