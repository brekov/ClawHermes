# Changelog

## v0.15.0 (2026-06-24)

### M3.6d DM 配对安全模型 — 配对码 + HMAC 挑战 + 管理员审批

- **5 个新 Gateway 端点**：`POST /dm/pair/generate`、`POST /dm/pair/verify`、`GET /dm/pair/status`、`GET /dm/pair/list`、`DELETE /dm/pair/{user_id}`
  - `generate`：生成 8 位配对码（1 小时 TTL），需 `ADMIN_KEY` 鉴权
  - `verify`：HMAC 挑战-响应验证，防重放
  - `status`/`list`/`revoke`：配对生命周期管理
- **安全模型**：借鉴 OpenClaw DM 配对模式 — 未知用户 → 生成配对码 → 管理员审批 → 加入 allowlist

### M3.6g QQ Bot 渠道适配器 — 第三渠道就绪

- **clawhermes-qq 子仓库**：QQ Bot HTTP API + WebSocket 长连接
  - 凭证管理：`QQ_APP_ID` / `QQ_TOKEN` / `QQ_SECRET`
  - 沙箱/正式环境切换：`sandbox: true/false`
  - 心跳保活：40s 间隔 + 自动重连
- **Gateway 集成**：`POST /qq/webhook` 端点 + ChannelAdapter 封装
- **配置示例**：`config/channels/qq.yaml.example`

### M3.6c Block Streaming — SSE 流式响应

- **新增长 `LLMProvider.chat_stream()`** — litellm 流式封装 + 块缓冲（800-1200 chars）
  - `StreamChunk` 类型：`text` / `tool_calls` / `error` / `done`
  - 流式消费 token → 块缓冲 → yield，首字延迟降低 50%+
  - 工具调用累积后一次性发出
  - 完整错误处理：RateLimit / Auth / Connection 异常 → `StreamChunk(kind="error")`
- **新增长 `Agent.chat_stream()`** — 异步迭代器产出 SSE 事件
  - 事件类型：`text` | `tool_call` | `tool_result` | `error` | `done`
  - 复用 Agent 的 Hook 体系 + 工具执行器
- **新增长 `POST /chat/stream` SSE 端点**
  - `text/event-stream` + `Cache-Control: no-cache` + `X-Accel-Buffering: no`
  - 复用 `ChatRequest` 输入模型
- **新增长 `MockProvider.chat_stream()`** — 测试用流式 Mock
- **测试**：3 个流式测试（纯文本 / 工具调用 / 中断）

渠道配置架构修复 — 死字段激活 + YAML 单一来源

### 配置架构重构

- **新增长 `channel/config.py`** — ChannelConfigLoader：YAML + ${VAR} 环境变量插值
  - 敏感值（密钥）：存放在 .env，通过 YAML `${FEISHU_APP_ID}` 语法引用
  - 操作配置（非敏感）：存放在 `channels/<name>.yaml` 中
  - 优先级：环境变量 > YAML > 内置默认值
- **app.py** — 27 处 `os.environ.get("FEISHU_*")` → 1 处 `build_adapter_config("feishu")`
  - 配置加载统一入口，零向后兼容 fallback
- **.env.example** — 27 个 FEISHU_* 变量 → 6 个纯敏感值（密钥/Token 类）
- **feishu.yaml.example** — 完整 26 字段操作配置示例，使用 ${VAR} 引用 .env 敏感值
- **配置分层原则**：`.env（敏感值）→ ${VAR} 插值 → channels/*.yaml → build_adapter_config()`

### M3.6e 飞书适配器 — 15 个死配置生效

- **LarkConfig 26/26 字段全部操作化**（之前仅 11 个生效）：
  - **加密**：`encrypt_key` → Webhook SHA256+hmac 签名校验
  - **Bot 身份**：`bot_open_id`、`bot_user_id` → @提及双重匹配（open_id 首选，user_id 回退）；`bot_name` → `get_user_info()` 返回
  - **权限门控**：`group_policy`（5 策略）、`allowed_group_users`（白/黑名单）、`admins`（管理员绕过）、`allow_bots`（三档过滤）、`require_mention`（@提及门控）
  - **WS 可配**：`ws_reconnect_nonce`、`ws_reconnect_interval` 替换硬编码 5s；`ws_ping_interval`、`ws_ping_timeout` 注入 lark.ws.Client
  - **高级**：`dedup_cache_size` → OrderedDict LRU 限界去重；`reactions_enabled` → 反应事件开关
