# ClawHermes · 项目开发计划

> 版本：v2.0
> 日期：2026-06-17
> 状态：Phase 1 ✅ | Phase 2 ✅ | Phase 3 🔄 M3.1 done

---

## 一、竞争分析

### 1.1 Hermes Agent 深度研究

**技术架构：**
- 语言：Python，~3万行代码，80+模块
- 核心循环：conversation_loop.py（run_agent.py）约3900行（单文件过大）
- 构造函数：60+参数（配置复杂）
- LLM接入：自实现统一接口，200+ Provider
- 工具系统：70+注册工具，28个toolsets
- API模式：3种 — chat_completions / codex_responses / anthropic_messages
- 终端后端：6种 — local / Docker / SSH / Modal / Daytona / Singularity
- 插件系统：3种发现源（用户 ~/.hermes/plugins/、项目 .hermes/plugins/、pip entry_points），内存 Provider 和 ContextEngine 为单选插件
- ACP集成：VS Code / Zed / JetBrains IDE集成
- Profile隔离：每个profile独立 HERMES_HOME / config / memory / sessions / gateway PID
- 技能加载：Progressive Disclosure 3级（skills_list → skill_view → skill_view with path）
- 条件激活技能：fallback_for_toolsets / requires_toolsets / fallback_for_tools / requires_tools
- 轨迹生成：ShareGPT格式训练数据生成
- 自进化：Background Review + Curator 闭环
- 技能系统：SKILL.md 标准，agentskills.io Hub
- 调度：Cron 定时任务
- 用户建模：Honcho 个性化
- 迁移：OpenClaw 迁移工具
- 测试规模：25,000测试，~1,250个测试文件

**设计原则：**
1. Prompt稳定性 — 三层架构保证核心指令不被意外覆盖
2. 可观察执行 — 每步操作可追踪、可审计
3. 可中断 — 任何长操作均可安全中断
4. 平台无关核心 — 核心逻辑不依赖特定OS/平台
5. 松耦合 — 模块间通过接口交互，可独立替换
6. Profile隔离 — 多配置互不干扰

**市场定位：** 自进化 Agent 研究框架，面向研究者和高级开发者

**核心优势：**
1. 三层 System Prompt（Stable/Context/Volatile）— prefix cache 友好，省 token
2. Background Review + Curator 自进化闭环 — 越用越聪明
3. ContextEngine 可插拔设计 — 压缩策略可替换
4. CredentialPool 多凭证池 — 高可用，错误码感知冷却（401/429）
5. 200+ LLM Provider — 覆盖面最广
6. 70+ 注册工具 + 28个toolsets — 功能最丰富
7. 3种API模式 — 灵活适配不同LLM协议
8. 6种终端后端 — 覆盖本地/云端/容器化场景
9. 插件系统 — 3种发现源，单选/多选插件类型
10. ACP集成 — VS Code/Zed/JetBrains IDE无缝接入
11. Profile隔离 — 多环境独立运行互不干扰
12. Progressive Disclosure技能加载 — 按需加载，减少token浪费
13. 条件激活技能 — fallback_for/requires 智能技能选择
14. 轨迹生成 — ShareGPT格式训练数据，支持模型微调
15. agentskills.io 技能市场 — 社区生态
16. Cron 调度 — 定时任务能力
17. Honcho 用户建模 — 个性化体验

**主要劣势：**
1. 单文件过大 — run_agent.py 3900行、cli.py、setup.py 均为巨型文件，维护困难
2. 60+ 构造参数 — 使用门槛高
3. 同步架构GIL瓶颈 — 全局解释器锁限制并发性能
4. 无WebSocket实时推送 — 缺少服务端主动推送能力
5. 无钩子拦截层 — 工具调用无审批机制
6. 无工具策略引擎 — 缺少权限控制
7. 配置无 fail-fast — 错误配置运行时才暴露
8. 无健康检查 — 运维困难

### 1.2 OpenClaw 深度研究

**技术架构：**
- 语言：TypeScript (Node.js 24)，~50+子目录，编译链复杂
- 架构：Gateway 中心化 + 插件体系
- WebSocket协议：请求/响应/事件三帧类型，共享密钥认证，幂等键
- 设备配对：设备身份 + 签名挑战v3（绑定 platform + deviceFamily）
- Node系统：macOS / iOS / Android / headless 节点，暴露 canvas / camera / screen / location 命令
- Canvas/A2UI：Agent可编辑 HTML/CSS/JS 可视化工作区
- 消息队列4模式：steer / followup / collect / interrupt
- Block Streaming：完成即发送，可配置 chunk（800-1200chars）/ coalesce
- 消息渠道：22+ 渠道支持
- 工具系统：40+ 内置工具，tool profiles (minimal/coding/full)
- 技能加载：6级优先级 — workspace > project > personal > managed > bundled > extra
- 钩子：before/after tool_call
- 技能市场：ClawHub
- 安全模型：DM配对策略（pairing/open），沙箱模式（non-main），工具 allow/deny 列表
- 沙箱：Docker sandbox 执行
- Web UI：Dashboard 管理面板
- Schema系统：TypeBox schema → JSON Schema → Swift模型代码生成

**市场定位：** 生产级个人/团队 AI 助手，面向终端用户和团队

