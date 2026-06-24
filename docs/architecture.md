# ClawHermes · 架构设计文档

> 版本：v2.1
> 日期：2026-06-23
> 基线版本：v0.15.0
> 状态：已实现 ChannelConfigLoader、飞书 26 字段、微信双模式、YAML ${VAR} 配置分层

---

## 1. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Channel 适配层                                │
│   ChannelAdapter ABC + CLI / REST / WebSocket          │
│   (飞书/微信 → 子仓库 clawhermes-lark / clawhermes-weixin)                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                          Gateway 层                                  │
│        FastAPI REST 服务（33 个端点 · Cron调度 · Docker沙箱）         │
│              CLI 接口 / HTTP API / WebSocket                         │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                        Agent 核心层                                  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │            三层 System Prompt (stable / context / volatile)     │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │             Agent Loop (Think-Act) + 异步钩子体系               │  │
│  │     LLM调用 → 工具执行 → 结果 → ACE自适应压缩 → 继续/结束      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 工具系统  │ │ 记忆系统  │ │ 技能系统  │ │ Cron调度 │ │ 子Agent  │  │
│  │ ·35工具  │ │ ·Memory  │ │ ·Skill   │ │ ·cron    │ │ ·委派    │  │
│  │  3级Prof │ │  Manager │ │  加载/   │ │ ·interval│ │ ·深度限制│  │
│  │ ·钩子体系 │ │ ·向量检索 │ │  管理    │ │ ·oneshot │ │ ·并发执行│  │
│  │ ·策略引擎 │ │ ·ChromaDB│ │ ·Review  │ │ ·asyncio │ │          │  │
│  │ ·Docker  │ │ ·用户画像 │ │ ·Curator │ │  原生    │ │          │  │
│  │  沙箱    │ │          │ │ ·Hub联邦 │ │          │ │          │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                                      │
│  ┌──────────┐                                                       │
│  │ MCP 集成 │  MCPClient (stdio+HTTP) · MCPRegistry · 动态工具发现  │
│  └──────────┘                                                       │
│                                                                      │
│  ┌──────────┐ ┌──────────────────────────────────────────────────┐  │
│  │ ACE 自适 │ │ 消息队列层（✅ v0.14.0）                          │  │
│  │ 应上下文 │ │ steer / followup / collect / interrupt 四模式     │  │
│  │ 压缩引擎 │ │ Profile 隔离 · 设备安全（规划中）                  │  │
│  └──────────┘ └──────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                         基础服务层                                    │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ LLM        │ │ 持久化       │ │ 凭证管理     │ │ MCP 客户端   │  │
│  │ Provider   │ │ (SQLite WAL │ │ Credential   │ │ (✅v0.14.0)  │  │
│  │ litellm    │ │  + JSONL    │ │ Pool 4策略   │ │ 动态工具发现 │  │
│  │ 132+模型   │ │  + ChromaDB)│ │              │ │              │  │
│  └────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.1 竞品研究新增架构组件

以下组件从竞品研究中识别，将逐步引入：

| 组件 | 来源 | 说明 |
|------|------|------|
| MCP 客户端层 | Hermes | 动态工具发现和注册，MCP 协议客户端模式 |
| 消息队列层 | OpenClaw | steer/followup/collect/interrupt 四模式消息处理 |
| Profile 隔离层 | Hermes | 多 Profile 并发运行，目录级隔离 |
| 设备安全层 | OpenClaw | DM 配对 + 签名挑战，设备级安全认证 |

---

## 2. 模块职责

### 2.1 Gateway 层

| 模块 | 职责 | 关键类/函数 |
|------|------|-------------|
| `gateway/app.py` | FastAPI REST 服务（33 个端点） | `app` (FastAPI instance) |
| `gateway/app.py` | Agent 初始化与组件装配 | `_create_agent_components()` / `_auto_init()` |
| `gateway/app.py` | Cron 调度端点（6个） | `create_cron_job` / `list_cron_jobs` / `get_cron_job` / `delete_cron_job` / `pause_cron_job` / `resume_cron_job` |
| `gateway/app.py` | 会话管理端点（3个） | `list_sessions` / `get_session` / `delete_session` |
| `gateway/app.py` | 记忆端点（2个） | `save_memory` / `search_memory` |
| `gateway/app.py` | 技能端点（2个） | `list_skills` / `create_skill` |
| `gateway/app.py` | 核心端点（3个） | `initialize` / `chat` / `health` |
| `gateway/app.py` | 工具端点（1个） | `list_tools` |
| `gateway/app.py` | Curator端点（1个） | `run_curator` |
| `gateway/setup.py` | Provider 配置管理 | provider config functions |