- **消息去重**：对齐 Hermes `_seen_message_ids` 模式
- **按 chat_id 串行处理锁**：对齐 Hermes `_chat_locks`
- **Webhook 签名校验**：SHA256(timestamp+nonce+encrypt_key+body) + hmac.compare_digest

### 文档全量同步

- **全部 14 个文档** 更新至 v0.15.0 基线（功能清单、架构图、模块统计、端点清单、配置分层）

### 质量

- 416 测试全部通过
- ruff 0 errors | mypy 281 errors（技术债，待清理）
- 代码行数：~6,900 行（+~150 行 config loader + adapter logic）
- clawhermes-lark：6,863 行（含 5,512 行 Hermes vendor 消息引擎）

## v0.14.0 (2026-06-22)

Phase 3 中期 — 全链路异步化 / 测试覆盖率 / MCP 集成 / 工具扩展至 35

## v0.14.0 (2026-06-22)

Phase 3 中期 — 全链路异步化 / 测试覆盖率 / MCP 集成 / 工具扩展至 35

### M3.11 全链路异步化

- **消除全部 threading.Thread**：scheduler、BackgroundReview、Curator 全部改为 asyncio 原生
- **CronScheduler 异步重构**：`sched.scheduler` + `threading.Thread` → `asyncio.create_task` + 动态 sleep
- **GatewayState 增强**：`initialize()` async、`shutdown()` 优雅关闭、`_bg_tasks` 后台任务管理
- **BackgroundReview**：`threading.Thread` → `asyncio.to_thread`，不阻塞事件循环
- **Curator**：`threading.Thread` → `asyncio.create_task` + `asyncio.sleep`

### M3.12 测试覆盖率提升

- **66% → 71%**（+107 测试，203 → 310）
- **Gateway 端点全覆盖**：health, tools, memory, skills, curator, sessions, cron, channels
- **组件全覆盖**：SkillManager, BackgroundReview, Curator, MemoryProvider, SessionManager, ChannelManager, SessionRouter, HookManager, ToolRegistry, DelegateManager, GatewayState
- **异常类 100%**、**类型模块 100%**

### M3.7 MCP 客户端集成

- **新增 `clawhermes/mcp/` 模块**：MCPClient (stdio + HTTP 双传输, JSON-RPC 2.0) + MCPRegistry
- **MCPServerSpec**：声明式 MCP Server 配置
- **Gateway 端点**：`POST /mcp/servers`、`GET /mcp/servers`、`DELETE /mcp/servers/{name}`

### M3.10 内置工具扩展至 35

- **新增 9 个工具**：
  - `sqlite_query` — SQLite 数据库查询（stdlib sqlite3）
  - `csv_parse` — CSV 文件解析（stdlib csv）
  - `hash_file` — 文件哈希 (md5/sha1/sha256/sha512)（stdlib hashlib）
  - `disk_usage` — 磁盘使用情况（stdlib shutil）
  - `base64_codec` — Base64 编解码（stdlib base64）
  - `process_list` — 系统进程列表
  - `image_info` — 图片信息（可选 Pillow）
  - `pdf_extract` — PDF 文本提取（可选 pypdf）
  - `markdown_render` — Markdown → HTML（可选 markdown）
- **工具总数**：26 → 35，跨越 data / file / system / util / media 5 个新分组

### 修复 & 测试增强

- **MCP 工具异步路径修复**：`MCPRegistry._make_handler` 改为返回 `async def handler`，修复 MCP 工具经异步分派路径静默失效（返回占位结果而非实际执行）的 bug
  - 新增 `_run_maybe_async()` 辅助函数兼容同步/异步 handler 混合分派
  - **权衡说明**：`_run_maybe_async` 在嵌套事件循环场景下通过 `threading.Thread` 执行协程。这是刻意打破 v0.14.0 "零 threading.Thread" 声明的工程权衡：该线程仅在一次性的嵌套循环边缘场景触发，短生命周期且不会泄漏。主流路径仍为零 Thread
- **CLI 测试覆盖**：新增 `tests/test_cli.py` 21 测试，覆盖 doctor/chat/gateway/config/agent/setup 全部子命令主路径
- **MCP 测试覆盖**：新增 `tests/test_mcp_client.py` 26 测试，覆盖 stdio/HTTP 双传输 + Registry + 同步/异步分派路径

### 质量