**核心优势：**
1. 22+ 消息渠道 — 覆盖所有主流平台
2. 40+ 内置工具 — 功能完整
3. tool profiles (minimal/coding/full) — 场景化工具集
4. before/after tool_call 钩子 — 工具级拦截/审批/改写
5. WebSocket协议 — 请求/响应/事件三帧，共享密钥认证，幂等键保证
6. 设备配对安全模型 — 签名挑战v3，绑定平台+设备族
7. Node系统 — 跨平台节点（macOS/iOS/Android/headless），暴露丰富设备能力
8. Canvas/A2UI — Agent可编辑可视化工作区
9. 消息队列4模式 — steer/followup/collect/interrupt 灵活消息路由
10. Block Streaming — 完成即发送，可配置chunk/coalesce
11. 6级技能加载优先级 — 精细控制技能来源
12. 安全模型 — DM配对策略 + 沙箱模式 + allow/deny列表
13. TypeBox schema → 代码生成 — 端到端类型安全
14. ClawHub 技能市场 — 社区生态
15. Docker sandbox — 安全执行环境
16. Web Dashboard — 可视化管理
17. 配置 fail-fast — 不带病运行
18. 双层持久化 — 树形 transcript

**主要劣势：**
1. WebSocket协议复杂度高 — 三帧类型+认证+幂等键+重连，实现和维护成本大
2. 设备配对流程复杂 — 签名挑战v3多步骤，用户体验门槛高
3. TypeScript运行时依赖Node 24 — 版本要求苛刻，部署受限
4. TS编译链 — 开发环境复杂
5. 钩子同步阻塞 — 影响性能
6. 配置爆炸 — 配置项过多
7. 无三层 Prompt — 每次重建，浪费 token
8. 无向量记忆 — 缺少语义搜索
9. 无自进化机制 — 不会越用越聪明
10. 无多凭证池 — 单凭证故障无转移

### 1.3 ClawHermes 现状评估（v0.12.2）

**已实现优势：**
- 纯 Python 零编译
- 三层 System Prompt（借鉴 Hermes）
- 双存储记忆（JSON + ChromaDB）
- 多凭证池（借鉴 Hermes）
- 自进化机制（Background Review + Curator）
- 钩子系统（借鉴 OpenClaw）
- Pydantic Settings 类型安全配置
- Docker + 一键安装
- 26个内置工具 + 3级Profile
- Channel Adapter SDK（CLI/REST/WebSocket）
- Cron调度（APScheduler）
- Docker Sandbox
- ACE自适应压缩
- Federated Skill Hub（M3.1 已完成）

**关键差距：**
| 项目 | ClawHermes | OpenClaw | Hermes | 优先级 |
|------|-----------|----------|--------|--------|
| 内置工具数 | 26 | 40+ | 70+ | 🔴 高 |
| 工具 profiles | ✅ 3级 | ✅ 3级 | ❌ | ✅ 已追平 |
| 技能 Hub | ✅ 联邦Hub | ClawHub | agentskills.io | 🟡 持续迭代 |
| Web UI | ❌ | Dashboard | ❌ | 🟢 低 |
| 消息渠道 | 3 | 22+ | 6 | 🟢 低 |
| 技能审核流 | ❌ | ✅ | ❌ | 🟡 中 |
| MCP集成 | ❌ | ❌ | ✅ | 🟡 中 |
| IDE集成 | ❌ | ❌ | ✅ ACP | 🟡 中 |
| Profile隔离 | ✅ 3级 | ❌ | ✅ 完整 | 🟡 增强 |
| 条件激活技能 | ❌ | ❌ | ✅ | 🟡 中 |
| Block Streaming | ❌ | ✅ | ❌ | 🟡 中 |
| 设备配对 | ❌ | ✅ | ❌ | 🟢 低 |
| 消息队列模式 | ❌ | ✅ 4种 | ❌ | 🟡 中 |

**已知代码质量问题（v0.12.2）：**
1. 并行工具执行仍为串行 — parallel_safe 分组后未真正并行执行
2. web_search 使用 curl+grep 解析 Google HTML — 脆弱不可靠
3. Gateway 全局状态 — 模块级变量，不利于多实例部署
4. SessionManager 线程安全 — SQLite check_same_thread=False 但无连接池/锁
5. 异步一致性 — chat_async 中工具执行仍为同步，BackgroundReview 用 threading.Thread 而非 asyncio
6. 测试覆盖率偏低 — 整体65%，gateway/app.py 和 tools/builtin.py 覆盖率偏低

---

## 二、优势融合方案

### 2.1 取 Hermes 之长（12项）

| # | Hermes 优势 | 融合方案 | 当前状态 |
|---|------------|---------|---------|
| H1 | 三层 System Prompt | 已实现 StableLayer/ContextLayer/VolatileLayer | ✅ 已完成 |
| H2 | Background Review | 已实现 SkillManager + BackgroundReview | ✅ 已完成 |
| H3 | Curator 自动维护 | 已实现 7天/30天/90天 自动归档 | ✅ 已完成 |
| H4 | ContextEngine 可插拔 | 已实现 ABC + LLMCompressor + NoopCompressor | ✅ 已完成 |
| H5 | CredentialPool 多凭证 | 已实现 4种调度策略 + 错误码冷却 | ✅ 已完成 |
| H6 | 200+ LLM Provider | 通过 litellm 支持 132+ Provider | ✅ 已完成 |
| H7 | Cron 调度 | APScheduler 集成 | ✅ 已完成 |
| H8 | Honcho 用户建模 | 用户画像持久化 | 📋 Phase 3 |
| H9 | MCP集成 | MCP客户端协议实现 | 📋 Phase 3 |
| H10 | Progressive Disclosure技能加载 | 3级按需加载（list→view→view with path） | 📋 Phase 3 |
| H11 | 条件激活技能 | fallback_for_toolsets/requires_toolsets 机制 | 📋 Phase 3 |
| H12 | ACP/IDE集成 | VS Code/Zed/JetBrains IDE插件 | 📋 Phase 4 |
| H13 | Profile隔离增强 | 每个Profile独立HERMES_HOME/config/memory/sessions | 📋 Phase 3 |
| H14 | 轨迹生成 | ShareGPT格式训练数据导出 | 📋 Phase 4 |