### 2.2 Agent 核心层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `agent/loop.py` | 思考-行动主循环 + 钩子管理 + 工具调度 | `Agent` / `AgentConfig` / `HookManager` / `ToolDispatcher` / `HookPoint` |
| `agent/prompt.py` | 三层 System Prompt 组装 | `SystemPrompt` / `StableLayer` / `ContextLayer` / `VolatileLayer` |
| `agent/context.py` | 上下文管理与压缩 | `ContextEngine` (ABC) / `LLMCompressor` / `NoopCompressor` |
| `agent/ace.py` | 自适应上下文引擎（ACE） | `AdaptiveContextEngine` / `ConversationType` / `CompressionStrategy` |
| `agent/memory.py` | 记忆管理器 | `MemoryManager` / `MemoryProvider` (ABC) |
| `agent/delegate.py` | 子 Agent 委派 | `DelegateManager` / 深度限制 / 并发执行 |
| `agent/scheduler.py` | Cron 调度器 | `CronScheduler` / `ScheduleSpec` / `ScheduleMode` / `JobStatus` |
| `agent/session.py` | 会话持久化（SQLite WAL） | `SessionManager` |
| `agent/exceptions.py` | 自定义异常类层次 | `ClawHermesError` → 5大类10子类 + 扩展异常 |
| `agent/agent_mgr.py` | 多 Agent 管理 | — |

### 2.3 工具系统

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `tools/registry.py` | 工具注册与发现 | `ToolRegistry` / `ToolDef` |
| `tools/dispatch.py` | 工具调度（并行/串行规则） | `ToolDispatcher` |
| `tools/hooks.py` | 钩子管理（同步+异步） | `HookManager` / `Hook` |
| `tools/policy.py` | 策略引擎 | `PolicyEngine` / `Policy` / `Profile` |
| `tools/builtin.py` | 26个内置工具 + 3级 Profile | `MINIMAL_TOOLS` / `STANDARD_TOOLS` / `FULL_TOOLS` / `PROFILE_MAP` |
| `tools/sandbox.py` | Docker 沙箱执行环境 | `DockerSandbox` / `SandboxPool` / `SandboxResult` |

### 2.4 LLM 层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `llm/provider.py` | Provider 抽象 + CredentialPool + chat_async | `LLMProvider` / `LLMResponse` / `CredentialPool` |
| `llm/router.py` | 模型路由 | `ModelRouter` |
| `llm/credential_pool.py` | 多凭证管理（4策略） | `CredentialPool` (fill_first / round_robin / random / least_used) |
| `llm/providers/` | 各提供商实现 | — |

### 2.5 存储层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `storage/session.py` | 会话持久化（SQLite WAL） | `SessionManager` |
| `storage/transcript.py` | 对话记录（JSONL 树形） | `TranscriptStore` |
| `storage/vector.py` | 向量检索 | `VectorStore` |
| `storage/chroma_memory.py` | ChromaDB 向量记忆存储 | `ChromaMemoryProvider` |

### 2.6 Channel 层

ClawHermes 通过 **Channel Adapter SDK** 提供标准化渠道接口，渠道适配器以 **git 子仓库** 形式独立维护，
遵循**多级实现策略**：

```
新渠道需求
    │
    ▼
1. 有官方为 Agent 开发的 SDK？ → git submodule 引入 + 适配 ChannelAdapter  ← 首选
    │ 无
    ▼
2. 有社区为 Agent 开发的 SDK？ → git submodule 引入 + 适配 ChannelAdapter   ← 次选
    │ 无
    ▼
3. 可复刻官方 Agent SDK？ → git submodule + 复刻核心逻辑 + ChannelAdapter    ← 三选
    │ 不可
    ▼
4. 有官方其他 SDK？ → git submodule 引入 + 适配 ChannelAdapter              ← 四选
    │ 不可
    ▼
5. 裸 API 实现 → git submodule + HTTP/WS 客户端 + ChannelAdapter            ← 末选
```

