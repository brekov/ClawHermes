# ClawHermes · 产品需求文档

> 版本：v3.0
> 日期：2026-06-17
> 状态：Phase 1 ✅ | Phase 2 ✅ | Phase 3 ✅ (v0.15.0) | v0.16.0 📋

> **v0.10.0 重要决策**：ClawHermes 移除旧消息渠道代码（飞书、微信、QQ、Telegram），集中精力重构 Agent 核心能力。
> ClawHermes 提供 **Channel Adapter SDK** 抽象层 + 标准化适配器接口，消息渠道由部署者按需集成，项目不内嵌任何平台特定代码。
> 渠道适配器通过 git 子仓库形式独立维护（如 `clawhermes-lark`），遵循**多级实现策略**（官方 Agent SDK → 社区 Agent SDK → 复刻 → 官方其他 SDK → 裸 API）。

---

## 1. 产品定位

**ClawHermes** 是一个 Python 原生的 AI Agent 框架，融合 Hermes 的自进化能力与 OpenClaw 的工程质量，在 Python 生态中打造最易嵌入的 Agent 框架。

### 1.1 差异化定位

| 维度 | Hermes | OpenClaw | ClawHermes |
|------|--------|----------|------------|
| 语言 | Python | TypeScript | **Python** |
| 定位 | 研究探索型 Agent | 消息网关 + Agent | **生产可用型 Agent 框架** |
| 核心优势 | 自进化、MCP、多 Profile | Gateway 中心化、插件钩子、Dashboard | **自进化 + 工程质量 + Python 原生** |
| 适合场景 | 个人研究、IDE 集成 | 团队消息路由 | **REST API 嵌入、团队协作、IDE 集成** |
| 安装方式 | 源码 clone | npm + 编译链 | **pip install** |

**核心差异**：
- **vs Hermes**：ClawHermes 更注重工程质量和生产可用性。Hermes 是研究探索型项目（3900 行主循环、60+ 构造参数），ClawHermes 通过模块化架构（单文件 < 500 行）、Pydantic Settings 类型化配置、异步架构解决这些工程短板，同时保留其自进化、MCP、多 Profile 等核心能力。
- **vs OpenClaw**：ClawHermes 是 Python 原生 Agent 框架，而非 TypeScript 消息网关。OpenClaw 的核心是 Gateway 路由和消息队列，ClawHermes 的核心是 Agent 智能和自进化，同时借鉴其插件钩子、工具策略、Dashboard 等工程实践。

### 1.2 核心价值主张

> "一个开箱即用、越用越聪明、通过 REST API 可嵌入任何系统的 Python AI Agent 框架"

三大支柱：
1. **越用越聪明** — 自进化机制（Background Review + Curator + Skill Evolution）
2. **工程可靠** — 类型化配置、异步架构、fail-fast 校验、可观测性
3. **即插即用** — pip install、REST API、Channel Adapter SDK、Docker 一键部署

### 1.3 目标用户

| 用户画像 | 核心需求 | ClawHermes 提供的价值 |
|---------|---------|---------------------|
| 想拥有个人 AI 助理的开发者 | REST API 嵌入自己的应用 | 开箱即用的 REST API + 持久化记忆 + 自进化 |
| 需要团队级 AI 助手的团队 | 多 Agent + 权限控制 | 工具策略引擎 + Profile 隔离 + Channel Adapter |
| Agent 框架研究者 | 可插拔引擎 + 可观测性 | ACE 可插拔 + Hook 体系 + 钩子暴露 |
| Python 生态开发者 | 纯 Python、零编译、pip 安装 | 零编译链、pip install、类型化配置 |

---

## 2. 功能需求

### 2.1 核心能力