### 2.2 取 OpenClaw 之长（13项）

| # | OpenClaw 优势 | 融合方案 | 当前状态 |
|---|-------------|---------|---------|
| O1 | before/after tool_call 钩子 | 已实现 HookManager 7个钩子点 | ✅ 已完成 |
| O2 | 工具策略引擎 | 已实现 allow/deny + 并行/串行调度 | ✅ 已完成 |
| O3 | tool profiles | 已实现 minimal/standard/full 三级工具集 | ✅ 已完成 |
| O4 | 40+ 内置工具 | 已扩展至 26个，持续迭代 | 🔄 进行中 |
| O5 | 配置 fail-fast | 已实现 Pydantic field_validator | ✅ 已完成 |
| O6 | 双层持久化 | 已实现 SQLite + JSONL | ✅ 已完成 |
| O7 | Docker sandbox | 容器化工具执行环境 | ✅ 已完成 |
| O8 | Block Streaming | 完成即发送，可配置chunk/coalesce | 📋 Phase 3 |
| O9 | 消息队列模式 | steer/followup/collect/interrupt 4种模式 | 📋 Phase 3 |
| O10 | 设备配对安全模型 | 签名挑战 + allow/deny列表 | 📋 Phase 4 |
| O11 | 6级技能加载优先级 | workspace>project>personal>managed>bundled>extra | 📋 Phase 3 |
| O12 | Web Dashboard | Observability Dashboard | 📋 Phase 4 |
| O13 | 技能审核流 | 提案→审批→发布流程 | 📋 Phase 3 |

---

## 三、劣势规避策略

### 3.1 规避 Hermes 短板（8项）

| # | Hermes 短板 | 规避方案 | 状态 |
|---|------------|---------|------|
| 1 | 单文件过大（run_agent.py 3900行, cli.py, setup.py） | 拆分为小模块，单文件不超 500 行 | ✅ |
| 2 | 60+ 构造参数 | Pydantic Settings 类型化配置 | ✅ |
| 3 | 同步架构GIL瓶颈 | asyncio 异步架构 | ✅ |
| 4 | 无WebSocket实时推送 | Channel Adapter SDK + WebSocket适配器 | ✅ |
| 5 | 无钩子拦截 | HookManager 7个钩子点 | ✅ |
| 6 | 无工具策略 | allow/deny + 并行/串行调度 | ✅ |
| 7 | 配置无 fail-fast | field_validator fail-fast | ✅ |
| 8 | 无健康检查 | /health 端点 | ✅ |

### 3.2 规避 OpenClaw 短板（10项）

| # | OpenClaw 短板 | 规避方案 | 状态 |
|---|-------------|---------|------|
| 1 | WebSocket协议复杂度高 | 简化协议设计：复用HTTP升级+JSON帧，避免三帧类型 | 📋 Phase 3 |
| 2 | 设备配对流程复杂 | 渐进式安全：默认开放，可选配对，不强制签名挑战 | 📋 Phase 4 |
| 3 | Node 24运行时依赖 | 纯 Python，零编译，Python 3.11+ | ✅ |
| 4 | TS编译链 | 纯 Python，零编译 | ✅ |
| 5 | 钩子同步阻塞 | 异步钩子执行 | ⚠️ 基础版 |
| 6 | 配置爆炸 | 分组配置 + preset | ✅ |
| 7 | 无三层 Prompt | 三层架构 + stable 缓存 | ✅ |
| 8 | 无向量记忆 | ChromaDB 语义搜索 | ✅ |
| 9 | 无自进化 | Background Review + Curator | ✅ |
| 10 | 无多凭证池 | CredentialPool 4种策略 | ✅ |

### 3.3 规避 ClawHermes 自身短板（6项）

| # | 短板 | 规避方案 | 阶段 |
|---|------|---------|------|
| 1 | 并行工具执行仍为串行 | 实现 asyncio.gather 真正并行执行 parallel_safe 工具组 | Phase 3 |
| 2 | web_search 脆弱不可靠 | 接入 SearXNG / SerpAPI / Tavily 等搜索API | Phase 3 |
| 3 | Gateway 全局状态 | 重构为类实例状态，支持多实例部署 | Phase 3 |
| 4 | SessionManager 线程安全 | 引入连接池 + threading.Lock / asyncio.Lock | Phase 3 |
| 5 | 异步一致性 | 工具执行全异步化，BackgroundReview 迁移至 asyncio.create_task | Phase 3 |
| 6 | 测试覆盖率偏低（65%） | 重点补充 gateway/app.py 和 tools/builtin.py 测试 | Phase 3 |

### 3.4 规避旧渠道架构短板（8项）

