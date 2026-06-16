# ClawHermes · 接口契约文档

> 版本：v0.6-draft
> 日期：2026-06-16
> 说明：定义各模块之间的接口规格，供并行开发和测试 mock 使用

---

## 1. LLM Provider 接口

### `LLMProvider`

```python
class LLMProvider:
    """LLM 调用封装"""

    def __init__(
        self,
        model: str,                    # 模型名，如 "deepseek/deepseek-chat"
        api_key: str | None = None,    # API 密钥
        base_url: str | None = None,   # 自定义端点
        max_tokens: int = 64000,       # 上下文窗口
        temperature: float = 0.7,      # 温度
        timeout_ms: int = 60000,       # 超时
        credential_pool: CredentialPool | None = None,  # 多凭证池
    )

    def chat(
        self,
        messages: list[dict],           # 消息列表 [{"role":"user","content":"..."}]
        tools: list[dict] | None = None, # OpenAI-compatible tool schemas
    ) -> LLMResponse: ...
```

### `LLMResponse`

```python
@dataclass
class LLMResponse:
    content: str | None          # 文本回复
    tool_calls: list[dict] | None  # 工具调用 [{id, function: {name, arguments}}]
    usage: dict | None           # Token用量
    model: str                   # 实际使用的模型
    duration_ms: float           # 耗时
```

### `CredentialPool`

```python
class CredentialPool:
    def __init__(self, api_keys: list[str], strategy: str = "round_robin")
    def get_key(self) -> str | None         # 获取可用 key
    def mark_failed(self, key: str, status_code: int | None = None)  # 标记失败
```

---

## 2. Agent 核心接口

### `Agent`

```python
class Agent:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        config: AgentConfig | None = None,
        memory_manager: MemoryManager | None = None,
        skill_manager: SkillManager | None = None,
    )

    def chat(self, user_message: str, session_id: str = "") -> str
        """输入用户消息，返回最终回复"""

    def interrupt(self)
        """中断当前对话"""

    def get_conversation(self) -> list[dict]
        """获取最近对话记录（供 Background Review）"""
```

### `SystemPrompt`

```python
class SystemPrompt:
    stable: StableLayer     # 身份 + 工具指导（缓存）
    context: ContextLayer   # 项目上下文
    volatile: VolatileLayer # 记忆快照 + 时间戳

    def build(self) -> str           # 组装完整 system prompt
    def invalidate_cache(self)       # 清除 stable 缓存
```

### `HookManager`

```python
class HookManager:
    def register(self, point: str, handler: Callable)  # 注册钩子
    def trigger(self, point: str, **kwargs) -> dict     # 触发钩子

# 预定义钩子点
HookPoint.BEFORE_TOOL_CALL    # 工具调用前 → 可改写参数/阻止
HookPoint.AFTER_TOOL_CALL     # 工具调用后 → 可记录耗时
HookPoint.BEFORE_AGENT_RUN    # 对话运行前 → 可阻止
HookPoint.BEFORE_AGENT_REPLY  # 回复用户前 → 可改写回复
HookPoint.AFTER_AGENT_END     # 对话结束后 → 用于 Background Review
HookPoint.MODEL_CALL_STARTED  # LLM 调用开始
HookPoint.MODEL_CALL_ENDED    # LLM 调用结束
```

---

## 3. 工具系统接口

### `ToolRegistry`

```python
class ToolRegistry:
    def register(self, tool: ToolDef)        # 注册工具
    def get(self, name: str) -> ToolDef | None  # 按名查找
    def list(self) -> list[ToolDef]           # 列出所有工具
    def schemas(self) -> list[dict]           # 生成 OpenAI schema
```

### `ToolDef`

```python
@dataclass
class ToolDef:
    name: str           # 工具名
    description: str    # 描述
    parameters: dict    # JSON Schema
    handler: Callable   # 实现函数
    group: str = "core" # 分组
    parallel_safe: bool = False  # 是否可并行
    timeout_ms: int = 30000
    require_confirm: bool = False
```

### `ToolDispatcher`

```python
class ToolDispatcher:
    def __init__(self, registry: ToolRegistry, hook_manager: HookManager)

    def execute(
        self,
        tool_calls: list[dict],   # LLM返回的工具调用
        context: dict,            # 执行上下文
    ) -> list[dict]              # 工具结果列表
```

### 内置工具注册函数