| # | 功能 | 优先级 | 来源 | 状态 |
|---|------|--------|------|:----:|
| F1 | 多 LLM 提供商接入（OpenAI/DeepSeek/Anthropic/本地） | P0 | OpenClaw | ✅ |
| F2 | 对话主循环（思考-行动） | P0 | 两者共有 | ✅ |
| F3 | 工具系统（注册/调度/执行） | P0 | 两者共有 | ✅ |
| F4 | 持久化记忆（跨会话） | P0 | Hermes | ✅ |
| F5 | 消息渠道系统 | P0 | OpenClaw + Hermes 融合设计 | ✅ v0.15.0（飞书/微信/QQ 全部就绪） |
| F6 | 技能系统（Skills） | P1 | Hermes | ✅ |
| F7 | 自进化机制（Background Review） | P1 | Hermes | ✅ |
| F8 | 工具钩子系统（before/after tool call） | P1 | OpenClaw | ✅ |
| F9 | 工具策略引擎（profile + allow/deny） | P1 | OpenClaw | ✅ |
| F10 | 上下文压缩 | P2 | 两者共有 | ✅ |
| F11 | 多凭证池与故障转移 | P2 | Hermes | ✅ |
| F12 | 子 Agent 委派 | P2 | Hermes | ✅ |
| F13 | MCP 集成（MCP 客户端，动态工具发现） | P1 | Hermes | ✅ v0.14.0 |
| F14 | Progressive Disclosure 技能加载（3 级加载模式） | P2 | Hermes | 📋 |
| F15 | 条件激活技能（fallback_for_toolsets/requires_toolsets） | P2 | Hermes | 📋 |
| F16 | 消息队列模式（steer/followup/collect/interrupt） | P1 | OpenClaw | ✅ v0.14.0 |
| F17 | Block Streaming（完成即发送模式） | P1 | OpenClaw | ✅ v0.15.0 |
| F18 | 设备配对安全模型（DM 配对 + 签名挑战） | P2 | OpenClaw | ✅ v0.15.0 |
| F19 | Profile 隔离（多 Profile 并发运行） | P1 | Hermes | 📋 |
| F20 | ACP/IDE 集成（VS Code/Zed/JetBrains） | P2 | Hermes | 📋 |
| F21 | Canvas 可视化工作区（A2UI） | P3 | OpenClaw | 📋 |
| F22 | 轨迹生成（ShareGPT 格式训练数据） | P3 | Hermes | 📋 |

> **F5 重构说明**：v0.10.0 移除旧实现（架构混乱、代码质量不达标），v0.13.0 重构重新引入。v0.12.0~v0.14.1 新增了 Channel Adapter SDK + Channel Router（ABC + CLI/REST/WebSocket），但 Gateway（app.py）并未集成 Channel SDK，/chat 端点直接调用 Agent.chat()，绕过了 ChannelAdapter。重构版将彻底解决这一问题。

**F5: 消息渠道系统（重构版）**
- 优先级：P0
- 来源：OpenClaw + Hermes 融合设计
- 状态：🔄 重构设计中

核心需求：
1. **Channel Router**：统一消息路由层，ChannelMessage → ChannelAdapter → SessionRouter → Agent
2. **Gateway-Channel 集成**：Gateway 的 /chat 端点通过 ChannelRouter 路由，而非直接调用 Agent
3. **消息队列模式**：steer（注入当前轮）/ followup（排队）/ collect（安静窗口合并）/ interrupt（中止当前）
4. **Block Streaming**：完成即发送，可配置 chunk/coalesce
5. **DM 配对安全**：未知用户收到配对码，管理员审批后放行
6. **会话路由**：按 (channel_type, chat_id) 路由到独立 session
7. **多渠道并发**：多个渠道适配器同时运行，共享同一 Agent 实例
8. **渠道健康检查**：每个适配器暴露 health() 方法，Gateway 统一监控
9. **渠道配置热加载**：YAML 配置变更后无需重启即可生效
10. **媒体处理**：图片/文件/语音消息的接收和发送

**渠道适配器优先级**：