| # | 旧渠道短板 | 规避方案 | 说明 |
|---|-----------|---------|------|
| 1 | bridge.py + bridge.mjs 混合架构 | 纯 Python 实现，零 Node.js 依赖 | 旧版用 Node.js bridge 调用微信/飞书 SDK，架构混乱 |
| 2 | 渠道代码与 Agent 核心耦合 | Channel Router 中间层解耦 | Gateway 不直接调用 Agent，通过 Router 路由 |
| 3 | 配置类爆炸（4个渠道配置类） | 统一 ChannelConfig + YAML 配置 | 旧版每个渠道一个 Pydantic 配置类，新版统一 |
| 4 | 渠道依赖硬编码在 pyproject.toml | 可选依赖 (extras) | pip install clawhermes[telegram] 按需安装 |
| 5 | 无消息队列 | steer/followup/collect/interrupt | 旧版消息直接处理，Agent 忙碌时丢失 |
| 6 | 无 DM 安全模型 | pairing 配对码 + allowlist | 旧版任何人都能与 Bot 对话 |
| 7 | 无流式输出 | Block Streaming 编辑模式 | 旧版等待完整响应后一次性发送 |
| 8 | 无渠道健康检查 | health() 抽象方法 + Gateway 统一监控 | 旧版渠道崩溃无感知 |

---

## 四、创新功能设计

### 4.1 Adaptive Context Engine (ACE) — 自适应上下文引擎

**核心理念：** 根据对话类型自动选择最优压缩策略

- 代码对话 → 保留代码块，压缩闲聊
- 知识问答 → 保留引用，压缩推理过程
- 创意写作 → 保留风格描述，压缩技术细节
- 实现：ContextEngine ABC 新增 `detect_conversation_type()` 方法
- ✅ 已完成基础版，Phase 3 增强对话类型检测精度

### 4.2 Skill Evolution Graph — 技能进化图谱

**核心理念：** 可视化技能的诞生、合并、归档全生命周期

- DAG 结构记录技能间演化关系
- 支持技能溯源：从哪次对话诞生、被哪些技能合并
- 技能健康度评分：使用频率 + 成功率 + 关联度
- Phase 3 实现

### 4.3 Multi-Modal Memory — 多模态记忆

**核心理念：** 记忆不止文本，支持图片/代码/结构化数据

- 图片记忆：截图 + OCR 文本 + 向量嵌入
- 代码记忆：AST 解析 + 语义索引
- 结构化记忆：表格/JSON Schema 索引
- Phase 3 实现

### 4.4 Agent Workflow Builder — Agent 工作流构建器

**核心理念：** 可视化编排多 Agent 协作流程

- 拖拽式工作流设计器
- 条件分支、循环、并行网关
- 工作流模板市场
- Phase 4 实现

### 4.5 Federated Skill Hub — 联邦技能中心

**核心理念：** 去中心化技能共享，兼容 ClawHub 和 agentskills.io

- Git-based 技能仓库（skill = git repo）
- 技能签名验证（GPG/SSH）
- 技能兼容性矩阵（版本/依赖/平台）
- ✅ M3.1 已完成基础版

### 4.6 Observability Dashboard — 可观测性仪表盘

**核心理念：** Agent 运行状态实时可视化

- Token 用量追踪
- 工具调用热力图
- 记忆增长曲线
- 技能使用排行
- LLM 响应延迟分布
- Phase 4 实现

### 4.7 Channel Adapter SDK — 渠道适配器 SDK

**核心理念：** 标准化接口，让任何人都能为 ClawHermes 写渠道适配器

- ABC 定义：`receive_message()` / `send_response()` / `get_user_info()`
- 内置适配器：CLI / REST API / WebSocket
- 示例适配器：Slack / Discord / 飞书
- ✅ 已完成基础版（CLI/REST/WebSocket）

### 4.8 Prompt Playground — 提示词实验场

**核心理念：** A/B 测试 System Prompt 效果

- 多版本 Prompt 并行测试
- 自动评估：响应质量 / 工具调用准确率 / token 效率
- Prompt 模板变量注入
- Phase 4 实现

### 4.9 MCP集成 — Model Context Protocol 客户端（💡 借鉴 Hermes）

**核心理念：** 通过MCP协议接入外部工具和数据源，无需自建

- MCP客户端协议实现，连接MCP Server
- 工具发现：自动注册MCP工具为ClawHermes工具
- 资源访问：MCP资源映射为ClawHermes上下文
- 与现有工具系统无缝集成
- Phase 3 实现

### 4.10 Progressive Disclosure 技能加载（💡 借鉴 Hermes）

**核心理念：** 按需加载技能信息，减少token浪费

- 3级加载：skills_list（名称+描述）→ skill_view（完整Prompt）→ skill_view with path（含代码路径）
- LLM首次只看到技能列表，按需请求完整内容
- 预估节省30-50%的技能相关token
- Phase 3 实现

### 4.11 条件激活技能（💡 借鉴 Hermes）

**核心理念：** 技能可根据工具集/工具可用性自动激活或降级

- fallback_for_toolsets：当指定toolset不可用时自动激活
- requires_toolsets：仅在指定toolset可用时才激活
- fallback_for_tools / requires_tools：工具级别的条件激活
- 场景示例：无Docker时自动降级到本地执行技能
- Phase 3 实现

### 4.12 消息队列模式（💡 借鉴 OpenClaw）

**核心理念：** 灵活的消息路由，支持多种交互模式

- steer：引导Agent调整方向（不中断当前执行）
- followup：追加指令（当前执行完成后处理）
- collect：收集Agent输出（批量返回）
- interrupt：强制中断当前执行
- 基于现有WebSocket适配器扩展
- → 详见 §4.17 Channel Router 渠道集成方案
- Phase 3 实现

### 4.13 Block Streaming（💡 借鉴 OpenClaw）

**核心理念：** 完成即发送，流式输出更自然