**已实现模块**：

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `channel/adapter.py` | ChannelAdapter ABC + 内置适配器 | `ChannelAdapter` / `CLIAdapter` / `RESTAdapter` / `WebSocketAdapter` |
| `channel/config.py` | 渠道配置管理（YAML + ${VAR} 插值） | `ChannelConfigLoader` |
| `channel/router.py` | 消息路由 + 队列 + 配对 | `ChannelRouter` / `SessionRouter` / `DMPairingManager` |

**待实现模块**（Phase 3 后续）：

| 模块 | 职责 |
|------|------|
| `channel/streaming.py` | Block Streaming 分块发送（Phase 3） |

**渠道适配器（git 子仓库，外部维护）**：

| 子仓库 | 渠道 | 实现级别 | 状态 |
|--------|------|:---:|:---:|
| `clawhermes-lark` | 飞书 | 1（官方 SDK: lark-oapi） | ✅ |
| `clawhermes-weixin` | 微信（个人 + 企业） | 1（社区 SDK: wechatpy） | ✅ |
| `clawhermes-qq` | QQ | 2（社区 SDK: Hermes 集成） | ✅ |
| — | Telegram | 3（复刻 Hermes bot_telegram） | 📋 v0.16.0 |
| — | Discord | 4（社区 SDK: discord.py） | 📋 v0.16.0 |
| — | Slack | 4（官方 SDK: slack-bolt） | 📋 v0.16.0 |

### 2.7 Skill Hub 层

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `skills/hub.py` | 联邦技能中心 | `SkillManifest` / `SkillHub` |
| `skills/manager.py` | 技能加载/管理/自进化 | `SkillManager` / `BackgroundReview` / `Curator` |

---

## 3. 核心流程

### 3.1 对话流程

```
用户消息 → Channel适配器 → Gateway → Session路由 → System Prompt组装
    ↓
Agent Loop 开始
    ↓
before_agent_run 钩子
    ↓
LLM 调用（携带 messages + tools）
    ↓
model_call_started / model_call_ended 钩子
    ↓
有工具调用？─────是────→ before_tool_call 钩子
    ↓                          ↓
   否                      工具执行（并行/串行）
    ↓                          ↓
ACE 自适应压缩              after_tool_call 钩子
    ↓                          ↓
before_agent_reply 钩子 ←── 结果合并回 messages
    ↓
返回响应
    ↓
after_agent_end 钩子
    ↓
Background Review（异步线程）
    ├── 检查是否有新记忆 → 写入 MemoryProvider
    ├── 检查是否有新技能 → 更新或创建 SKILL.md
    └── 更新用户画像
    ↓
返回用户
```

### 3.2 消息队列流程（✅ v0.14.0，借鉴 OpenClaw）

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

**设计要点**：
- `steer` 模式适合实时纠偏（用户修正指令方向）
- `followup` 模式适合追加信息（不打断当前执行流）
- `collect` 模式适合批量输入（等待用户输入完毕后合并处理）
- `interrupt` 模式适合紧急中断（安全停止、优先级变更）
- 默认模式：`steer`（配置项 `CH_QUEUE_MODE`）

### 3.3 自进化流程

```
每轮对话结束
    ↓
Background Review 触发（异步线程）
    ├── 检查是否有新记忆 → 写入 MemoryProvider
    ├── 检查是否有新技能 → 更新或创建 SKILL.md
    └── 更新用户画像
    ↓
Curator（每小时检查，7天周期）
    ├── 合并重叠技能
    ├── 标记30天未用技能为 stale
    ├── 归档90天未用技能（可恢复）
    └── 绝不动 bundled/hub 技能
```

### 3.4 Cron 调度流程

```
创建调度任务 → CronScheduler
    ↓
ScheduleSpec 解析
    ├── cron → 按分钟/小时/星期规则触发
    ├── interval → 按固定间隔触发
    └── oneshot → 延迟一次触发
    ↓
调度线程轮询（1秒间隔）
    ↓
到达触发时间 → 执行器回调
    ↓
Agent.chat(task, session_id=sid)
    ↓
JobStatus 状态流转
    PENDING → RUNNING → COMPLETED / FAILED
    可暂停(PAUSED) / 可取消(CANCELLED)
    ↓
JSON 持久化（jobs.json）
```

### 3.5 技能联邦发布/安装流程