| 适配器 | 优先级 | 实现级别 | 子仓库 | 通道 | 状态 |
|--------|--------|---------|--------|------|:---:|
| CLI | P0 | 内置 | — | stdin/stdout | ✅ 已实现 |
| REST | P0 | 内置 | — | HTTP API | ✅ 已实现 |
| WebSocket | P0 | 内置 | — | WS 双向 | ✅ 已实现 |
| 飞书 | P0 | 1（官方 SDK） | `clawhermes-lark` | lark-oapi WebSocket | ✅ v0.14.1 |
| 微信 | P0 | 1（官方/社区 SDK） | `clawhermes-weixin` | 个人微信 + 企微 | ✅ v0.14.1 |
| QQ | P1 | 3（子仓库复刻） | `clawhermes-qq` | QQ Bot HTTP API | ✅ v0.15.0 |
| Telegram | P2 | 1（社区 SDK） | — | python-telegram-bot | 📋 v0.16.0 |
| Discord | P2 | 1（社区 SDK） | — | discord.py | 📋 v0.16.0 |
| Slack | P2 | 1（官方 SDK） | — | slack-bolt | 📋 v0.16.0 |
| WebChat | P2 | 3（子仓库复刻） | `clawhermes-webchat` | WebSocket Web UI | 📋 v0.16.0 |

### 2.2 已实现的扩展能力（Phase 1-2）

| # | 功能 | 说明 | 状态 |
|---|------|------|:----:|
| E1 | Channel Adapter SDK | ABC + CLI/REST/WebSocket 标准化接口 | ✅ |
| E2 | Cron 调度器 | cron/interval/oneshot，JSON 持久化 | ✅ |
| E3 | Docker Sandbox | 安全执行，资源限制，SandboxPool | ✅ |
| E4 | ACE 自适应上下文引擎 | 4 种对话类型检测 + 自动压缩策略 | ✅ |
| E5 | 内置工具集 35 个 | minimal(5)/standard(9)/full(35) 三级 profile | ✅ |
| E6 | 异步钩子 | async handler + 超时保护 | ✅ |
| E7 | Federated Skill Hub | SkillManifest + SkillHub，基于 Git 的联邦技能中心 | ✅ |
| E8 | 会话持久化 | SessionManager (SQLite WAL)，重启不丢失 | ✅ |
| E9 | 异常类层次 | ClawHermesError → LLMError/ToolError/MemoryError/ConfigError/SessionError | ✅ |

### 2.3 非功能需求

| # | 要求 | 指标 | 状态 |
|---|------|------|:----:|
| N1 | 可扩展性 | 新 LLM/新工具均通过插件注册 | ✅ |
| N2 | 安全性 | 密钥与配置分离 | ✅ |
| N3 | 可靠性 | 配置校验 fail-fast，凭证故障自动转移 | ✅ |
| N4 | 可观测性 | 关键路径有钩子暴露 | ⚠️ 基础版 |
| N5 | 易用性 | 单命令 setup，配置文件有 schema 校验 | ✅ |
| N6 | 性能 — 首次响应延迟 | < 3s（Hermes 和 OpenClaw 的基准） | 📋 |
| N7 | 性能 — 工具调用延迟 | < 1s | 📋 |
| N8 | 性能 — 记忆搜索延迟 | < 200ms（ChromaDB 优势） | 📋 |
| N9 | 性能 — 内存占用 | < 512MB | 📋 |
| N10 | 性能 — 并发会话数 | ≥ 10 | 📋 |
| N11 | 可观测性 — Dashboard | 实时监控 Agent 状态、工具调用、记忆使用 | 📋 |
| N12 | 可观测性 — 结构化日志 | JSON 格式日志，支持 OpenTelemetry 追踪 | 📋 |
| N13 | 安全性 — 沙箱模式 | Docker Sandbox 强制隔离，资源限制 | ✅ |
| N14 | 安全性 — 设备配对 | DM 配对 + 签名挑战（借鉴 OpenClaw） | 📋 |
| N15 | 安全性 — 工具权限审计 | 工具调用日志 + 权限变更审计 | 📋 |
| N16 | 安全性 — 渠道隔离 | 不同渠道的会话和凭证严格隔离 | 📋 |
| N17 | 性能 — 渠道消息延迟 | 从消息到达到 Agent 开始处理 < 500ms | 📋 |
| N18 | 可靠性 — 渠道故障隔离 | 单个渠道崩溃不影响其他渠道和 Agent 核心 | 📋 |