- 工具调用结果完成一个block即发送
- 可配置chunk大小（800-1200字符）
- coalesce策略：短block合并发送，长block分片发送
- 与现有WebSocket适配器集成
- → 详见 §4.18 Block Streaming 渠道流式输出方案
- Phase 3 实现

### 4.14 设备配对安全模型（💡 借鉴 OpenClaw）

**核心理念：** 渐进式安全，从开放到配对可选

- 开放模式：默认，无需认证（本地/可信网络）
- 配对模式：签名挑战，绑定设备标识
- 工具级安全：allow/deny列表控制工具权限
- 沙箱模式：非主线程工具在沙箱中执行
- Phase 4 实现

### 4.15 ACP/IDE集成（💡 借鉴 Hermes）

**核心理念：** Agent Communication Protocol，IDE内无缝使用

- VS Code扩展：侧边栏对话 + 内联代码建议
- Zed集成：通过LSP协议
- JetBrains插件：通过IntelliJ Platform SDK
- ACP协议：标准化的Agent-IDE通信
- Phase 4 实现

### 4.16 Profile隔离增强（💡 借鉴 Hermes）

**核心理念：** 每个Profile完全独立运行

- 独立HERMES_HOME目录
- 独立配置文件
- 独立记忆存储
- 独立会话管理
- 独立Gateway进程（PID隔离）
- Phase 3 实现

### 4.17 Channel Router — 渠道消息路由器

**核心理念：** 统一消息路由层，解耦 Gateway 与渠道适配器

- 消息路由：(channel_type, chat_id) → session_id 自动映射
- 消息队列：4 种模式（steer/followup/collect/interrupt）
- DM 配对：配对码生成 + 管理员审批 + allowlist
- 渠道健康检查：统一 health() 接口
- 配置热加载：YAML 变更自动检测 + 适配器重载
- 媒体处理：图片/文件/语音消息的统一处理接口
- Phase 3 实现

### 4.18 Block Streaming — 渠道流式输出

**核心理念：** 借鉴 OpenClaw 的完成即发送模式

- 编辑模式：通过编辑原消息实现流式更新（Telegram/Discord）
- 新消息模式：发送新消息追加内容（Slack/飞书）
- 分块策略：优先段落断行 → 换行 → 句子
- 空闲合并：减少单行消息刷屏
- Phase 3 实现

---

## 五、分阶段开发路线图

### Phase 1: 代码质量与稳定性（v0.11.0） ✅ 已完成

**目标：** 修复已知问题，补齐核心功能，建立工程基础设施

**里程碑：**
| 里程碑 | 交付物 | 验收标准 | 状态 |
|--------|--------|---------|------|
| M1.1 | 存根工具接入 | memory_search/memory_save/delegate_task 接入实际管理器 | ✅ |
| M1.2 | 异常类层次 | ClawHermesError → LLMError/ToolError/MemoryError/ConfigError | ✅ |
| M1.3 | Gateway 去重 | _auto_init() 与 initialize() 合并为单一方法 | ✅ |
| M1.4 | 依赖清理 | 移除未用依赖 | ✅ |
| M1.5 | chat_async 实现 | 异步对话接口完整可用 | ✅ |
| M1.6 | 会话持久化 | SQLite 持久化，重启不丢失 | ✅ |
| M1.7 | CI 流水线 | GitHub Actions: lint + typecheck + test | ✅ |
| M1.8 | 工具 profiles | minimal(5)/standard(9)/full(15+) 三级工具集 | ✅ |
| M1.9 | 内置工具扩展 | 新增 6+ 实用工具 | ✅ |
| M1.10 | 测试增强 | 测试用例从 56 增至 100+，覆盖率 > 80% | ✅ |

### Phase 2: 功能增强与扩展（v0.12.0 - v0.13.0） ✅ 已完成

**目标：** 扩展工具生态，增强 Agent 能力

**里程碑：**
| 里程碑 | 交付物 | 验收标准 | 状态 |
|--------|--------|---------|------|
| M2.1 | Channel Adapter SDK | ABC + 3个内置适配器(CLI/REST/WebSocket) | ✅ |
| M2.2 | Cron 调度 | APScheduler 集成，支持定时/周期任务 | ✅ |
| M2.3 | Docker Sandbox | 容器化工具执行环境 | ✅ |
| M2.4 | ACE 自适应压缩 | 对话类型检测 + 策略自动切换 | ✅ |
| M2.5 | 内置工具扩展至 25+ | 新增代码分析/数据处理/系统管理工具 | ✅ |
| M2.6 | 异步钩子完善 | 全钩子点异步执行，超时保护 | ✅ |
| M2.7 | mypy strict | 逐步收紧至 strict=true | ✅ |

### Phase 3: 生态建设与架构强化（v0.13.0 - v0.16.0） 🔄 进行中

**目标：** 建立技能生态，增强记忆与用户建模，修复架构短板