```
技能作者 → SkillManifest 填写元数据
    ↓
SkillHub.publish()
    ├── SHA-256 校验和计算
    ├── GPG 签名（可选）
    └── 推送到 Git 仓库
    ↓
技能消费者 → SkillHub.search() / SkillHub.install()
    ├── 拉取 Git 仓库
    ├── SHA-256 校验和验证
    ├── GPG 签名验证（如已签名）
    ├── min_clawhermes 版本检查
    └── 安装到本地 skills 目录
    ↓
SkillManager 自动发现新技能
```

### 3.6 消息渠道架构

#### 3.6.1 渠道决策流程（多级策略）

ClawHermes 的消息渠道采用**决策树模式**，按优先级选择实现方式：

```
新渠道需求
    │
    ▼

```
新渠道需求
    │
    ▼
1. 有官方为Agent 开发的 SDK？ → git submodule 引入依赖 + 适配 ChannelAdapter     ← 首选
    │ 无                         例：飞书 lark-oapi / larksuite-openclaw-lark
    ▼
2. 有社区为Agent 开发的 SDK？ → git submodule 引入依赖 + 适配 ChannelAdapter        ← 次选
    │ 无                         例：微信 wechatpy / QQ Bot（Hermes 集成）
    ▼
3. 可复刻官方Agent 开发的 SDK？ → git submodule + 复刻核心逻辑 + 适配 ChannelAdapter          ← 三选
    │ 不可                       例：Telegram Bot API（参考 Hermes bot_telegram）
    ▼
4. 有官方其他SDK  → git submodule 引入依赖 + 适配 ChannelAdapter         ← 四选
    │ 不可             例：Slack slack-bolt / Discord discord.py
    ▼
5. 裸 API 实现  → git submodule + HTTP/WS 客户端 + 适配 ChannelAdapter        ← 最后
                      极少新平台/冷门渠道
```

**渠道优先级**：飞书 > 微信 > QQ（P0 国内生态优先）→ Telegram > Discord > Slack（P1 国际生态后续）

#### 3.6.2 当前渠道状态

```
                    ┌──────────────────────────┐
                    │     Channel Router ✅     │
                    │  · SessionRouter         │
                    │  · 4 队列模式             │
                    │  · allowlist 过滤        │
                    └───────────┬──────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
  ┌─────▼─────┐          ┌─────▼─────┐          ┌─────▼─────┐
  │ CLI ✅    │          │ REST ✅   │          │ WS ✅     │
  │ (print)   │          │ (Future)  │          │ (conn reg)│
  └───────────┘          └───────────┘          └───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
  ┌─────▼─────┐          ┌─────▼─────┐          ┌─────▼─────┐
  │ 飞书 ✅   │          │ 微信 ✅   │          │ QQ 📋     │
  │clawhermes │          │clawhermes │          │clawhermes │
  │ -lark     │          │ -weixin   │          │ -qq       │
  │ lark-oapi │          │ wechatpy  │          │ QQ Bot API│
  └───────────┘          └───────────┘          └───────────┘
```

#### 3.6.3 消息渠道系统总览

**P1 国际渠道（后续规划）**：Telegram（裸 API，末选策略）| Discord（discord.py，四选策略）| Slack（slack-bolt，四选策略）

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          消息渠道系统架构                                      │
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │   飞书    │  │   微信    │  │    QQ    │  │ Telegram │  │  Discord │ ... │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Adapter  │     │
│  │(子仓库 ✅)│  │(子仓库 ✅)│  │(子仓库 📋)│  │(社区SDK 📋)│  │(社区SDK 📋)│     │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘      │
│        └──────────────┼─────────────┼─────────────┼────────────┘            │
│                       ▼             ▼             ▼                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Channel Router                                  │    │
│  │  · 消息路由：(channel_type, chat_id) → session_id                    │    │
│  │  · 消息队列：steer / followup / collect / interrupt                  │    │
│  │  · Block Streaming：完成即发送，可配置 chunk/coalesce（TODO）         │    │
│  │  · DM 配对：配对码生成 + 管理员审批（TODO）                           │    │
│  │  · 渠道健康检查：每个适配器 health() 统一监控（TODO）                  │    │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
│                             │                                               │
│  ┌──────────────────────────▼──────────────────────────────────────────┐    │
│  │                    Session Router                                     │    │
│  │  · 会话映射：(channel_type, chat_id) → Agent session_id              │    │
│  │  · 跨渠道会话：可选的跨渠道会话合并                                   │    │
│  │  · 会话重置策略：daily / idle / manual                                │    │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
│                             │                                               │
│  ┌──────────────────────────▼──────────────────────────────────────────┐    │
│  │                    Agent Core                                         │    │
│  │  Agent.chat_async() / Agent.chat() → Background Review               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Channel Config Store                               │    │
│  │  · YAML 配置文件：~/.clawhermes/channels/<name>.yaml                 │    │
│  │  · 凭证管理：API Token 通过 ${VAR} 引用 .env，与配置分离               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 3.6.4 Channel Router 核心流程

同 v0.14.1，保持不变：

```
渠道消息到达 → ChannelAdapter.receive_message()
    ↓