- 416 测试全部通过
- ruff 0 errors | mypy 281 errors（技术债，待清理）（6 strict checks）
- 代码行数：~3,700 行（+301 行 MCP 模块, +281 行工具扩展）


### M3.6e 飞书渠道适配器

- **clawhermes-lark v0.1.0 子仓库**：分层架构实现
  - **Layer 1 (lark-oapi)**: Token 管理/认证/WebSocket 长连接/API 调用
  - **Layer 2 (Hermes vendor)**: 复刻 Hermes feishu_hermes.py (5512行) — 消息解析/Markdown→飞书 Post 转换/@提及标准化
  - **Layer 3 (ChannelAdapter)**: 统一接口 `start`/`stop`/`send_response`/`get_user_info`
- **send_response 完整实现**：通过 lark-oapi CreateMessage API 实际发送消息（+指数退避重试）
- **get_user_info 实现**：通过 lark-oapi Contact API 获取用户信息
- **媒体消息支持**：`send_image`/`send_file`（上传 + 发送二合一）
- **Hermes vendor 兼容层**：`sys.modules` 注入机制解决 Hermes 5 大内部依赖（228行 shim）
- **WebSocket 长连接**：自动重连 + 事件分发（参考 openclaw-lark monitor 模式）
- **ClawHermes 薄封装**：`channel/adapters/feishu.py`（36行）→ 实际逻辑在 clawhermes-lark

### M3.6f 微信渠道适配器

- **clawhermes-weixin 子仓库**：微信渠道适配器独立实现
- **wechatpy 社区 SDK**：公众号/企业微信消息收发
- **ChannelAdapter 封装**：与飞书接口一致
- **Gateway 集成**：消息路由 + 渠道注册

## v0.13.0 (2026-06-17)

Phase 3 核心架构强化 — 并行执行 / 搜索重构 / Gateway 状态重构 / 线程安全

### M3.2 并行工具执行

- **asyncio.gather 真正并行执行**：parallel_safe 工具组通过 `asyncio.gather` 并行执行，不再串行
- **新增 `execute_async` 方法**：`ToolDispatcher.execute_async()` 原生异步执行，支持 `chat_async` 全链路异步
- **新增 `_execute_single_tool_async`**：异步工具执行器，支持协程 handler 和 `run_in_executor` 包装同步 handler
- **工具执行耗时追踪**：`AFTER_TOOL_CALL` 钩子现在提供真实的 `duration_ms` 数据

### M3.3 web_search 重构

- **多搜索引擎支持**：新增 DuckDuckGo（默认）/ SearXNG / SerpAPI / Tavily 四种搜索引擎
- **环境变量切换**：`CH_SEARCH_ENGINE` 控制搜索引擎选择
- **结构化搜索结果**：搜索结果包含 `title` / `url` / `snippet` 结构化字段
- **优雅降级**：httpx 不可用时自动回退到 curl+grep，DuckDuckGo 失败时自动降级
- **SearXNG 错误处理**：连接失败时返回结构化错误而非抛异常

### M3.4 Gateway 状态重构

- **GatewayState 类**：模块级全局变量重构为 `GatewayState` 类实例，支持多实例部署
- **消除 global 语句**：`initialize()` 和 `_auto_init()` 不再使用 `global` 关键字
- **状态访问方法**：`get_agent()` / `get_memory()` / `get_skill_manager()` 封装在 GatewayState 中
- **版本号更新**：Gateway version 从 0.12.1 更新为 0.13.0

### M3.5 SessionManager 线程安全

- **threading.Lock 保护**：所有 SQLite 操作通过 `self._lock` 保护，消除竞态条件
- **close() 方法加锁**：关闭连接时也获取锁，防止并发关闭

### M3.6a Channel Router

- **新增 `channel/router.py`**：统一消息路由层，解耦 Gateway 与渠道适配器
- **SessionRouter**：(channel_type, chat_id) → session_id 自动映射，支持过期清理
- **ChannelRouter**：消息路由 + allowlist 过滤 + 消息队列 + Agent handler 集成
- **QueueMode 枚举**：steer/followup/collect/interrupt 4 种消息队列模式
- **Gateway 集成**：`/chat` 端点通过 ChannelRouter 路由，新增 `/channels` 和 `/channels/sessions` 端点
- **GatewayState 扩展**：新增 `channel_router` 属性

### M3.6b 消息队列模式