**里程碑：**
| 里程碑 | 交付物 | 验收标准 | 状态 |
|--------|--------|---------|------|
| M3.1 | Federated Skill Hub | Git-based 技能仓库 + 签名验证 | ✅ |
| M3.2 | 并行工具执行 | asyncio.gather 真正并行执行 parallel_safe 组 | ✅ |
| M3.3 | web_search重构 | 多搜索引擎支持(DuckDuckGo/SearXNG/SerpAPI/Tavily) | ✅ |
| M3.4 | Gateway状态重构 | GatewayState 类实例，消除 global 语句 | ✅ |
| M3.5 | SessionManager线程安全 | threading.Lock 保护所有 SQLite 操作 | ✅ |
| M3.6a | Channel Router | ChannelRouter + SessionRouter + Gateway 集成，/chat 通过 Router 路由 | ✅ P0 |
| M3.6b | 消息队列模式 | steer/followup/collect/interrupt 4 种模式完整可用 | ✅ P0 |
| M3.6c | DM 配对安全 | 配对码生成 + 管理员审批 + allowlist + 速率限制 | 📋 P1 |
| M3.6d | Block Streaming | 编辑模式 + 新消息模式 + 分块策略 + 空闲合并 | 📋 P1 |
| M3.6e | Telegram 适配器 | Bot API 集成，DM + 群聊，媒体收发，流式编辑 | 📋 P1 |
| M3.6f | Discord 适配器 | Bot API + Gateway，DM + 服务器，线程回复，流式编辑 | 📋 P1 |
| M3.6g | Slack 适配器 | Bolt SDK，DM + 频道，线程回复，Block Kit | 📋 P1 |
| M3.6h | 飞书适配器 | WebSocket 事件订阅，DM + 群聊，卡片消息 | 📋 P2 |
| M3.6i | WebChat 适配器 | WebSocket 聊天界面，Markdown 渲染，代码高亮 | 📋 P2 |
| M3.6j | 渠道配置热加载 | YAML 变更自动检测 + 适配器热重载 | 📋 P2 |
| M3.6k | 媒体处理 | 图片/文件/语音消息统一处理接口 | 📋 P2 |
| M3.7 | MCP客户端集成 | MCP协议客户端，自动注册MCP工具 | 📋 |
| M3.8 | Progressive Disclosure | 3级技能按需加载 | 📋 |
| M3.9 | 条件激活技能 | fallback_for/requires 机制 | 📋 |
| M3.12 | Profile隔离增强 | 独立HERMES_HOME/config/memory/sessions/PID | 📋 |
| M3.13 | 6级技能加载优先级 | workspace>project>personal>managed>bundled>extra | 📋 |
| M3.14 | Skill Evolution Graph | DAG 技能演化图谱 | 📋 |
| M3.15 | Multi-Modal Memory | 图片/代码/结构化记忆 | 📋 |
| M3.16 | 用户画像持久化 | Honcho 式用户建模 | 📋 |
| M3.17 | 技能审核流 | 提案→审批→发布流程 | 📋 |
| M3.18 | 测试覆盖率提升 | 65%→85%，重点补充gateway/app.py和tools/builtin.py | 📋 |

**渠道重构依赖关系：**

```
M3.6a (Channel Router) ← M3.6b (消息队列) ← M3.6c (DM配对)
                    ← M3.6d (Block Streaming)
                    ← M3.6e-g (Telegram/Discord/Slack 适配器)
                                              ← M3.6h (飞书适配器)
                                              ← M3.6i (WebChat)
                    ← M3.6j (配置热加载)
                    ← M3.6k (媒体处理)
```

### Phase 4: 体验与差异化（v0.17.0 - v0.19.0）

**目标：** 打造差异化竞争优势，完善开发者体验

**里程碑：**
| 里程碑 | 交付物 | 验收标准 |
|--------|--------|---------|
| M4.1 | Observability Dashboard | Web UI 实时监控 |
| M4.2 | Agent Workflow Builder | 可视化工作流编排 |
| M4.3 | Prompt Playground | A/B 测试 + 自动评估 |
| M4.4 | ACP/IDE集成 | VS Code扩展 + Zed/JetBrains插件 |
| M4.5 | 设备配对安全模型 | 渐进式安全：开放→配对可选 |
| M4.6 | 轨迹生成 | ShareGPT格式训练数据导出 |
| M4.7 | 示例渠道适配器 | Slack/Discord/飞书适配器 |
| M4.8 | 性能优化 | 响应延迟 < 2s，内存 < 512MB |
| M4.9 | 文档完善 | API 文档 + 教程 + 示例 |

### Phase 5: 生态成熟期（v1.0.0+）

**目标：** 生态成熟，社区运营，v1.0正式发布

**里程碑：**
| 里程碑 | 交付物 | 验收标准 |
|--------|--------|---------|
| M5.1 | 社区技能市场 | 用户可发布/安装技能，评分/评论系统 |
| M5.2 | 多语言SDK | Python/TypeScript/Go 客户端SDK |
| M5.3 | 企业级特性 | SSO/审计日志/多租户/SLA |
| M5.4 | 性能基准认证 | 公开benchmark报告，对比Hermes/OpenClaw |
| M5.5 | 插件生态 | 第三方插件开发者文档 + 插件模板 |
| M5.6 | v1.0.0 发布 | 全部功能验收通过，文档完整，性能达标 |

---

## 六、质量标准与测试流程

### 6.1 代码质量标准

| 指标 | 当前值 (v0.12.2) | Phase 3 目标 | v1.0 目标 |
|------|-----------------|-------------|----------|
| ruff lint 错误 | 0 | 0 | 0 |
| mypy 错误 | 0 | 0 | 0 |
| 测试用例数 | 165 | 250+ | 400+ |
| 测试覆盖率 | 65% | > 85% | > 90% |
| 单文件行数上限 | 500 | 500 | 500 |
| 文档覆盖率 | ~70% | > 85% | > 95% |

### 6.2 测试分层

```
┌─────────────────────────────┐
│     E2E 测试（5%）           │  完整用户场景验证
├─────────────────────────────┤
│     集成测试（20%）          │  模块间交互验证
├─────────────────────────────┤
│     单元测试（75%）          │  函数/类级别验证
└─────────────────────────────┘
```