ChannelRouter.route(message)
    ↓
1. 安全检查：DM 配对验证 / allowlist 检查
    ↓ 不通过 → 发送配对码 / 静默丢弃
2. 会话路由：查找 (channel_type, chat_id) → session_id
    ↓ 无映射 → 创建新会话
3. 消息队列：检查 Agent 当前状态
    ├── 空闲 → 直接处理
    ├── 运行中 + steer → 注入当前轮次
    ├── 运行中 + followup → 排队等下一轮
    ├── 运行中 + collect → 等待安静窗口后合并
    └── 运行中 + interrupt → 中止当前，执行新消息
4. Agent 处理：agent.chat_async(message, session_id=session_id)
    ↓
5. 响应路由：ChannelRouter → ChannelAdapter.send_response()
    ↓
6. Block Streaming（待实现）：分块发送响应
```

#### 3.6.5 ChannelAdapter 接口

| 方法 | 类型 | 说明 | 状态 |
|------|------|------|:---:|
| `start()` | 抽象 | 启动渠道监听 | ✅ |
| `stop()` | 抽象 | 停止渠道监听 | ✅ |
| `send_response()` | 抽象 | 发送响应 | ✅ |
| `get_user_info()` | 抽象 | 获取用户信息 | ✅ |
| `health()` | 抽象 | 渠道健康检查 | 📋 Phase 3 |
| `send_typing()` | 抽象 | "正在输入"指示 | 📋 Phase 3 |
| `send_media()` | 抽象 | 媒体消息（图片/文件/语音） | 📋 Phase 3 |

#### 3.6.6 消息队列模式

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| steer | 注入当前轮次，工具完成后融合 | 默认模式 |
| followup | 排队等下一轮 | 非紧急追加 |
| collect | 安静窗口后合并 | 群聊批量 |
| interrupt | 中止当前执行新消息 | 紧急指令 |

#### 3.6.7 DM 配对安全模型（Phase 3 待实现）

```
未知用户 DM → 生成配对码（8位，1小时有效）→ 管理员审批 → 加入 allowlist
```

#### 3.6.8 渠道配置架构

```yaml
# ~/.clawhermes/channels/feishu.yaml
channel_type: feishu
enabled: true

adapter:
  domain: feishu            # feishu / lark / ...
  connection_mode: websocket
  bot_name: ""

routing:
  queue_mode: steer
  session_reset: daily

security:
  group_policy: allowlist
  allowed_group_users: []
  admins: []
  allow_bots: none
  require_mention: true

webhook:
  host: 0.0.0.0
  port: 8080
  path: /feishu/webhook

websocket:
  reconnect_nonce: 30
  reconnect_interval: 120
  ping_interval: null
  ping_timeout: null

performance:
  log_level: 20
  max_retries: 3
  retry_delay: 1.0
  dedup_cache_size: 1024

features:
  reactions_enabled: true