---

## 3. 用户场景

### 场景一：个人助理 ✅
开发者通过 REST API 或 CLI 与 Agent 对话，Agent 能记住用户偏好，越用越了解用户。Background Review 在对话后自动沉淀记忆和技能，下次对话更智能。

**已实现**：持久化记忆（ChromaDB）、自进化机制、REST API、CLI 交互。

### 场景二：代码助手 ✅
程序员在终端通过 CLI 与 Agent 交互，Agent 能够读写文件、执行命令、安装依赖、提交代码。Docker Sandbox 提供安全执行环境，工具策略引擎控制权限边界。

**已实现**：35 个内置工具（含 sqlite_query/csv_parse/hash_file/base64_codec/pdf_extract 等）、MCP 动态工具、Docker Sandbox、工具策略引擎（allow/deny）、ACE 上下文压缩。

### 场景三：团队机器人 ✅
Agent 提供 REST API，上层应用（飞书/微信/网页等）通过 Channel Adapter SDK 接入 Agent 能力，成员可以通过任意前端与 Agent 交互。Cron 调度器支持定时任务。

**已实现**：Channel Adapter SDK（ABC + CLI/REST/WebSocket）、飞书/微信渠道适配器（子仓库）、Cron 调度器、Federated Skill Hub。

### 场景四：IDE 集成开发 📋
开发者在 VS Code/Zed/JetBrains 中通过 ACP（Agent Communication Protocol）与 ClawHermes 交互，Agent 能理解项目上下文、执行重构、运行测试、提交代码。Profile 隔离确保不同项目使用不同配置和工具集。

**待实现**：F19 Profile 隔离、F20 ACP/IDE 集成、F14 Progressive Disclosure 技能加载。

### 场景五：自动化工作流 📋
通过 Cron 调度器 + 技能系统 + 子 Agent 委派，构建自动化工作流。例如：每日自动汇总代码变更、每周生成项目报告、监控日志异常自动告警。消息队列模式（steer/followup/collect/interrupt）支持复杂的工作流编排。

**待实现**：F16 消息队列模式、F15 条件激活技能、F22 轨迹生成。

### 场景六：多渠道个人助理 📋
用户通过飞书与 Agent 日常对话，工作时切换到 Slack，回家后用 WebChat。所有渠道共享同一 Agent 实例和记忆，跨渠道会话连续。消息队列模式确保 Agent 忙碌时新消息不会丢失。

**待实现**：F5 消息渠道系统、F16 消息队列模式、F17 Block Streaming。

---

## 4. 与 Hermes/OpenClaw 的差异

### 4.1 取 Hermes 之长

| 能力 | Hermes 实现 | ClawHermes 适配 | 状态 |
|------|------------|----------------|:----:|
| 三层 System Prompt | persona + tools + context | 已实现，缓存友好，省 token | ✅ |
| Background Review | 对话后自动沉淀记忆/技能 | 已实现，自进化核心机制 | ✅ |
| Curator | 技能库自动维护 | 已实现，SkillManager | ✅ |
| ContextEngine 可插拔 | 压缩策略可替换 | 已实现，ACE 自适应引擎 | ✅ |
| 多凭证池 | 高可用 | 已实现，故障自动转移 | ✅ |
| MCP 集成 | MCP 客户端，动态工具发现 | 已实现，F13 | ✅ v0.14.0 |
| Progressive Disclosure | 3 级技能加载（core/standard/extended） | 待实现，F14 | 📋 |
| 条件激活技能 | fallback_for_toolsets/requires_toolsets | 待实现，F15 | 📋 |
| Profile 隔离 | 多 Profile 并发运行 | 待实现，F19 | 📋 |
| ACP/IDE 集成 | VS Code/Zed/JetBrains 集成 | 待实现，F20 | 📋 |
| 轨迹生成 | ShareGPT 格式训练数据 | 待实现，F22 | 📋 |

### 4.2 取 OpenClaw 之长