**单元测试：** 每个公开函数/类必须有测试
**集成测试：** Agent Loop + LLM + Tools + Memory 联合验证
**E2E 测试：** 完整对话场景（含工具调用、记忆沉淀、技能进化）

**覆盖率重点区域（Phase 3）：**
- gateway/app.py — 当前覆盖率偏低，需补充API端点测试
- tools/builtin.py — 当前覆盖率偏低，需补充工具执行测试
- agent/loop.py — 并行执行路径需覆盖
- skills/hub.py — 联邦技能中心各场景需覆盖

### 6.3 CI/CD 流水线

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  lint:     ruff check src/
  typecheck: mypy src/
  test:     pytest --cov=src/clawhermes --cov-fail-under=85
  build:    docker build -t clawhermes .
```

### 6.4 性能基准

| 指标 | 当前值 (v0.12.2) | Phase 3 目标 | v1.0 目标 |
|------|-----------------|-------------|----------|
| 首次响应延迟 | 未测 | < 3s | < 2s |
| 工具调用延迟 | 未测 | < 1s | < 500ms |
| 记忆搜索延迟 | 未测 | < 200ms | < 100ms |
| 内存占用 | 未测 | < 512MB | < 512MB |
| 并发会话数 | 1 | 5+ | 10+ |
| 并行工具执行 | 串行 | 真正并行 | 真正并行 |

### 6.5 发布门禁

每个版本发布前必须通过：
- [ ] 全部测试通过（0 失败）
- [ ] 覆盖率达标（Phase 3: 85%, v1.0: 90%）
- [ ] ruff lint 0 错误
- [ ] mypy 0 错误
- [ ] CHANGELOG.md 已更新
- [ ] 版本号已更新

---

## 七、资源分配与职责分工

### 7.1 角色定义

| 角色 | 职责 | 人数 |
|------|------|------|
| 项目负责人 | 架构决策、代码审查、里程碑验收 | 1 |
| 后端开发 | Agent 核心、工具系统、记忆系统 | 1-2 |
| 基础设施 | CI/CD、Docker、部署、监控 | 1 |
| 测试 | 测试用例编写、覆盖率保障 | 1 |
| 文档 | API 文档、教程、示例 | 兼任 |

### 7.2 Phase 3 任务分配

| 任务 | 负责人 | 优先级 | 依赖 |
|------|--------|--------|------|
| M3.2 并行工具执行 | 后端 | P0 | 无 |
| M3.3 web_search重构 | 后端 | P0 | 无 |
| M3.4 Gateway状态重构 | 后端 | P1 | M3.2 |
| M3.5 SessionManager线程安全 | 后端 | P1 | M3.4 |
| M3.6a Channel Router | 后端 | P0 | M3.4 |
| M3.6b 消息队列模式 | 后端 | P0 | M3.6a |
| M3.6c DM 配对安全 | 后端 | P1 | M3.6b |
| M3.6d Block Streaming | 后端 | P1 | M3.6a |
| M3.6e Telegram 适配器 | 后端 | P1 | M3.6a |
| M3.6f Discord 适配器 | 后端 | P1 | M3.6a |
| M3.6g Slack 适配器 | 后端 | P1 | M3.6a |
| M3.6h 飞书适配器 | 后端 | P2 | M3.6e-g |
| M3.6i WebChat 适配器 | 后端 | P2 | M3.6e-g |
| M3.6j 渠道配置热加载 | 后端 | P2 | M3.6a |
| M3.6k 媒体处理 | 后端 | P2 | M3.6a |
| M3.7 MCP客户端集成 | 后端 | P1 | 无 |
| M3.8 Progressive Disclosure | 后端 | P2 | M3.1 |
| M3.9 条件激活技能 | 后端 | P2 | M3.8 |
| M3.12 Profile隔离增强 | 后端 | P2 | M3.4 |
| M3.13 6级技能加载优先级 | 后端 | P2 | M3.8 |
| M3.14 Skill Evolution Graph | 后端 | P3 | M3.1 |
| M3.15 Multi-Modal Memory | 后端 | P3 | 无 |
| M3.16 用户画像持久化 | 后端 | P3 | 无 |
| M3.17 技能审核流 | 后端 | P3 | M3.1 |
| M3.18 测试覆盖率提升 | 测试 | P0 | M3.2-M3.5, M3.6a |

---

## 八、v1.0 目标架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Observability Dashboard                    │
│              (Token追踪 / 工具热力图 / 记忆曲线)               │
├──────────────────────────────────────────────────────────────┤
│                    Channel Adapter SDK                        │
│       (CLI / REST / WebSocket / Slack / Discord / 飞书)       │
├──────────────────────────────────────────────────────────────┤
│                    ACP / IDE 集成层                           │
│          (VS Code / Zed / JetBrains)                          │
├──────────────────────────────────────────────────────────────┤
│                      Gateway 层                               │
│     FastAPI REST + WebSocket + Block Streaming + 消息队列      │
├──────────────────────────────────────────────────────────────┤
│                      Agent 核心层                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ 三层Prompt  │ │ Agent Loop │ │ Workflow   │ │ Cron调度  │ │
│  │ (缓存友好)  │ │(Think-Act) │ │ Builder   │ │(APScheduler)│
│  └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ 工具系统    │ │ 记忆系统    │ │ 技能系统    │ │ 上下文引擎 │ │
│  │ 50+工具    │ │ 多模态记忆  │ │ 进化图谱    │ │ ACE自适应 │ │
│  │ profiles   │ │ 向量+关系   │ │ 联邦Hub    │ │ 智能压缩  │ │
│  │ 钩子+策略  │ │ 用户画像    │ │ 审核流     │ │           │ │
│  │ MCP集成    │ │            │ │ 条件激活   │ │           │ │
│  └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
├──────────────────────────────────────────────────────────────┤
│                      基础服务层                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐ │
│  │ LLM    │ │ 持久化  │ │ 凭证池 │ │ 沙箱   │ │ 会话管理  │ │
│  │132+Pro │ │SQLite+ │ │4策略   │ │Docker  │ │ 线程安全  │ │
│  │viders  │ │ChromaDB│ │故障转移│ │Sandbox │ │ 连接池    │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └───────────┘ │
│  ┌────────┐ ┌────────┐ ┌────────┐                           │
│  │Profile │ │ 安全   │ │ 轨迹   │                           │
│  │ 隔离   │ │配对模型│ │ 生成   │                           │
│  └────────┘ └────────┘ └────────┘                           │
└──────────────────────────────────────────────────────────────┘
```