```## 4. 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | 生态丰富、团队熟悉 |
| LLM 统一接口 | **litellm** | 132+ 模型统一接口，省去自己封装 |
| Web 框架 | FastAPI | 原生 async、自动文档 |
| 数据库 | SQLite → PostgreSQL | 轻量起步，按需升级 |
| 向量库 | ChromaDB | 纯 Python，零配置嵌入 |
| 异步框架 | asyncio | Python 原生异步 |
| 配置管理 | Pydantic Settings | 类型安全，schema 校验 |
| 包管理 | uv | 比 pip 快 10-100 倍 |
| 测试 | pytest + pytest-asyncio | 行业标准 |
| 代码质量 | ruff + mypy | 零配置 lint + 类型检查 |
| MCP 集成方式 | **客户端模式**（✅ v0.14.0） | 作为 MCP Client 动态发现外部工具，支持 stdio + HTTP 双传输，JSON-RPC 2.0 协议，无需自建 MCP Server |
| 消息队列模式 | **steer 优先**（✅ v0.14.0） | steer/followup/collect/interrupt 四模式已实现，通过 `QueueMode` 枚举 + `CH_QUEUE_MODE` 配置切换 |
| Profile 隔离 | **目录隔离**（规划中） | 每个 Profile 独立数据目录（skills/、memory/、sessions.db），零进程开销；进程隔离方案留作 v2.0+ 选项 |
| 技能加载策略 | **Progressive Disclosure**（规划中） | 按 Profile 级别渐进暴露工具，minimal→standard→full，减少认知负荷和 token 消耗；全量加载仅用于调试场景 |
| 流式输出 | **Block Streaming**（规划中） | 按 SSE 块流式输出（工具调用块、文本块分别推送），兼顾实时性和完整性；完整响应模式作为降级方案 |
| 渠道集成方式 | **Channel Router 中间层** | 解耦 Gateway 与渠道，Gateway 不直接调用 Agent |
| 消息队列默认模式 | **steer** | 借鉴 OpenClaw，适合大多数场景 |
| 渠道配置格式 | ✅ **YAML + 环境变量引用** | 已实现：`channel/config.py` ChannelConfigLoader，${VAR} 插值，.env/频道分层 |
| 渠道依赖管理 | **可选依赖 (extras)** | telegram/discord/slack 等为可选安装，不污染核心 |
| 流式输出模式 | **编辑模式（Telegram/Discord）+ 新消息模式（Slack/飞书）** | 不同平台 API 能力不同，适配器自行选择 |
| DM 安全模型 | **pairing 模式默认** | 借鉴 OpenClaw，安全优先 |

---

## 5. 模块依赖图

```
gateway/app.py
    ├── channel/adapter.py → agent/exceptions.py
    ├── agent/loop.py
    │   ├── agent/prompt.py → agent/context.py
    │   ├── agent/ace.py → agent/context.py
    │   ├── tools/registry.py
    │   ├── tools/dispatch.py
    │   ├── tools/hooks.py
    │   ├── tools/policy.py
    │   ├── tools/builtin.py → tools/registry.py
    │   ├── tools/sandbox.py → agent/exceptions.py
    │   ├── agent/memory.py → storage/vector.py
    │   │                 → storage/chroma_memory.py
    │   ├── skills/manager.py → skills/hub.py
    │   ├── agent/delegate.py → agent/loop.py
    │   └── agent/scheduler.py
    ├── agent/session.py → agent/exceptions.py
    ├── llm/provider.py → llm/credential_pool.py
    └── storage/session.py → storage/transcript.py

    无循环依赖 ✓