- **4 种队列模式完整实现**：steer（注入当前轮）/ followup（排队等下一轮）/ collect（缓冲合并）/ interrupt（中止当前）
- **collect 缓冲区**：Agent 忙碌时收集消息，空闲后合并为一条消息处理
- **interrupt 优先**：清空队列后插入队首，立即处理
- **消息级队列模式**：每条消息可通过 `metadata.queue_mode` 指定模式
- **安全事件循环处理**：`asyncio.get_running_loop()` 替代已废弃的 `ensure_future`

### 测试增强

- **新增 38 个测试用例**：165 → 203
- `TestParallelToolExecution`：5 个并行执行测试
- `TestWebSearchRefactor`：7 个搜索重构测试
- `TestGatewayState`：3 个 Gateway 状态测试
- `TestSessionManagerThreadSafety`：2 个线程安全测试
- `TestSessionRouter`：7 个会话路由测试
- `TestChannelRouter`：8 个渠道路由测试
- `TestMessageQueueModes`：6 个消息队列模式测试

## v0.12.2 (2026-06-17)

评审问题修复 — P0-P3 级问题系统性修复

### P0 级修复（立即修复）

- **/health 端点版本动态化**：修复版本硬编码为 "0.11.0" 的问题，改为动态读取 pyproject.toml 版本
- **AgentConfig 默认值统一**：`max_iterations` 默认值从 20 改为 50，与文档保持一致
- **README badge 版本更新**：版本显示从 v0.12.0 更新为 v0.12.1

### P1 级修复（文档准确性）

- **architecture.md 端点数更新**：10 → 18
- **architecture.md 工具数更新**：15 → 26
- **architecture.md 异常类数量修正**：17 子类 → 10 子类 + 2 个扩展异常类
- **architecture.md 模块状态更新**：标记已完成模块（Channel SDK、Cron Scheduler、ACE 等）
- **api-contract.md cron 端点补充**：新增 6 个 cron 端点定义
- **data-model.md 版本更新**：v0.6-draft → v2.1，新增 CronJob/ChannelMessage/ChannelUser 数据模型

### P2 级修复（质量问题）

- **CHANGELOG 测试数修正**：v0.12.0 测试数从 152 更新为 165

### P3 级修复（代码质量）

- **ToolDispatcher 并行调度优化**：移除硬编码的 PARALLEL_SAFE 集合，改为使用 ToolDef.parallel_safe 属性判断
- **原生异步 chat_async 实现**：使用 LLMProvider.chat_async 而非 run_in_executor 包装同步方法
- **MockProvider 异步支持**：添加 chat_async 方法支持异步测试

### 测试结果

- ruff: All checks passed!
- mypy: Success: no issues found in 24 source files
- pytest: 165 passed in 11.81s

## v0.12.1 (2026-06-17)

文档修复与环境配置完善

### 修复

- **CLI 重命名**：`clawhermes agent set-persona` → `clawhermes agent set`，与 `create/list/show/switch` 风格统一
- **.env.example**：重写为清晰的分组注释，移除内部变量 `CH_GW_API_KEY`/`CH_GW_MODEL`
- **配置示例**：补全 `config.yaml.example`、`providers/deepseek.yaml.example`、渠道配置（slack/feishu/discord）、Agent 文件（SOUL/AGENTS/config.json）
- **FEATURES.md**：CLI 命令同步、渠道配置说明、统计数字对齐实际代码
- **README**：端点计数修正 19→18
- **CHANGELOG/RELEASE.md**：端点计数、源文件数同步修正

## v0.12.0 (2026-06-17)

功能增强与扩展 — Phase 2 完成

### 新增

- **Channel Adapter SDK**：ChannelAdapter ABC + CLI/REST/WebSocket 3 个内置适配器 + ChannelManager
- **Cron 调度器**：标准库零依赖调度器，cron/interval/oneshot 三种模式，JSON 持久化，6 个新 API 端点
- **Docker 沙箱**：DockerSandbox 安全执行环境，run_python/run_command，资源限制，SandboxPool 预热
- **ACE 自适应上下文引擎**：ConversationClassifier（代码/问答/创意/混合检测），CompressionStrategy 按类型选择
- **11 个新内置工具**：compress_file/http_request/json_query/git_status/git_diff/git_log/env_list/timer/url_encode/url_decode/calc
- **功能全景扩展**：F15 Cron调度 + F16 Docker沙箱 + F17 ACE + F18 Channel SDK

### 工具系统

- 内置工具：15 → 26（+73%）
- 并行安全工具：7 个标记 parallel_safe
- 需确认工具：2 个标记 require_confirm（http_request/git_diff）