| 能力 | OpenClaw 实现 | ClawHermes 适配 | 状态 |
|------|-------------|----------------|:----:|
| 插件钩子体系 | 工具级拦截/审批/改写 | 已实现，7 个 HookPoint + 异步 | ✅ |
| 工具策略引擎 | 精细权限控制 | 已实现，profile + allow/deny | ✅ |
| 双层持久化 | 树形 transcript | 已实现，SessionManager (SQLite WAL) | ✅ |
| 配置校验 fail-fast | 不带病运行 | 已实现，Pydantic Settings | ✅ |
| 消息队列模式 | steer/followup/collect/interrupt | 已实现，F16 | ✅ v0.14.0 |
| Block Streaming | 完成即发送模式 | 已实现，F17 | ✅ v0.15.0 |
| 设备配对安全 | DM 配对 + 签名挑战 | 已实现，F18 | ✅ v0.15.0 |
| Dashboard | 实时监控 Agent 状态 | 待实现，N11 | 📋 |
| Canvas/A2UI | 可视化工作区 | 待实现，F21 | 📋 |

### 4.3 规避两者短板

| 短板 | 来源 | 规避方案 | 状态 |
|------|------|---------|:----:|
| 主循环 3900 行 | Hermes | 拆分为小模块，单文件不超 500 行 | ✅ |
| 60+ 构造参数 | Hermes | Pydantic Settings 类型化配置 | ✅ |
| GIL 限制 | Hermes | 异步架构 + asyncio | ✅ |
| TypeScript 编译链 | OpenClaw | 纯 Python，零编译，pip install | ✅ |
| 钩子同步阻塞 | OpenClaw | 钩子异步执行 + 超时保护 | ✅ |
| 配置爆炸 | OpenClaw | 分组配置，preset，Pydantic 校验 | ✅ |
| 无 MCP 支持 | OpenClaw | F13 MCP 集成（借鉴 Hermes） | ✅ |
| 无自进化 | OpenClaw | Background Review + Curator（借鉴 Hermes） | ✅ |
| 无性能基准 | 两者 | N6-N10 性能指标体系 | 📋 |
| 无可观测性 Dashboard | Hermes | N11 Dashboard + N12 结构化日志 | 📋 |

---

## 5. 里程碑完成情况

| 阶段 | 产出 | 状态 |
|------|------|:----:|
| M1: 需求与架构 | PRD + 架构文档 + 技术选型 | ✅ |
| M2: 项目骨架 | 目录结构 + 配置 + 核心类型 | ✅ |
| M3: LLM + Agent 循环 | Provider 层 + 对话主循环 | ✅ |
| M4: 工具系统 | 注册/钩子/策略/调度 | ✅ |
| M5: 记忆 + 技能 | Memory + Skills + 自进化 | ✅ |
| M7: 测试 + 提交 | 单元测试 + GitHub | ✅ |

---

## 6. Phase 1 需求（v0.11.0）

> 状态：✅ 已完成
> 目标：代码质量与稳定性提升

### 6.1 功能需求

| # | 功能 | 优先级 | 说明 | 状态 |
|---|------|--------|------|:----:|
| P1.1 | 存根工具接入 | P0 | memory_search/memory_save/delegate_task 接入实际管理器 | ✅ |
| P1.2 | 异常类层次 | P0 | ClawHermesError → LLMError/ToolError/MemoryError/ConfigError/SessionError | ✅ |
| P1.3 | Gateway 去重 | P1 | _auto_init() 与 initialize() 合并为 _create_agent_components() | ✅ |
| P1.4 | 依赖清理 | P1 | 移除 sqlalchemy/sqlite-utils/beautifulsoup4/markdownify | ✅ |
| P1.5 | chat_async 实现 | P1 | Agent.chat_async() + LLMProvider.chat_async() | ✅ |
| P1.6 | 会话持久化 | P1 | SessionManager (SQLite WAL)，重启不丢失 | ✅ |
| P1.7 | CI 流水线 | P0 | GitHub Actions: lint + typecheck + test + build | ✅ |
| P1.8 | 工具 profiles | P1 | minimal(5)/standard(9)/full(26) 三级工具集 | ✅ |
| P1.9 | 内置工具扩展 | P2 | 新增 web_fetch/list_dir/patch_file/grep/search_replace/code_eval 等 | ✅ |
| P1.10 | 测试增强 | P0 | 测试用例 23→73，覆盖率 40%→65% | ✅ |