```python
def register_builtin_tools(registry: ToolRegistry)
# 注册：session_status, read_file, write_file, exec, get_time,
#       web_search, memory_search, memory_save
```

---

## 4. 记忆系统接口

### `MemoryProvider`（抽象基类）

```python
class MemoryProvider(ABC):
    @abstractmethod
    def save(self, item: MemoryItem)
    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[MemoryItem]
    @abstractmethod
    def get_recent(self, limit: int = 10) -> list[MemoryItem]
```

### `MemoryManager`

```python
class MemoryManager:
    def add_provider(self, provider: MemoryProvider)   # 添加存储后端
    def save(self, content: str, importance: float = 0.5, scope=MemoryScope.USER)
    def search(self, query: str, limit: int = 5) -> list[MemoryItem]
    def get_recent(self, limit: int = 10) -> list[MemoryItem]
    def snapshot(self, query: str | None = None) -> str  # VolatileLayer 用
```

---

## 5. 技能系统接口

### `SkillManager`

```python
class SkillManager:
    def __init__(self, skills_dir: str | Path)

    def list(self, status: str | None = None) -> list[Skill]
    def get(self, name: str) -> Skill | None
    def create(self, name: str, content: str, description: str = "", category: str = "general") -> Skill
    def update(self, name: str, **kwargs) -> Skill | None
    def record_usage(self, name: str)
    def get_context(self, active_skills: list[str] | None = None) -> str
```

### `BackgroundReview`

```python
class BackgroundReview:
    def __init__(self, llm_provider, memory_manager, skill_manager)
    def review(self, conversation: list[dict]) -> dict
        # 返回: {"memories": [...], "skills": [...]}
    def apply(self, conversation: list[dict])
        # 审查并写入记忆/技能
```

### `Curator`

```python
class Curator:
    def __init__(self, skill_manager: SkillManager)
    def run(self, dry_run: bool = False) -> dict
        # 返回: {"stale": n, "archived": n, "active": n}
```

---

## 6. Gateway 接口

### HTTP API

```
POST /init     { api_key, model?, base_url?, max_iterations? }
              → { status, model, tools, skills, chroma }

POST /chat     { message, session_id? }
              → { response, session_id, model }

GET  /health  → { status, version, uptime_seconds, tools, skills, sessions }

GET  /tools   → { tools: [{name, description, parallel_safe}] }

POST /memory/save   ?content=xxx&importance=0.5 → { status }
GET  /memory/search ?query=xxx → { results: [{content, importance}] }

GET  /skills  ?status=active → { skills: [...] }
POST /skills/create ?name=xxx&content=xxx → { status, name }

POST /curator/run ?dry_run=false → { status, stats }

GET  /sessions → { sessions: [...], count }

POST /channels/feishu/start           ?app_id&app_secret → { status }
POST /channels/feishu/start-from-env   (从环境变量读取) → { status }
POST /channels/wechat/start            ?corp_id&corp_secret&agent_id → { status }
POST /channels/wechat/public/start     ?app_id&app_secret&token&encoding_aes_key → { status }
POST /channels/wechat/callback         { body } → response
POST /channels/qq/start                ?ws_url&token → { status }
POST /channels/telegram/start          ?token → { status }
POST /channels/webhook/receive         ?platform&chat_id&text → { status }
GET  /channels                         → { channels: [...], count }
GET  /channels → { channels: [...], count }
```

### Channel Bridge (Node.js)

```
POST /send  { channel, to, text } → { success, messageId? }
GET  /health → { status, weixin, feishu }
```

---

## 7. 渠道适配器接口

```python
class PlatformAdapter(ABC):
    @abstractmethod
    def send_text(self, chat_id: str, text: str) -> SendResult
    @abstractmethod
    def start(self, message_handler: Callable[[MessageEvent], None])
    @abstractmethod
    def stop(self)
```

---

## 8. 外部依赖接口

| 依赖 | 用途 | 接口稳定性 |
|------|------|-----------|
| litellm.completion() | 调用LLM | 稳定，OpenAI-compatible |
| chromadb.PersistentClient() | 向量存储 | 稳定 |
| lark-oapi ws.Client() | 飞书 WebSocket | 稳定 |
| wechatpy.WeChatClient | 微信 API | 稳定 |
| OneBot (go-cqhttp) | QQ 协议 | 稳定 |