```

---

## 6. v1.0 目标架构

> 以下为 v1.0 完整目标架构，与当前实现（v0.14.1）对比

### 6.1 已实现模块（v0.11.0）

| 模块 | 职责 | 状态 |
|------|------|:----:|
| `agent/exceptions.py` | 自定义异常类层次（5大类10子类 + 扩展异常） | ✅ |
| `agent/session.py` | 会话持久化管理（SQLite WAL） | ✅ |
| `tools/builtin.py` | 26个内置工具 + 3级 Profile | ✅ |
| `agent/loop.py` | Agent Loop + HookManager + ToolDispatcher | ✅ |
| `agent/prompt.py` | 三层 System Prompt | ✅ |
| `agent/context.py` | 上下文压缩引擎 | ✅ |
| `agent/memory.py` | 记忆管理器 | ✅ |
| `agent/delegate.py` | 子 Agent 委派 | ✅ |
| `skills/hub.py` | 联邦技能中心（SkillManifest + SkillHub） | ✅ |
| `llm/provider.py` | LLM Provider + CredentialPool + chat_async | ✅ |
| `gateway/app.py` | FastAPI REST 服务（12个端点） | ✅ |
| `.github/workflows/ci.yml` | CI 流水线 | ✅ |

### 6.2 已实现模块（v0.14.1）

| 模块 | 职责 | 阶段 |
|------|------|------|
| `channel/adapter.py` | Channel Adapter SDK ABC + 3个内置适配器 | Phase 2 ✅ |
| `agent/scheduler.py` | Cron 调度器（cron/interval/oneshot） | Phase 2 ✅ |
| `agent/ace.py` | 自适应上下文引擎（ACE） | Phase 2 ✅ |
| `tools/sandbox.py` | Docker 沙箱执行环境 | Phase 2 ✅ |
| `skills/hub.py` | 联邦技能中心（SkillHub） | Phase 3 ✅ |

### 6.3 新增模块（v0.14.1）

| 模块 | 职责 | 阶段 |
|------|------|------|
| `storage/chroma_memory.py` | ChromaDB 向量记忆存储（语义检索） | Phase 2 ✅ |
| `gateway/app.py` | Gateway 端点扩展至18个（+Cron 6个） | Phase 2 ✅ |
| `agent/agent_mgr.py` | 多 Agent 管理 | Phase 2 ✅ |

### 6.4 待实现模块

| 模块 | 职责 | 阶段 |
|------|------|------|
| `agent/queue.py` | 消息队列独立模块（当前内联于 loop.py / types.py） | Phase 4 |
| `agent/profile.py` | Profile 隔离（多 Profile 并发运行） | Phase 3 |
| `agent/security.py` | 设备安全（DM 配对 + 签名挑战） | Phase 3 |
| `channel/config.py` | 渠道配置管理 + 热加载 | ✅ Phase 3 (v0.14.1) |
| `channel/streaming.py` | Block Streaming | Phase 3 |
| `channel/adapters/telegram.py` | Telegram 适配器 | 📋 Phase 3 续 |
| `channel/adapters/discord.py` | Discord 适配器 | 📋 Phase 3 续 |
| `channel/adapters/slack.py` | Slack 适配器 | 📋 Phase 3 续 |
| `channel/adapters/feishu.py` | 飞书适配器（已迁移至子仓库 `clawhermes-lark`） | ✅ Phase 3 (v0.14.1) |
| `channel/adapters/webchat.py` | WebChat 适配器 | 📋 Phase 3 续 |
| `skills/evolution.py` | 技能进化图谱 | Phase 3 |
| `memory/multimodal.py` | 多模态记忆 | Phase 3 |
| `agent/user_model.py` | 用户画像持久化 | Phase 3 |
| `dashboard/` | 可观测性仪表盘 | Phase 4 |
| `workflow/` | 工作流构建器 | Phase 4 |
| `playground/` | 提示词实验场 | Phase 4 |
| `acp/` | IDE 集成（Agent Communication Protocol） | Phase 4 |

---

## 7. 异常类层次

```
ClawHermesError (base)
├── LLMError
│   ├── LLMConnectionError          # LLM 连接失败
│   ├── LLMRateLimitError           # LLM 速率限制（含 retry_after）
│   └── LLMResponseError            # LLM 响应解析失败
├── ToolError
│   ├── ToolNotFoundError           # 工具未找到
│   ├── ToolExecutionError          # 工具执行失败（含 tool_name）
│   └── ToolBlockedError            # 工具被钩子/策略阻止（含 tool_name + reason）
├── MemoryError
│   ├── MemoryStorageError          # 记忆存储失败（含 provider）
│   └── MemorySearchError           # 记忆搜索失败（含 provider）
├── ConfigError
│   ├── ConfigValidationError       # 配置校验失败（含 field）
│   └── ConfigNotFoundError         # 配置文件未找到
├── SessionError
│   ├── SessionNotFoundError        # 会话未找到（含 session_id）
│   └── SessionExpiredError         # 会话已过期（含 session_id）
├── ChannelError                    # 渠道相关异常
│   ├── ChannelConnectionError      # 渠道连接失败
│   └── ChannelMessageError         # 渠道消息处理失败
└── SandboxError                    # 沙箱相关异常
    ├── SandboxNotAvailableError    # Docker 沙箱不可用
    └── SandboxTimeoutError         # 沙箱执行超时
```

**设计原则**：
- 所有异常继承 `ClawHermesError`，支持 `detail` 关键字参数
- 关键子类携带上下文字段（`tool_name`、`provider`、`session_id`、`retry_after` 等）
- 扩展异常（Channel、Sandbox）按领域独立，不破坏原有5大类结构

---

## 8. 工具 Profile 架构

```
ToolProfile
├── minimal (5 tools) — 轻量场景
│   └── session_status, read_file, write_file, exec, get_time
│
├── standard (9 tools) — 默认
│   └── minimal + web_search, memory_search, memory_save, delegate_task
│
└── full (35 tools) — 完整能力
    └── standard + web_fetch, list_dir, patch_file, grep, search_replace,
                   code_eval, compress_file, http_request, json_query,
                   git_status, git_diff, git_log, env_list, timer,
                   url_encode, url_decode, calc