### 6.2 非功能需求

| # | 要求 | 指标 | 状态 |
|---|------|------|:----:|
| NP1 | 代码质量 | ruff 0 错误，mypy 0 错误 | ✅ |
| NP2 | 测试覆盖率 | 65%（核心模块 > 80%） | ⚠️ |
| NP3 | CI 全绿 | push/PR 自动检查 | ✅ |
| NP4 | 无存根代码 | 所有公开接口有实际实现 | ✅ |

---

## 7. Phase 2 完成（v0.12.0）

> 状态：✅ 已完成
> 目标：功能增强与扩展

| 里程碑 | 功能 | 状态 |
|--------|------|:----:|
| M2.1 | Channel Adapter SDK（ABC + CLI/REST/WebSocket） | ✅ |
| M2.2 | Cron 调度器（cron/interval/oneshot，JSON 持久化） | ✅ |
| M2.3 | Docker Sandbox（安全执行，资源限制，SandboxPool） | ✅ |
| M2.4 | ACE 自适应上下文引擎（4 种对话类型检测） | ✅ |
| M2.5 | 内置工具扩展 15→26（+11 个工具） | ✅ |
| M2.6 | 异步钩子（async handler，超时保护） | ✅ |
| M2.7 | mypy selective strict（6 项检查，零 Any） | ✅ |

---

## 8. Phase 3 进行中（v0.13.0~v0.14.1 ✅ | v0.15.0+ 🔄）

> 状态：v0.15.0 已交付 ✅
> 目标：生态建设 — 联邦技能中心、MCP 集成、异步化、工具扩展、渠道适配器

| 里程碑 | 功能 | 优先级 | 说明 | 状态 |
|--------|------|--------|------|:----:|
| M3.1 | Federated Skill Hub | P1 | SkillManifest + SkillHub，基于 Git 的联邦技能中心 | ✅ |
| M3.2 | Skill Evolution Graph | P2 | 技能演化图谱，可视化技能的创建/修改/合并历史 | 📋 |
| M3.3 | Multi-Modal Memory | P1 | 支持图片/文件/代码片段等多模态记忆存储 | 📋 |
| M3.4 | 用户画像持久化 | P1 | 长期用户偏好建模，跨会话用户理解 | 📋 |
| M3.5 | 技能审核流 | P2 | 技能发布前的安全审核 + 依赖检查 + 兼容性验证 | 📋 |
| M3.6a | Channel Router | P0 | 统一消息路由层，Gateway-Channel 集成 | ✅ v0.14.0 |
| M3.6b | 消息队列模式 | P0 | steer/followup/collect/interrupt | ✅ v0.14.0 |
| M3.6c | Block Streaming | P1 | 完成即发送模式 | ✅ v0.15.0 |
| M3.6d | DM 配对安全 | P1 | 配对码 + 管理员审批 | ✅ v0.15.0 |
| M3.6e | 飞书适配器 | P0 | lark-oapi，26 字段全部生效，WebSocket + Webhook 双协议 | ✅ |
| M3.6f | 微信适配器 | P0 | clawhermes-weixin，个人微信长轮询 + 企微 Webhook 双模式 | ✅ |
| M3.6g | QQ 适配器 | P1 | QQ Bot API，年轻用户主力 | ✅ v0.15.0 |
| M3.6h | Telegram 适配器 | P1 | Bot API | 📋 |
| M3.6i | Discord 适配器 | P2 | Bot API + Gateway | 📋 |
| M3.6j | Slack 适配器 | P2 | Bolt SDK | 📋 |
| M3.6k | WebChat 适配器 | P2 | 基于 WebSocket 的 Web 聊天 | 📋 |
| M3.6l | 渠道配置分层 | P0 | YAML + ${VAR} 插值 + ChannelConfigLoader | ✅ |
| M3.6m | 媒体处理 | P2 | 图片/文件/语音消息 | 📋 |
| M3.7 | MCP 集成 | P1 | F13: MCP 客户端，动态工具发现与注册 | ✅ v0.14.0 |
| M3.8 | Profile 隔离 | P1 | F19: 多 Profile 并发运行，配置/工具/记忆隔离 | 📋 |
| M3.9 | Block Streaming | P1 | F17: 完成即发送模式，降低首字延迟 | ✅ v0.15.0 |
| M3.10 | 消息队列模式 | P1 | F16: steer/followup/collect/interrupt 工作流编排 | ✅ v0.14.0 |