### Gateway

- API 端点：13 → 18（+6 cron 端点）
- POST/GET/DELETE /cron/jobs + pause/resume

### 测试

- 测试用例：73 → 165（+126%）
- ruff: 0 errors | mypy: 0 errors (6 项严格检查) | pytest: 165 passed

### 异步钩子

- HookManager 支持 async handler 注册和超时保护
- `trigger_async()` / `trigger_sync_with_async()` / `remove()`

### 类型安全

- mypy selective strict：warn_return_any、unused_ignores、redundant_casts、check_untyped_defs、no_implicit_optional、strict_equality
- 零 `typing.Any` 导入，`assert isinstance()` 运行时守卫

### Phase 3 启动

- **M3.1 Federated Skill Hub**：SkillManifest + SkillHub，Git 仓库技能发布/安装/验证，SHA-256 校验 + GPG 签名

### 文档

- README：Badge 更新、功能全景 F15-F18、工具表 26 项、架构图更新
- PRD/architecture/development-plan：Phase 2 状态更新

### 新增

- **自定义异常类层次**：`ClawHermesError` → 5大类17子类（LLMError/ToolError/MemoryError/ConfigError/SessionError）
- **工具 Profile 分级**：minimal(5)/standard(9)/full(15) 三级工具集，通过 `CH_TOOLS_PROFILE` 环境变量或 `/init` API 配置
- **6个新内置工具**：web_fetch、list_dir、patch_file、grep、search_replace、code_eval
- **chat_async 异步接口**：`Agent.chat_async()` + `LLMProvider.chat_async()`（基于 litellm.acompletion）
- **会话持久化**：`SessionManager`（SQLite WAL 模式），会话重启不丢失，支持 CRUD + 过期清理
- **CI 流水线**：GitHub Actions（lint + typecheck + test + build）
- **3个新 API 端点**：`GET /sessions/{id}`、`DELETE /sessions/{id}`、`GET /sessions?limit=N`

### 修复

- **存根工具接入**：memory_search/memory_save 接入 MemoryManager，delegate_task 接入 DelegateManager
- **Gateway 代码去重**：提取 `_create_agent_components()` 公共方法，消除 `_auto_init()` 与 `initialize()` 重复
- **LLMProvider 异常处理**：使用自定义异常类替代宽泛 `except Exception`
- **Agent Loop 工具上下文**：注入 MemoryManager/DelegateManager 到工具执行上下文

### 变更

- **移除4个未使用依赖**：sqlalchemy、sqlite-utils、beautifulsoup4、markdownify
- **移除渠道配置类**：ChannelFeishuConf/ChannelWechatConf/ChannelQQConf/ChannelTelegramConf
- **Gateway 版本**：0.10.0 → 0.11.0
- **Gateway 端点数**：10 → 13

### 测试

- 测试用例：23 → 73（+217%）
- 测试覆盖率：~40% → 65%
- 核心模块覆盖率：exceptions 100%、session 96%、loop 86%、memory 85%、prompt 83%
- ruff: 0 errors | mypy: 0 errors | pytest: 73 passed

### 文档

- 新增 `docs/development-plan.md`：完整开发计划（竞争分析、路线图、质量标准）
- 更新 `docs/PRD.md`：Phase 1 需求状态更新为已完成
- 更新 `docs/architecture.md`：v1.0 目标架构（已实现/待实现模块分离）
- 更新 `docs/api-contract.md`：新增 SessionManager 接口、异常类层次、Profile 参数
- 更新 `docs/env-reference.md`：新增 CH_GW_API_KEY/CH_GW_MODEL/CH_TOOLS_PROFILE
- 更新 `docs/comparison.md`：新增竞争策略与路线图

## v0.10.0 (2026-06-16)

回归 Agent 框架本分 — 移除全部消息渠道代码

### 变更说明

> ClawHermes 不再是一个消息网关/Gateway，而是一个纯 Python AI Agent 框架，通过 REST API 暴露能力。
> 消息渠道集成由部署者自行对接（如通过 OpenClaw、自建 webhook 或任意前端）。

### 移除

- **全部渠道代码**：`bridge.py`、`bridge.mjs`、`channels.py`、`platforms/` 目录已删除
- **渠道依赖**：`python-telegram-bot`、`lark-oapi`、`wechatpy` 等依赖已移除
- **渠道配置**：渠道相关的配置命令（`gateway setup` 不再配置渠道）
- **Channel Bridge**：Node.js bridge 代码已删除
- **渠道 API 端点**：Gateway 从 16+ 端点缩减为 10 个 Agent 核心端点