```

**Profile 选择策略**：

| Profile | 工具数 | 适用场景 | Token 开销 |
|---------|:------:|----------|-----------|
| minimal | 5 | 嵌入式/受限环境 | 最低 |
| standard | 9 | 日常对话（默认） | 中等 |
| full | 35 | 开发/运维/高级 | 最高 |

**工具并行安全标记**：

| 可并行 ✅ | 不可并行 ❌ |
|-----------|------------|
| get_time, read_file, session_status, web_search, memory_search, web_fetch, list_dir, grep, compress_file, git_status | write_file, exec, memory_save, delegate_task, patch_file, search_replace, code_eval, http_request, json_query, git_diff, git_log, env_list, timer, url_encode, url_decode, calc |

---

## 附录 A：Gateway 端点清单（33 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/init` | 初始化 Agent |
| POST | `/chat` | 对话 |
| GET | `/health` | 健康检查 |
| GET | `/tools` | 列出工具 |
| POST | `/memory/save` | 保存记忆 |
| GET | `/memory/search` | 搜索记忆 |
| GET | `/skills` | 列出技能 |
| POST | `/skills/create` | 创建技能 |
| POST | `/curator/run` | 运行 Curator |
| GET | `/sessions` | 列出会话 |
| GET | `/sessions/{id}` | 获取会话 |
| DELETE | `/sessions/{id}` | 删除会话 |
| POST | `/cron/jobs` | 创建调度任务 |
| GET | `/cron/jobs` | 列出调度任务 |
| GET | `/cron/jobs/{id}` | 获取调度任务 |
| DELETE | `/cron/jobs/{id}` | 删除调度任务 |
| POST | `/cron/jobs/{id}/pause` | 暂停调度任务 |
| POST | `/cron/jobs/{id}/resume` | 恢复调度任务 |
| GET | `/channels` | 渠道列表 |
| GET | `/channels/sessions` | 渠道会话 |
| POST | `/mcp/servers` | 注册 MCP Server |
| GET | `/mcp/servers` | 列出 MCP Server |
| DELETE | `/mcp/servers/{name}` | 删除 MCP Server |
| POST | `/chat/stream` | SSE 流式对话 |
| POST | `/dm/pair/generate` | 生成配对码（需 ADMIN_KEY） |
| POST | `/dm/pair/verify` | 验证配对挑战 |
| GET | `/dm/pair/status` | 查询配对状态 |
| GET | `/dm/pair/list` | 列出已配对用户 |
| DELETE | `/dm/pair/{user_id}` | 撤销配对 |
| POST | `/feishu/webhook` | 飞书事件回调（需启用 clawhermes-lark） |
| POST | `/wechat/webhook` | 微信消息回调（需启用 clawhermes-weixin） |
| POST | `/wecom/webhook` | 企业微信消息回调（需启用 clawhermes-weixin） |
| POST | `/qq/webhook` | QQ 消息回调（需启用 clawhermes-qq） |

---

## 附录 B：CredentialPool 策略说明

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `fill_first` | 优先使用第一个可用 Key | 单 Key 或主备模式 |
| `round_robin` | 轮询分配（默认） | 多 Key 均衡负载 |
| `random` | 随机选择 | 简单分散请求 |
| `least_used` | 选择使用次数最少的 Key | 精确均衡 |

**冷却机制**：Key 被 mark_failed 后按状态码进入冷却期（401→300s，429→3600s，其他→600s），冷却期内该 Key 不可用。

---

## 附录 C：ACE 自适应压缩策略

| 对话类型 | 保留代码块 | 保留引用 | 保留风格 | 最大摘要 Token | 摘要焦点 |
|----------|:----------:|:--------:|:--------:|:--------------:|----------|
| CODE | ✅ | ❌ | ❌ | 6000 | 代码和技术决策 |
| QA | ❌ | ✅ | ❌ | 4000 | 事实、引用和结论 |
| CREATIVE | ❌ | ❌ | ✅ | 5000 | 风格和叙事线索 |
| MIXED | ✅ | ✅ | ❌ | 5000 | 综合摘要 |

**块保护模式**：每种策略定义 `block_protect_patterns`（正则列表），匹配的内容块在压缩时不会被截断。