---

## 9. Phase 4 规划（v1.0.0）

> 状态：📋 规划中
> 目标：体验与差异化 — 可观测性、IDE 集成、安全增强

| 里程碑 | 功能 | 优先级 | 说明 | 状态 |
|--------|------|--------|------|:----:|
| M4.1 | Observability Dashboard | P1 | N11: 实时监控 Agent 状态、工具调用、记忆使用 | 📋 |
| M4.2 | 结构化日志 | P1 | N12: JSON 格式日志，OpenTelemetry 追踪 | 📋 |
| M4.3 | ACP/IDE 集成 | P2 | F20: VS Code/Zed/JetBrains Agent Communication Protocol | 📋 |
| M4.4 | Progressive Disclosure | P2 | F14: 3 级技能加载（core/standard/extended） | 📋 |
| M4.5 | 条件激活技能 | P2 | F15: fallback_for_toolsets/requires_toolsets | 📋 |
| M4.6 | 设备配对安全 | P2 | F18: DM 配对 + 签名挑战 | 📋 |
| M4.7 | 工具权限审计 | P2 | N15: 工具调用日志 + 权限变更审计 | 📋 |
| M4.8 | 性能基准测试 | P1 | N6-N10: 建立性能基准，持续监控 | 📋 |
| M4.9 | Canvas 可视化 | P3 | F21: A2UI 可视化工作区 | 📋 |
| M4.10 | 轨迹生成 | P3 | F22: ShareGPT 格式训练数据导出 | 📋 |

---

## 10. Phase 5 概要（v1.1.0+）

> 状态：📋 远期规划
> 目标：平台化 — 多租户、市场、企业级

| 方向 | 关键特性 | 说明 |
|------|---------|------|
| 多租户 | 租户隔离 + 配额管理 + 计费 | 支持企业级多团队部署 |
| 技能市场 | 发布/发现/安装/评分 | 基于 Federated Skill Hub 的去中心化市场 |
| Agent 编排 | DAG 工作流 + 条件分支 + 并行执行 | 复杂多 Agent 协作场景 |
| 企业安全 | SSO/OIDC 集成 + 数据加密 + 合规审计 | 满足企业安全要求 |
| 边缘部署 | 轻量运行时 + 本地模型 + 离线模式 | 支持边缘设备和离线场景 |
| 多语言 SDK | TypeScript/Go/Rust 客户端库 | 扩展非 Python 生态的接入能力 |

---

## 11. 版本路线图

| Phase | 版本 | 核心目标 | 关键特性 |
|-------|------|---------|---------|
| Phase 1 | v0.11.0 | 代码质量与稳定性 | 异常层次 / 会话持久化 / CI / 工具扩展 |
| Phase 2 | v0.12.0 | 功能增强与扩展 | Channel Adapter / Cron / Sandbox / ACE / 异步钩子 |
| Phase 3 | v0.13.0-v0.15.0 | 生态建设 | Skill Hub / MCP / 渠道适配器(飞书/微信) / 消息队列 / Streaming |
| Phase 4 | v1.0.0 | 体验与差异化 | Dashboard / IDE 集成 / 安全增强 / 性能基准 |
| Phase 5 | v1.1.0+ | 平台化 | 多租户 / 技能市场 / Agent 编排 / 企业安全 |