---

## 九、关键指标对比

| 指标 | 当前 (v0.12.2) | Phase 3 目标 | Phase 4 目标 | v1.0 目标 |
|------|---------------|-------------|-------------|----------|
| 内置工具数 | 26 | 35+ | 45+ | 50+ |
| MCP工具 | 0 | ✅ | ✅ | ✅ |
| 工具 profiles | 3 | 3+ | 3+ | 3+ |
| 测试用例 | 165 | 250+ | 350+ | 400+ |
| 测试覆盖率 | 65% | > 85% | > 88% | > 90% |
| CI 流水线 | GitHub Actions | GitHub Actions | 完整 CI/CD | 完整 CI/CD |
| 会话持久化 | SQLite | SQLite + 连接池 | SQLite + 连接池 | SQLite + Redis |
| 异步一致性 | 部分 | 完整 | 完整 | 完整 |
| 并行工具执行 | 串行 | ✅ asyncio.gather | ✅ | ✅ |
| 技能 Hub | 联邦 Hub | 联邦 Hub + 审核流 | 联邦 Hub + 审核 | 社区市场 |
| Block Streaming | ❌ | ✅ | ✅ | ✅ |
| 消息队列模式 | ❌ | ✅ 4种 | ✅ 4种 | ✅ 4种 |
| MCP集成 | ❌ | ✅ | ✅ | ✅ |
| IDE集成 | ❌ | ❌ | ✅ | ✅ |
| Profile隔离 | 3级 | 完整隔离 | 完整隔离 | 完整隔离 |
| 条件激活技能 | ❌ | ✅ | ✅ | ✅ |
| Web UI | ❌ | ❌ | Dashboard | Dashboard |
| 文档覆盖率 | ~70% | > 85% | > 90% | > 95% |
| 渠道适配器数 | 3 (CLI/REST/WS) | 6+ (+Telegram/Discord/Slack) | 7+ (+飞书/WebChat) | 8+ |
| Gateway-Channel 集成 | ❌ 未集成 | ✅ Channel Router | ✅ 完整集成 | ✅ 完整集成 |
| DM 安全模型 | ❌ | ✅ pairing | ✅ pairing + open | ✅ pairing + open |
| 媒体处理 | ❌ | ✅ 图片/文件 | ✅ +语音 | ✅ 完整 |
| 渠道健康检查 | ❌ | ✅ health() | ✅ +Dashboard | ✅ +Dashboard |

---

## 十、总结与行动建议

### 立即行动（Phase 3 当前优先）

1. **并行工具执行** — asyncio.gather 真正并行执行 parallel_safe 工具组
2. **web_search 重构** — 接入 SearXNG/SerpAPI/Tavily，替换脆弱的 curl+grep
3. **Gateway 状态重构** — 模块级变量→类实例，支持多实例部署
4. **SessionManager 线程安全** — 连接池 + asyncio.Lock
5. **异步一致性** — 工具执行全异步化，BackgroundReview 迁移至 asyncio
6. **MCP客户端集成** — 接入MCP协议，扩展工具生态
7. **测试覆盖率提升** — 65%→85%，重点补充 gateway/app.py 和 tools/builtin.py

### 中期规划（Phase 3 后半 + Phase 4）

- Channel Router + 消息队列 + DM 配对
- Block Streaming + Telegram/Discord/Slack 适配器
- 渠道配置热加载 + 媒体处理
- Progressive Disclosure + 条件激活技能 + 6级技能加载优先级
- Profile隔离增强 + 设备配对安全模型
- Skill Evolution Graph + Multi-Modal Memory + 用户画像
- Observability Dashboard + Agent Workflow Builder
- ACP/IDE集成 + Prompt Playground

### 远期愿景（Phase 5）

- 社区技能市场 + 多语言SDK
- 企业级特性（SSO/审计/多租户）
- 性能基准认证
- v1.0.0 正式发布

### 核心差异化定位

ClawHermes 的差异化竞争力在于 **"Hermes 的深度 + OpenClaw 的工程品质"**：

1. **vs Hermes** — 更好的代码组织（无巨型文件）、真正的异步架构（非GIL受限）、WebSocket实时推送、工具策略引擎
2. **vs OpenClaw** — 零编译纯Python、三层Prompt省token、向量记忆语义搜索、自进化闭环、多凭证池高可用
3. **独特优势** — MCP集成扩展工具边界、条件激活技能智能降级、Block Streaming+消息队列灵活交互、Profile完整隔离多环境运行
