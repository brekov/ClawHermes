# ClawHermes · 架构设计文档

> 版本：v1.0
> 日期：2026-06-16
> 状态：已实现

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                      Gateway 层                          │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐    │
│  │ CLI     │ │ 微信     │ │Telegram │ │ ...更多  │    │
│  └────┬────┘ └────┬─────┘ └────┬────┘ └────┬─────┘    │
│       │           │            │           │           │
│  ┌────▼───────────▼────────────▼───────────▼─────────┐ │
│  │              Session Manager                       │ │
│  │    会话路由 / 消息队列 / 上下文管理                 │ │
│  └────────────────────┬──────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    Agent 核心层                          │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │          System Prompt 三层架构                  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐         │   │
│  │  │ Stable   │ │ Context  │ │ Volatile │         │   │
│  │  │ (身份/指 │ │ (项目/   │ │ (记忆/时 │         │   │
│  │  │  导)     │ │  场景)   │ │  间戳)   │         │   │
│  │  └──────────┘ └──────────┘ └──────────┘         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │          Agent Loop (思考-行动循环)              │   │
│  │  LLM 调用 → 工具执行 → 结果合并 → 继续/结束     │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────┐    │
│  │ 工具系统   │ │ 记忆系统   │ │ 技能系统         │    │
│  │ ·注册/调   │ │ ·Mem       │ │ ·Skill 加载/管理 │    │
│  │  度        │ │  oryMana  │ │ ·Backgroun      │    │
│  │ ·钩子体系  │ │  ger       │ │  d Review       │    │
│  │ ·策略引擎  │ │ ·向量检索  │ │ ·Curator 维护    │    │
│  └────────────┘ └────────────┘ └──────────────────┘    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    基础服务层                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ LLM      │ │ 持久化   │ │ 凭证管理 │ │ 子Agent  │  │
│  │ Provider │ │ (SQLite+ │ │ (Cred    │ │ 委派     │  │
│  │ 适配器   │ │  JSONL)  │ │ entialP  │ │          │  │
│  │          │ │          │ │ ool)     │ │          │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 模块职责

### 2.1 Gateway 层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `gateway/run.py` | Gateway 生命周期管理 | `GatewayRunner` |
| `gateway/session.py` | 会话路由、消息队列 | `SessionManager` |
| `gateway/delivery.py` | 消息投递（发送/编辑/删除） | `DeliveryService` |
| `gateway/platforms/` | 各渠道适配器 | `BasePlatformAdapter` |
| `gateway/config.py` | Gateway 配置 | `GatewayConfig` |

### 2.2 Agent 核心层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `agent/loop.py` | 思考-行动主循环 | `Agent` / `AgentConfig` |
| `agent/prompt.py` | 三层 System Prompt 组装 | `SystemPrompt` / `StableLayer` / `ContextLayer` / `VolatileLayer` |
| `agent/context.py` | F10: 上下文管理与压缩 | `ContextEngine` (ABC) / `LLMCompressor` / `NoopCompressor` |
| `agent/memory.py` | 记忆管理器 | `MemoryManager` / `MemoryProvider` (ABC) |
| `agent/delegate.py` | F12: 子 Agent 委派 | `DelegateManager` / 深度限制 / 并发执行 |
| `skills/manager.py` | 技能加载/管理/自进化 | `SkillManager` / `BackgroundReview` / `Curator` |
| `agent/loop.py` | 工具注册/调度/钩子 | `ToolRegistry` / `ToolDispatcher` / `HookManager` |

### 2.3 工具系统

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `tools/registry.py` | 工具注册与发现 | `ToolRegistry` |
| `tools/dispatch.py` | 工具调度（并行/串行规则） | `ToolDispatcher` |
| `tools/hooks.py` | 钩子管理 | `HookManager` / `Hook` |
| `tools/policy.py` | 策略引擎 | `PolicyEngine` / `Policy` / `Profile` |
| `tools/builtin/` | 内置工具实现 | — |

### 2.4 LLM 层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `llm/provider.py` | Provider 抽象 | `LLMProvider` (ABC) |
| `llm/router.py` | 模型路由 | `ModelRouter` |
| `llm/credential_pool.py` | 多凭证管理 | `CredentialPool` |
| `llm/providers/` | 各提供商实现 | — |

### 2.5 存储层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `storage/session.py` | 会话持久化 | `SessionStore` |
| `storage/transcript.py` | 对话记录（JSONL 树形） | `TranscriptStore` |
| `storage/vector.py` | 向量检索 | `VectorStore` |

---

## 3. 核心流程

### 3.1 对话流程

```
用户消息 → Gateway → Session 路由 → System Prompt 组装
    ↓
Agent Loop 开始
    ↓
LLM 调用（携带 messages + tools）
    ↓
有工具调用？─────是────→ 工具调度
    ↓                          ↓
   否                      before_tool_call 钩子
    ↓                          ↓
返回响应                 工具执行（并行/串行）
    ↓                          ↓
Background Review        after_tool_call 钩子
    ↓                          ↓
写入记忆/技能 ←──────── 结果合并回 messages
    ↓
返回用户
```

### 3.2 消息队列模式（来自 OpenClaw）

```
消息到达 → 当前 Agent 状态？
    ├── 空闲 → 直接处理
    ├── 运行中 → 按模式：
    │   ├── steer → 注入当前轮次，当前工具完成后自然融入
    │   ├── followup → 排队等下一轮
    │   ├── collect → 等待安静窗口后合并
    │   └── interrupt → 中止当前，执行新消息
    └── 忙碌 → 排队
```

### 3.3 自进化流程（来自 Hermes）

```
每轮对话结束
    ↓
Background Review 触发
    ├── 检查是否有新记忆 → 写入 MemoryProvider
    ├── 检查是否有新技能 → 更新或创建 SKILL.md
    └── 更新用户画像
    ↓
Curator（每7天）
    ├── 合并重叠技能
    ├── 标记30天未用技能为 stale
    ├── 归档90天未用技能（可恢复）
    └── 绝不动 bundled/hub 技能
```

---

## 4. 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | 生态丰富、团队熟悉 |
| LLM 统一接口 | **litellm** | 100+ 模型统一接口，省去自己封装 |
| Web 框架 | FastAPI | 原生 async、自动文档 |
| 数据库 | SQLite → PostgreSQL | 轻量起步，按需升级 |
| 向量库 | ChromaDB | 纯 Python，零配置嵌入 |
| 异步框架 | asyncio | Python 原生异步 |
| 配置管理 | Pydantic Settings | 类型安全，schema 校验 |
| 包管理 | uv | 比 pip 快 10-100 倍 |
| 测试 | pytest + pytest-asyncio | 行业标准 |
| 代码质量 | ruff + mypy | 零配置 lint + 类型检查 |

---

## 5. 模块依赖图

```
gateway/run.py
    ├── gateway/session.py → agent/loop.py
    │   ├── agent/prompt.py → agent/context.py
    │   ├── agent/tools.py
    │   │   ├── tools/registry.py
    │   │   ├── tools/dispatch.py
    │   │   ├── tools/hooks.py
    │   │   └── tools/policy.py
    │   ├── agent/memory.py → storage/vector.py
    │   ├── agent/skills.py
    │   └── agent/delegate.py
    ├── llm/router.py → llm/provider.py → llm/credential_pool.py
    └── storage/session.py → storage/transcript.py

    无循环依赖 ✓
```