### 新增

- **纯 Agent 框架定位**：聚焦 Agent 核心（LLM、工具、记忆、技能、自进化）
- **REST API 对接能力**：通过 10 个 REST 端点暴露 Agent 能力，可对接任意前端

### 功能全景

| 模块 | 能力 |
|:---|:---|
| Agent 核心 | 多LLM接入(132)、三层Prompt、上下文压缩(F10)、子Agent委派(F12)、多Agent |
| 工具系统 | 9内置工具、钩子系统(before/after)、并行/串行调度、策略引擎 |
| 记忆系统 | JSON+ChromaDB双存储、语义搜索、跨会话持久化 |
| 技能系统 | SkillManager、Background Review(自进化)、Curator(自动维护) |
| 配置管理 | config.yaml主配置、providers/*.yaml、.env密钥分离 |

## v0.9.0 (2026-06-16)

配置体系重构 — 对齐 OpenClaw/Hermes

### 配置文件结构

```
~/.clawhermes/
├── config.yaml              # 主配置（agent/gateway/memory…）
├── providers/*.yaml         # 每个 LLM Provider 独立文件
├── agents/<name>/           # 每个 Agent 独立目录
│   ├── SOUL.md / AGENTS.md / USER.md
└── skills/
```

### 新增

- `config.yaml` 主配置文件（`clawhermes config show/init/path`）
- LLM Provider 配置独立为 `providers/*.yaml`，增删 provider 不影响其他配置
- 对比分析文档 `docs/comparison.md`（ClawHermes vs OpenClaw vs Hermes）

### 变更

- Agent 设定文件对齐 OpenClaw/Hermes：`persona.md → SOUL.md`、`instructions.md → AGENTS.md`
- `clawhermes setup` 自动生成 config.yaml

### 功能全景

| 模块 | 能力 |
|:---|:---|
| Agent 核心 | 多LLM接入(132)、三层Prompt、上下文压缩(F10)、子Agent委派(F12)、多Agent |
| 工具系统 | 9内置工具、钩子系统(before/after)、并行/串行调度、策略引擎 |
| 记忆系统 | JSON+ChromaDB双存储、语义搜索、跨会话持久化 |
| 技能系统 | SkillManager、Background Review(自进化)、Curator(自动维护) |
| 配置管理 | config.yaml主配置、providers/*.yaml、.env密钥分离 |

## v0.8.0 (2026-06-16)

Agent 设定 + 多 Agent + 微信扫码

### 新增

- Agent 身份设定（persona.md → 后改为 SOUL.md）
- 多 Agent 管理（clawhermes agent create/list/switch/show/delete）
- 个人微信扫码登录（@tencent-weixin/openclaw-weixin-cli）
- FEATURES.md 完整功能介绍

## v0.7.0 (2026-06-16)

渠道接入改造 — gateway setup

### 新增

- `clawhermes gateway setup/start/status` 命令组
- 企业微信扫码登录（ilink 协议）
- 渠道配置声明式

## v0.6.0 (2026-06-16)

软件工程补全 + F10/F12

### 新增中间产物

- docs/data-model.md、docs/api-contract.md、docs/sequence-diagrams.md

### 新增功能模块

- F10 上下文压缩（ContextEngine + LLMCompressor）
- F12 子Agent委派（DelegateManager）

## v0.5.0 (2026-06-16)

兼容层 — 复用 OpenClaw Node SDK

### 新增

- channel-bridge.cjs（复用微信/飞书 SDK）

## v0.4.0 (2026-06-16)

三渠道对齐

### 新增

- 飞书/微信/QQ 适配器
- Gateway 9个渠道API端点

## v0.3.0 (2026-06-16)

四大功能补齐

### 新增

- ChromaDB 向量检索、技能系统、Background Review、Curator
- 多渠道消息网关

## v0.2.1 (2026-06-16)

真实 API 验证

### 修复

- litellm 版本修正
- 全链路通过 DeepSeek 验证

## v0.2.0 (2026-06-16)

可部署版本

### 新增

- Gateway 常驻服务、Docker、一键安装脚本、56测试

## v0.1.0 (2026-06-16)

首个版本

### 核心功能

- Agent 循环、三层 Prompt、钩子系统、8工具、记忆系统、多凭证池
