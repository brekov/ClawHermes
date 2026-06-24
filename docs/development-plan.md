# ClawHermes · 项目推进计划

> 版本：v2.1
> 日期：2026-06-24
> 基线版本：v0.15.0（Block Streaming ✅ + DM 配对 ✅ + QQ 适配器 ✅）
> 状态：Phase 1 ✅ | Phase 2 ✅ | Phase 3 ✅ v0.15.0 | 下一目标 v0.16.0
> 方法论：软件工程全流程 — 现状评估 → 竞品研究 → 差距分析 → SMART 目标 → 架构演进 → 分阶段路线图 → 质量保障 → 风险管理

---

## 目录

1. [项目定位与核心目标](#1-项目定位与核心目标)
2. [当前进度评估（v0.15.0）](#2-当前进度评估v0150)
3. [竞品深度研究](#3-竞品深度研究)
4. [差距分析与差异化方向](#4-差距分析与差异化方向)
5. [SMART 目标设定](#5-smart-目标设定)
6. [架构演进设计](#6-架构演进设计)
7. [分阶段实施路线图](#7-分阶段实施路线图)
8. [质量保障体系](#8-质量保障体系)
9. [风险管理与应对](#9-风险管理与应对)
10. [成功标准与验收门禁](#10-成功标准与验收门禁)
11. [核心指标追踪表](#11-核心指标追踪表)

---

## 1. 项目定位与核心目标

### 1.1 一句话定位

> **ClawHermes = Hermes 的自进化深度 × OpenClaw 的工程品质 × Python 原生零编译**
>
> 一个开箱即用、越用越聪明、可通过 REST API 嵌入任何系统的 Python AI Agent 框架。

### 1.2 三大价值支柱

| 支柱 | 内涵 | 竞品对标 |
|:---|:---|:---|
| **越用越聪明** | Background Review + Curator 自进化闭环 + 向量记忆语义搜索 | 借鉴 Hermes，OpenClaw 无此能力 |
| **工程可靠** | Pydantic 类型化配置 / asyncio 异步 / fail-fast 校验 / 7 钩子点 / 工具策略引擎 | 借鉴 OpenClaw 工程实践 |
| **即插即用** | `pip install` / REST API 26 端点 / Channel Adapter SDK / Docker 一键 | 规避 Hermes 60+ 参数与 OpenClaw TS 编译链 |

### 1.3 差异化定位矩阵

| 维度 | Hermes | OpenClaw | **ClawHermes** |
|:---|:---|:---|:---|
| 语言 | Python | TypeScript | **Python** |
| 定位 | 研究探索型 Agent | 消息网关 + 个人助手 | **生产可用型 Agent 框架** |
| 核心循环 | 3900 行单文件 | 单进程嵌入 | **~300 行模块化** |
| 构造参数 | 60+ | 适中 | **~10（Pydantic）** |
| 异步模型 | 同步为主 (GIL) | 事件循环 | **asyncio 原生** |
| 安装方式 | 源码 clone | npm + 编译 | **pip install** |
| 向量记忆 | ❌ | ❌ | **✅ ChromaDB（三者唯一）** |
| 自适应压缩 | ❌ | ❌ | **✅ ACE（独创）** |
| 自进化闭环 | ✅ | ❌ | **✅** |
| 钩子体系 | ❌ | ✅ 同步 | **✅ 异步** |
| 消息渠道 | ❌ | 22+ | **SDK 抽象 + 飞书 P0 + 微信 P0 ✅** |
| MCP 协议 | ✅ | ❌ | ✅ |

### 1.4 北极星目标（v1.0.0）

```
v1.0.0 时 ClawHermes 应成为：
  1. Python 生态中最易嵌入的 Agent 框架（pip install + REST + Docker + SDK）
  2. 具备完整自进化能力的生产级框架（记忆 + 技能 + 用户建模闭环）
  3. 工程质量对标 OpenClaw（类型安全 + fail-fast + Dashboard + 钩子）
  4. 能力深度对齐 Hermes（MCP + Progressive Disclosure + 条件激活技能）
  5. 差异化创新壁垒（ACE 自适应 / 向量记忆 / 联邦 Hub / Channel SDK）
```

---


### 2.1 版本交付历史
## 2. 当前进度评估（v0.15.0）

| 版本 | 日期 | 核心交付 | 测试 |
|:---|:---|:---|:---:|
| v0.1.0 | 2026-06-16 | Agent 循环、三层 Prompt、钩子、8 工具、记忆、多凭证池 | 56 |
| v0.11.0 | 2026-06-17 | 异常层次、会话持久化、CI、工具 profiles、chat_async | 73 |
| v0.12.0 | 2026-06-17 | Channel SDK、Cron、Docker Sandbox、ACE、异步钩子、26 工具 | 165 |
| v0.12.2 | 2026-06-17 | P0-P3 评审修复、版本动态化、README 与架构文档同步 | 165 |
| **v0.13.0** | **2026-06-17** | **并行执行、web_search 重构、Gateway 状态重构、线程安全、Channel Router、消息队列 4 模式** | **203** |
| **v0.14.0** | **2026-06-22** | **全链路异步化、MCP 集成、工具扩展至 35、MCP 异步修复、测试覆盖率 73%（373 测试）** | **373** |
| **v0.14.1** | **2026-06-23** | **渠道配置架构重构（YAML ${VAR} 单一来源）、15 死配置字段激活、LarkConfig 26/26 全部生效、微信双模式** | **373** |
| **v0.14.2** | **2026-06-23** | **文档审计 — 端点纠错 23→26、项目定位修正、Channel 架构重写、RELEASE.md 对齐 GitHub 格式** | **373** |
| **v0.15.0** | **2026-06-24** | **Block Streaming SSE（M3.6c）+ DM 配对安全（M3.6d）+ QQ 适配器（M3.6g）** | **416** |

### 2.2 已交付功能清单（19 项）

| # | 功能 | 代码位置 | 状态 |
|:---|:---|:---|:---:|
| F1 | 多 LLM 接入（litellm 132+ provider） | `llm/provider.py` | ✅ |
| F2 | 思考-行动循环（50 次上限 + 7 钩子点） | `agent/loop.py` | ✅ |
| F3 | 35 内置工具 + 3 级 Profile（minimal/standard/full） | `tools/builtin.py` | ✅ |
| F4 | 双存储记忆（JSON + ChromaDB 向量语义搜索） | `agent/memory.py` | ✅ |
| F5 | 会话持久化（SQLite WAL + threading.Lock 线程安全） | `agent/session.py` | ✅ |
| F6 | 技能管理（SkillManager + CRUD + 元数据） | `skills/manager.py` | ✅ |
| F7 | 自进化闭环（Background Review + Curator 定期维护） | `skills/manager.py` | ✅ |
| F8 | 工具钩子（before/after 7 钩子点 + 异步超时保护） | `agent/loop.py` | ✅ |
| F9 | 工具策略引擎（Profile + allow/deny + 并行安全标记） | `tools/builtin.py` | ✅ |
| F10 | 上下文压缩（LLMCompressor 可插拔） | `agent/context.py` | ✅ |
| F11 | 多凭证池（CredentialPool 4 策略 + 故障冷却） | `llm/provider.py` | ✅ |
| F12 | 子 Agent 委派（并行执行 + 深度限制 MAX_DEPTH=2） | `agent/delegate.py` | ✅ |
| F13 | 异步接口（Agent.chat_async + LLMProvider.chat_async） | `agent/loop.py` | ✅ |
| F14 | 异常层次（5 大类 10 子类 + 2 扩展异常） | `agent/exceptions.py` | ✅ |
| F15 | Cron 调度器（cron/interval/oneshot + JSON 持久化） | `agent/scheduler.py` | ✅ |
| F16 | Docker 沙箱（SandboxPool 预热 + 资源限制） | `tools/sandbox.py` | ✅ |
| F17 | ACE 自适应上下文（4 种对话类型自动检测） | `agent/ace.py` | ✅ |
| F18 | Channel Adapter SDK（ABC + CLI/REST/WebSocket） | `channel/adapter.py` | ✅ |
| F19 | Federated Skill Hub（Git 联邦 + SHA-256 校验） | `skills/hub.py` | ✅ |

### 2.3 v0.13.0~v0.14.0 新增能力

| 里程碑 | 能力 | 关键实现 |
|:---|:---|:---|
| M3.1 | Federated Skill Hub | SkillHub 发布/安装/搜索 + SkillManifest 元数据 |
| M3.2 | 并行工具执行 | asyncio.gather 真正并行 + parallel_safe 标记 |
| M3.3 | web_search 重构 | DuckDuckGo/SearXNG/SerpAPI/Tavily + 优雅降级 |
| M3.4 | Gateway 状态重构 | 模块变量 → GatewayState 类 + 消除 global |
| M3.5 | SessionManager 线程安全 | threading.Lock 保护全部 SQLite 操作 |
| M3.6a | Channel Router | 统一消息路由层 + SessionRouter 映射管理 |
| M3.6b | 消息队列 4 模式 | steer / followup / collect / interrupt 完整实现 |
| M3.7 | MCP 客户端集成 | MCPClient (stdio + HTTP) + MCPRegistry + 3 Gateway 端点 |
| M3.10 | 内置工具扩展至 35 | +9 工具（sqlite_query / csv_parse / hash_file / disk_usage / base64_codec / process_list / image_info / pdf_extract / markdown_render） |
| M3.11 | 全链路异步化 | 消除全部 threading.Thread，100% asyncio 原生 |
| M3.12 | 测试覆盖率提升 | 66% → 73%（203 → 373 测试），Gateway + 组件全覆盖 |

### 2.4 当前技术栈

```
语言:       Python 3.12+
LLM 编排:   litellm（132+ provider）
Web 框架:   FastAPI + uvicorn
向量存储:   ChromaDB 0.6+
关系存储:   SQLite（aiosqlite + WAL）
配置管理:   Pydantic Settings + YAML
类型检查:   mypy（6 strict checks）
代码检查:   ruff（0 errors）
测试框架:   pytest + pytest-asyncio + pytest-cov
CI/CD:      GitHub Actions（lint + typecheck + test + build）
```

### 2.5 Gateway 端点现状（33 个）

| 分类 | 端点 | 方法 |
|:---|:---|:---:|
| 核心 | `/init` `/chat` `/chat/stream` `/health` `/tools` | POST/GET |
| 记忆 | `/memory/save` `/memory/search` | POST/GET |
| 技能 | `/skills` `/skills/create` `/curator/run` | GET/POST |
| 会话 | `/sessions` `/sessions/{id}` | GET/DELETE |
| 调度 | `/cron/jobs` `/cron/jobs/{id}` `/cron/jobs/{id}/pause` `/cron/jobs/{id}/resume` | CRUD |
| 渠道 | `/channels` `/channels/sessions` `/wechat/webhook` `/wecom/webhook` `/feishu/webhook` | GET/POST |
| MCP | `/mcp/servers` `/mcp/servers/{name}` | POST/GET/DELETE |

---

## 3. 竞品深度研究

### 3.1 Hermes Agent（NousResearch/hermes-agent）

**定位**：自进化 Agent 研究框架 | Python | ~3 万行 | 80+ 模块 | GitHub 106k+ Stars

**核心优势（可借鉴）**：

| 能力 | 实现细节 | ClawHermes 状态 |
|:---|:---|:---|
| 三层 System Prompt | Stable / Context / Volatile，prefix cache 友好 | ✅ 已实现 |
| Background Review + Curator | 对话后自动沉淀记忆/技能，定期维护 | ✅ 已实现 |
| CredentialPool 多凭证池 | 轮询/最少使用/随机 + 401/429 故障冷却 | ✅ 已实现 |
| 200+ LLM Provider | 统一接口覆盖几乎所有 LLM | ✅ 基于 litellm 132+ |
| MCP 客户端 | 动态工具发现，扩展工具边界 | ❌ **Phase 3 优先级 P0** |
| Progressive Disclosure | 3 级技能加载（list→view→path），省 token | ❌ **Phase 4** |
| 条件激活技能 | fallback_for_toolsets / requires_toolsets 智能选择 | ❌ **Phase 4** |
| Profile 隔离 | 每 Profile 独立 HOME/config/memory/sessions | ❌ **Phase 3** |
| ACP/IDE 集成 | VS Code / Zed / JetBrains | ❌ **Phase 4** |
| 轨迹生成 | ShareGPT 格式训练数据导出 | ❌ **Phase 4** |
| 插件系统 | 3 种发现源 + pip entry_points | ❌ **远期** |
| 70+ 内置工具 + 28 toolsets | 最丰富的工具生态 | ⚠️ 35 工具，差距缩小中 |

**关键劣势（应规避）**：
- 核心循环 3900 行单文件 — ClawHermes 已解决（~300 行模块化）
- 60+ 构造参数 — ClawHermes 已解决（Pydantic ~10 参数）
- 同步架构受 GIL 限制 — ClawHermes 已解决（asyncio 原生）
- 无钩子拦截层 — ClawHermes 已解决
- 无工具策略引擎 — ClawHermes 已解决
- 无 WebSocket 实时推送 — ClawHermes 已规划

### 3.2 OpenClaw（openclaw/openclaw）

**定位**：生产级个人/团队 AI 助手 | TypeScript (Node.js) | ~50+ 子目录 | 编译链复杂

**核心优势（可借鉴）**：

| 能力 | 实现细节 | ClawHermes 状态 |
|:---|:---|:---|
| 钩子体系 | before/after tool_call 工具级拦截 | ✅ 已实现并增强（异步+超时） |
| 工具策略引擎 | Profile + allow/deny 精细权限 | ✅ 已实现 |
| Block Streaming | 完成即发送，chunk/coalesce 可配 | ✅ SSE v0.15.0 |
| 消息队列 4 模式 | steer/followup/collect/interrupt | ✅ v0.14.0 已实现 |
| 22+ 消息渠道 | 覆盖所有主流平台 | ⚠️ SDK 就绪，飞书+微信 ✅，QQ 待实现 |
| Dashboard | 实时监控 Agent 状态 | ❌ **Phase 4 优先级 P0** |
| Canvas/A2UI | 可编辑 HTML/CSS/JS 可视化工作区 | ❌ **远期** |
| 设备配对安全 | DM 配对 + 签名挑战 v3 | ❌ **Phase 3** |
| 6 级技能加载优先级 | workspace > project > personal > managed > bundled > extra | ❌ **Phase 4** |
| 配置校验 fail-fast | 不带病运行 | ✅ 已实现 |

**关键劣势（应规避）**：
- TypeScript 编译链，部署门槛高 — ClawHermes 纯 Python 零编译
- 无三层 System Prompt — ClawHermes 已实现
- 无向量记忆语义搜索 — ClawHermes 已实现（三者唯一）
- 无自进化闭环 — ClawHermes 已实现
- 无自适应上下文压缩 — ClawHermes 已实现（ACE 独创）
- 无 Channel Adapter SDK 抽象 — ClawHermes 已实现（三者唯一）

### 3.3 竞争策略矩阵

| 策略 | 对标对象 | 具体措施 | 状态 |
|:---|:---|:---|:---:|
| **优势融合** | Hermes 三层 Prompt | 已实现 + 缓存优化 | ✅ |
| **优势融合** | OpenClaw 钩子系统 | 已实现 + 异步非阻塞 + 超时保护 | ✅ |
| **优势融合** | Hermes 自进化 | Background Review + Curator 闭环 | ✅ |
| **优势融合** | OpenClaw 工具 Profile | 3 级 Profile + allow/deny | ✅ |
| **优势融合** | Hermes 多凭证池 | CredentialPool 4 策略 + 故障冷却 | ✅ |
| **劣势规避** | Hermes 3900 行循环 | 核心循环 ~300 行（缩小 13 倍） | ✅ |
| **劣势规避** | Hermes 60+ 参数 | Pydantic Settings ~10 参数 | ✅ |
| **劣势规避** | OpenClaw TS 编译 | 纯 Python 零编译 `pip install` | ✅ |
| **劣势规避** | OpenClaw 同步钩子 | 异步钩子 + 超时保护 | ✅ |
| **创新突破** | 三者均无 | ChromaDB 向量记忆语义搜索 | ✅ |
| **创新突破** | 三者均无 | ACE 自适应上下文压缩 | ✅ |
| **创新突破** | vs 中心化 Hub | Federated Skill Hub 去中心化 | ✅ |
| **创新突破** | 三者均无 | Channel Adapter SDK 标准化抽象 | ✅ |
| **追赶补齐** | Hermes MCP | MCP 客户端集成 | ✅ 已达成 |
| **追赶补齐** | Hermes 70+ 工具 | 工具扩展至 45+ | 📋 P1 |
| **追赶补齐** | OpenClaw 渠道 | 6+ 渠道适配器（四级 SDK 策略） | 📋 P1 |
| **追赶补齐** | OpenClaw Dashboard | Observability Dashboard | 📋 P1 |

---

## 4. 差距分析与差异化方向

### 4.1 关键差距（v0.15.0 → v1.0.0）

| 差距领域 | 当前 | 目标 | 严重程度 |
|:---|:---|:---|:---:|
| MCP 协议 | ✅ 已集成 MCP 客户端 v0.14.0 | 多 MCP Server 动态工具发现 | ✅ 已达成 |
| 渠道适配器 | ✅ 飞书 + 微信 已集成 | 8+（QQ/Telegram/Discord/Slack） | 🟡 中 |
| Block Streaming | ✅ SSE v0.15.0 | ✅ 完成 | ✅ 已达成 |
| 测试覆盖率 | 71%（416 测试） | >90% | 🟡 中 |
| 内置工具数 | 35 | 45+ | 🟡 中 |
| 多模态记忆 | ❌ 仅文本 | ✅ 图片/文件 | 🟡 中 |
| Profile 隔离 | 3 级工具 Profile | 完整隔离（config/memory/sessions） | 🟡 中 |
| 条件激活技能 | ❌ | ✅ | 🟢 低 |
| Progressive Disclosure | ❌ | ✅ 3 级加载 | 🟢 低 |
| IDE 集成 | ❌ | ✅ LSP/ACP | 🟢 低 |
| Dashboard | ❌ | ✅ | 🟢 低 |
| DM 安全模型 | ✅ | ✅ | ✅ 已达成 |

### 4.2 差异化创新护城河

| 创新点 | 说明 | 竞品对比 | 壁垒 |
|:---|:---|:---|:---|
| **ACE 自适应压缩** | 对话类型自动检测 + 4 种压缩策略切换 | 三者唯一 | 高（需上下文理解） |
| **ChromaDB 向量记忆** | 语义搜索记忆，非关键词匹配 | 三者唯一 | 中（技术选型） |
| **Federated Skill Hub** | Git 去中心化技能共享 + SHA-256 校验 | vs 中心化 Hub | 中（协议设计） |
| **Channel Adapter SDK** | 标准化渠道抽象，4 方法实现新渠道 | 三者唯一 | 中（接口设计） |
| **纯 Python 零编译** | `pip install` 一键安装 | vs TS 编译链 | 低（语言选择） |

---

## 5. SMART 目标设定

### 5.1 v0.14.0（Phase 3 中期 ✅ 已达成）

| 目标 | 衡量标准 | 时限 |
|:---|:---|:---|
| MCP 客户端集成（F13） | 支持 3+ MCP Server 动态工具发现 | 2 周 |
| 内置工具扩展至 35+ | +9 工具（浏览器/数据库/图片/代码等） | 2 周 |
| 全链路异步化 | 消除全部 threading.Thread 调用，100% asyncio | 1 周 |
| 测试覆盖率 > 80% | 65% → 80%，重点补充 gateway + tools；⚠️ 实际 ~61%，Phase 3 后期推进 | 1 周 |

### 5.1b v0.15.0 全部目标（✅ 已完成）

| 目标 | 衡量标准 | 时限 |
|:---|:---|:---|
| DM 配对安全模型 | pairing 码 + 管理员审批 + 签名挑战 | ✅ 已完成 |
| QQ 适配器 | QQ Bot HTTP API + 子仓库复刻，完成第三渠道 | ✅ 已完成 |

### 5.2 v0.16.0（Phase 3 后期）

| 目标 | 衡量标准 | 时限 |
|:---|:---|:---|
| Telegram 适配器 | 社区 python-telegram-bot → ChannelAdapter 封装 | 1 周 |
| Discord 适配器 | 社区 discord.py → ChannelAdapter 封装 | 1 周 |
| Slack 适配器 | 官方 slack-bolt → ChannelAdapter 封装 | 1 周 |
| Profile 隔离 | 独立 config/memory/sessions per profile | 1 周 |

### 5.3 v0.17.0（Phase 3 收尾）

| 目标 | 衡量标准 | 时限 |
|:---|:---|:---|
| 多模态记忆 | 支持图片/文件/代码片段存储与检索 | 2 周 |
| 用户画像持久化 | 长期偏好建模，跨会话用户理解 | 1 周 |
| 工具扩展至 45+ | +10 工具（语音/视频/地图/邮件等） | 2 周 |
| 测试覆盖率 > 85% | 80% → 85%，全模块覆盖 | 1 周 |

### 5.4 v1.0.0（Phase 4）

| 目标 | 衡量标准 | 时限 |
|:---|:---|:---|
| Observability Dashboard | 实时监控 Agent 状态/工具调用/记忆使用 | 3 周 |
| 结构化日志 + OpenTelemetry | JSON 日志 + Trace/Span 全链路追踪 | 1 周 |
| Progressive Disclosure | 3 级技能加载（core/standard/extended） | 2 周 |
| 条件激活技能 | fallback_for / requires 智能技能选择 | 1 周 |
| 6 级技能加载优先级 | workspace > project > personal > managed > bundled > extra | 1 周 |
| ACP/IDE 集成 | VS Code 插件基础版 | 2 周 |
| 性能基准认证 | 建立 8 项性能基准并持续监控 | 1 周 |
| 测试覆盖率 > 90% | 85% → 90%，补充集成测试 | 1 周 |

---

## 6. 架构演进设计

### 6.1 v1.0.0 目标架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         接入层（Access Layer）                        │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ REST API │ │ WebSocket│ │ Telegram │ │ Discord  │ │ Slack    │  │
│  │ (27端点) │ │ (实时推送)│ │ Bot API  │ │ Bot API  │ │ Bolt SDK │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       └────────────┴────────────┴────────────┴────────────┘         │
│                                │                                     │
│                    ┌───────────▼───────────┐                         │
│                    │   Channel Router      │                         │
│                    │  · SessionRouter      │                         │
│                    │  · 消息队列 4 模式     │                         │
│                    │  · DM 配对安全        │                         │
│                    │  · Block Streaming    │                         │
│                    │  · 渠道配置热加载      │                         │
│                    └───────────┬───────────┘                         │
└────────────────────────────────┼────────────────────────────────────┘
                                  │
┌────────────────────────────────▼────────────────────────────────────┐
│                       Gateway 层（v0.15.0 ✅）                       │
│                                                                      │
│  FastAPI · GatewayState 类 · 27 REST 端点 · Cron 调度 · Docker 沙箱 │
└────────────────────────────────┬────────────────────────────────────┘
                                   │
┌─────────────────────────────────▼───────────────────────────────────┐
│                         Agent 核心层                                 │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │         三层 System Prompt + 6 级技能加载优先级               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Agent Loop（asyncio 全链路异步）                             │   │
│  │  LLM → 工具（asyncio.gather 并行）→ ACE 自适应压缩 → 迭代    │   │
│  │  Block Streaming → SSE 完成即发送                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 工具系统  │ │ 记忆系统  │ │ 技能系统  │ │ MCP 集成 │ │ 子Agent  │ │
│  │ ·45+工具 │ │ ·多模态  │ │ ·P.Discl │ │ ·客户端  │ │ ·委派    │ │
│  │ ·3级Prof │ │ ·向量搜索│ │ ·条件激活│ │ ·工具发现│ │ ·并发    │ │
│  │ ·钩子    │ │ ·画像    │ │ ·6级加载│ │ ·注册    │ │          │ │
│  │ ·策略    │ │ ·ChromaDB│ │ ·审核流 │ │          │ │          │ │
│  │ ·沙箱    │ │          │ │ ·演化图 │ │          │ │          │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│                                                                      │
│  ┌──────────┐ ┌──────────────────────────────────────────────────┐  │
│  │ Profile  │ │ 消息队列层（v0.14.0 ✅）                         │  │
│  │ 完整隔离 │ │ steer / followup / collect / interrupt           │  │
│  └──────────┘ └──────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────┘
                                   │
┌─────────────────────────────────▼───────────────────────────────────┐
│                       基础设施层                                     │
│                                                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────────┐ │
│  │ LLM    │ │ 持久化  │ │ 凭证池 │ │ 沙箱   │ │ 可观测性         │ │
│  │132+   │ │SQLite+ │ │4策略   │ │Docker  │ │ Dashboard +      │ │
│  │Provider│ │ChromaDB│ │故障转移│ │Sandbox │ │ 结构化日志 +     │ │
│  │        │ │        │ │        │ │Pool    │ │ OpenTelemetry    │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 关键架构演进

| 演进项 | 当前（v0.15.0） | 目标（v1.0.0） |
|:---|:---|:---|
| 异步模型 | 全链路 asyncio（含 1 处可控 threading.Thread 用于 MCP 嵌套协程兼容） | 连接池 + 多实例部署就绪 |
| Gateway 状态 | GatewayState 类（单实例） | 连接池 + 多实例部署就绪 |
| 渠道集成 | Channel Router + 飞书 + 微信 ✅；QQ + DM 配对开发中 | 8+ 渠道适配器 + 配置热加载 |
| 技能加载 | 全量加载（浪费 token） | Progressive Disclosure 3 级 + 6 级优先级 + 条件激活 |
| 工具系统 | 35 内置 + MCP 动态工具 | 45+ 内置 + MCP 动态工具 |
| 记忆系统 | 文本向量 | 多模态（图片/文件/代码）+ 用户画像 |
| 可观测性 | 日志 | Dashboard + 结构化日志 + OpenTelemetry |
| 流式输出 | ✅ Block Streaming（SSE）v0.15.0 | Block Streaming（SSE）|

---

## 7. 分阶段实施路线图

### 7.1 Phase 1 & 2（✅ 已完成）

| Phase | 版本 | 核心交付 |
|:---|:---|:---|
| Phase 1 | v0.1.0 → v0.11.0 | 核心框架、异常层次、会话持久化、CI、工具 profiles |
| Phase 2 | v0.12.0 → v0.12.2 | Channel SDK、Cron、Docker Sandbox、ACE、异步钩子、26 工具 |

### 7.2 Phase 3（🔄 进行中 — v0.15.0 ✅，推进 v0.16.0）

#### 7.2.1 已完成（v0.13.0~v0.14.0）

| 里程碑 | 交付 | 测试 |
|:---|:---|:---:|
| M3.1 | Federated Skill Hub（Git 联邦 + 校验） | ✅ |
| M3.2 | 并行工具执行（asyncio.gather） | 5 |
| M3.3 | web_search 重构（4 引擎 + 降级） | 7 |
| M3.4 | Gateway 状态重构（类实例） | 3 |
| M3.5 | SessionManager 线程安全（Lock） | 2 |
| M3.6a | Channel Router（统一路由层） | 8 |
| M3.6b | 消息队列 4 模式 | 6 |

#### 7.2.2 下一优先级（v0.14.0 ✅ 已达成）

| 里程碑 | 功能 | 优先级 | 工作量 | 依赖 |
|:---|:---|:---:|:---:|:---|
| **M3.7 ✅** | **MCP 客户端集成（F13）** — MCP 协议客户端，动态工具发现与注册，支持 3+ MCP Server | 🔴 P0 | 3d | litellm |
| **M3.10 ✅** | **内置工具扩展至 35+** — 浏览器工具(playwright)、数据库工具(sqlite)、图片处理(Pillow)、代码分析(AST) | 🔴 P0 | 4d | — |
| **M3.11 ✅** | **全链路异步化** — BackgroundReview → asyncio，消除全部 threading.Thread，零阻塞调用 | 🔴 P0 | 2d | M3.2 |
| **M3.12 ⚠️** | **测试覆盖率 > 80%** — 重点补充 gateway/app.py 和 tools/builtin.py；⚠️ 实际 ~61%，持续追赶 | 🟡 P1 | 2d | — |

#### 7.2.3 Phase 3 中期（v0.15.0）

| 里程碑 | 功能 | 优先级 | 工作量 |
|:---|:---|:---:|:---:|
| **M3.6c** | ✅ **Block Streaming（F17）** — SSE 完成即发送，chunk 800-1200 chars，首字延迟降低 50%+ | 🟡 P1 | ✅ 完成 |
| **M3.6d** | **DM 配对安全（F18）** — 配对码生成 + 管理员审批 + 签名挑战 | 🟡 P1 | 3d |
| **M3.6e** | ✅ **飞书适配器** — 分层架构 lark-oapi + Hermes vendor 消息引擎；WebSocket 长连接 + Token 管理 + send_response/get_user_info | 🔴 P0 | ✅ 完成 | M3.6a |
| **M3.6f** | ✅ **微信适配器** — clawhermes-weixin 子仓库 + wechatpy SDK；ChannelAdapter + Gateway 集成 | 🔴 P0 | ✅ 完成 | M3.6a |
| **M3.6g** | 🔄 **QQ 适配器（PR #21 审查中）** — 子仓库 `clawhermes-qq`，复刻 Hermes QQ SDK 逻辑（Lv3·子仓库复刻） | 🟡 P1 | 2d | M3.6a |
| **M3.6h** | **Telegram 适配器** — 社区 python-telegram-bot → ChannelAdapter（Lv1·社区 SDK）→ 推至 v0.16.0 | 🟢 P2 | — | M3.6a |
| **M3.6i** | **Discord 适配器** — 社区 discord.py → ChannelAdapter（Lv1·社区 SDK）→ 推至 v0.16.0 | 🟢 P2 | — | M3.6a |
| **M3.6j** | **Slack 适配器** — 官方 slack-bolt → ChannelAdapter（Lv1·官方 SDK）→ 推至 v0.16.0 | 🟢 P2 | — | M3.6a |

| 里程碑 | 功能 | 优先级 | 工作量 |
|:---|:---|:---:|:---:|
| **M3.3** | **多模态记忆（F21）** — 图片/文件/代码片段向量化存储与检索 | 🟡 P1 | 3d |
| **M3.4** | **用户画像持久化（F22）** — 长期偏好建模，跨会话用户理解 | 🟡 P1 | 2d |
| **M3.10b** | **内置工具扩展至 45+** — 语音识别、地图服务、邮件、日历、PDF 解析等 | 🟢 P2 | 4d |
| **M3.5** | **技能审核流** — 发布前安全审核 + 依赖检查 + 兼容性验证 | 🟢 P2 | 2d |
| **M3.2b** | **Skill Evolution Graph** — 技能演化 DAG 图谱可视化 | 🟢 P2 | 2d |
| **M3.6k** | **WebChat 适配器** — 基于 WebSocket 的 Web 聊天 UI | 🟢 P2 | 2d | M3.6a |
| **M3.6l** | ✅ **渠道配置架构** — ChannelConfigLoader + YAML ${VAR} 插值 + .env/频道分层 | 🟡 P1 | ✅ 完成 | M3.6a |
| **M3.6m** | **媒体处理** — 图片/文件/语音消息处理 | 🟢 P2 | 2d |
| **M3.13** | **测试覆盖率 > 85%** — 全模块覆盖，补充集成测试 | 🟡 P1 | 2d |

### 7.3 Phase 4（📋 v1.0.0 — 体验与差异化）

| 里程碑 | 功能 | 优先级 | 工作量 |
|:---|:---|:---:|:---:|
| **M4.1** | **Observability Dashboard** — 实时监控 Agent 状态、工具调用、记忆使用、渠道状态 | 🔴 P0 | 5d |
| **M4.2** | **结构化日志 + OpenTelemetry** — JSON 格式日志，Trace/Span 全链路追踪 | 🔴 P0 | 2d |
| **M4.4** | **Progressive Disclosure（F14）** — 3 级技能加载（core/standard/extended） | 🟡 P1 | 3d |
| **M4.5** | **条件激活技能（F15）** — fallback_for_toolsets / requires_toolsets 智能选择 | 🟡 P1 | 2d |
| **M4.5b** | **6 级技能加载优先级** — workspace > project > personal > managed > bundled > extra | 🟡 P1 | 1d |
| **M4.3** | **ACP/IDE 集成（F20）** — VS Code 插件（基础版） | 🟢 P2 | 4d |
| **M4.6** | **设备配对安全增强** — 签名挑战 v3，绑定 platform + deviceFamily | 🟢 P2 | 2d |
| **M4.7** | **工具权限审计** — 工具调用日志 + 权限变更审计 | 🟢 P2 | 1d |
| **M4.8** | **性能基准测试** — 8 项性能基准，CI 自动检测回归 | 🟡 P1 | 2d |
| **M4.9** | **Canvas 可视化（F21）** — A2UI 可编辑 HTML/CSS/JS 工作区 | 🟢 P3 | 5d |
| **M4.10** | **轨迹生成（F22）** — ShareGPT 格式训练数据导出 | 🟢 P3 | 2d |

### 7.4 Phase 5（📋 v1.1.0+ — 平台化）

| 方向 | 关键特性 |
|:---|:---|
| 多租户 | 租户隔离 + 配额管理 + 计费 |
| 技能市场 | 基于 Federated Skill Hub 的社区市场（发布/发现/安装/评分） |
| Agent 编排 | DAG 工作流 + 条件分支 + 并行执行 |
| 企业安全 | SSO/OIDC 集成 + 数据加密 + 合规审计 |
| 边缘部署 | 轻量运行时 + 本地模型 + 离线模式 |
| 多语言 SDK | TypeScript/Go/Rust 客户端库 |

---

## 8. 质量保障体系

### 8.1 代码质量门禁

| 检查项 | 工具 | 当前标准 | v1.0 目标 |
|:---|:---|:---|:---|
| 代码风格 | ruff | 0 errors | 0 errors |
| 类型检查 | mypy | 6 strict checks, 0 errors | 全量 strict, 0 errors |
| 单元测试 | pytest | 203 passed | 500+ passed |
| 覆盖率 | pytest-cov | ~65% | >90% |
| 集成测试 | pytest | 基础 | 完整覆盖 REST API + 渠道 |
| CI 流水线 | GitHub Actions | lint + typecheck + test + build | + security scan + perf bench |
| 性能回归 | 自建 | 无 | CI 自动检测 |

### 8.2 测试分层策略

```
┌──────────────────────────────────────────┐
│           E2E 测试（渠道接入 / 用户故事）   │
│         ┌────────────────────────────┐    │
│         │  集成测试（REST API / DB / ChromaDB）│
│         │  ┌──────────────────────┐  │    │
│         │  │  单元测试（每个模块）  │  │    │
│         │  │  · 纯函数测试        │  │    │
│         │  │  · Mock LLM 调用     │  │    │
│         │  │  · Mock 外部服务     │  │    │
│         │  └──────────────────────┘  │    │
│         └────────────────────────────┘    │
└──────────────────────────────────────────┘
```

### 8.3 代码审查清单

- [ ] 类型注解完整（无 `Any` 导入）
- [ ] 异常处理覆盖（使用项目异常类层次）
- [ ] 异步一致性（无同步阻塞调用）
- [ ] 测试覆盖新代码（目标 > 85%）
- [ ] 文档同步更新（PRD / architecture / CHANGELOG）
- [ ] 性能无回归（如有基准，自动检测）

---

## 9. 风险管理与应对

| 风险 | 概率 | 影响 | 应对策略 |
|:---|:---:|:---:|:---|
| MCP 协议生态不成熟，集成困难 | 中 | 高 | 先支持主流 MCP Server（filesystem/git/sqlite），渐进扩展 |
| 多渠道适配器维护成本高 | 高 | 中 | Channel Adapter SDK 标准化，每个适配器 <200 行；社区贡献模板 |
| asyncio 全链路迁移引入并发 bug | 中 | 高 | 渐进式迁移，每步加测试；保留同步回退接口 |
| ChromaDB 依赖升级不兼容 | 低 | 中 | 锁定版本范围；提供 JSON 回退存储 |
| litellm 上游 Breaking Change | 低 | 高 | 锁定主版本；CI 周度兼容性测试 |
| 测试覆盖率提升缓慢 | 中 | 低 | 新代码强制 >85% 覆盖率门禁；渐进补充旧代码 |
| 社区贡献质量参差 | 高 | 低 | CONTRIBUTING.md + CI 自动校验 + PR 模板 |

---

## 10. 成功标准与验收门禁

### 10.1 v1.0.0 发布门禁

| 门禁 | 标准 |
|:---|:---|
| 测试 | 500+ 用例全部通过，覆盖率 > 90% |
| 类型 | mypy 全量 strict，0 errors |
| 代码风格 | ruff 0 errors |
| 文档 | PRD / architecture / api-contract / data-model / deployment 完整且与代码一致 |
| 性能 | 8 项基准全部达标，无回归 |
| 安全 | DM 配对 + 工具权限审计 + 无高危依赖 |
| 渠道 | 6+ 渠道适配器可用 + Block Streaming |
| MCP | MCP 客户端支持 3+ MCP Server |
| Dashboard | Observability Dashboard 可部署 |
| 安装 | `pip install clawhermes` 一键安装，Docker 一键部署 |

### 10.2 各版本验收标准

| 版本 | 测试 | 覆盖率 | 新功能 | 文档 |
|:---|:---:|:---:|:---|:---:|
| v0.14.0 | 373 | 61% | MCP + 35 工具 + 全链路异步 | CHANGELOG + MCP 文档 |
| v0.15.0 | 420+ | >65% | Block Streaming + DM 配对 + QQ + 飞书 + 微信 | CHANGELOG + 渠道指南 |
| v0.16.0 | 450+ | >75% | QQ 适配器 + DM 配对 + Profile 隔离 | QQ 适配器文档 |
| v1.0.0 | 500+ | >90% | 全部 Phase 4 功能 | 完整文档集 |

---

## 11. 核心指标追踪表

### 11.1 能力指标

| 指标 | v0.14.0 | v0.15.0 实际 | v0.16.0 目标 | v1.0.0 目标 |
|:---|:---:|:---:|:---:|:---:|
| 内置工具数 | 35 | 35 | 45 | 50+ |
| MCP 工具 | 0 | ✅ | ✅ | ✅ | ✅ |
| 渠道适配器 | 3 | 6（CLI/REST/WS/飞书/微信/QQ） | 8 | 8+ |
| 测试用例 | 203 | 420+ | 500 | 500+ |
| 测试覆盖率 | 65% | 61% | 75% | 90%+ |
| Block Streaming | ❌ | ✅ | ✅ | ✅ |
| MCP 集成 | ❌ | ✅ | ✅ | ✅ | ✅ |
| Profile 隔离 | 3 级工具 | 3 级工具 | ✅ 完整 | ✅ 完整 | ✅ 完整 |
| Progressive Disclosure | ❌ | ❌ | ❌ | ❌ | ✅ |
| 条件激活技能 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 多模态记忆 | ❌ | ❌ | ❌ | ✅ | ✅ |
| Dashboard | ❌ | ❌ | ❌ | ❌ | ✅ |
| IDE 集成 | ❌ | ❌ | ❌ | ❌ | ✅ |
| DM 安全模型 | ❌ | ✅ | ✅ | ✅ |
| 结构化日志 | ❌ | ❌ | ❌ | ❌ | ✅ |

### 11.2 差异化优势追踪

| 差异化点 | v0.14.0 | Phase 3 目标 | v1.0.0 目标 |
|:---|:---|:---|:---|
| ACE 自适应压缩 | ✅ 基础版（4 种类型 + 规则分类） | LLM 辅助分类 | 迭代再压缩 |
| ChromaDB 向量记忆 | ✅ 文本向量（三者唯一） | — | 多模态向量 |
| Federated Skill Hub | ✅ Git 联邦 + SHA-256（去中心化） | + 审核流 | 社区市场 |
| Channel Adapter SDK | ✅ 标准化 ABC（三者唯一） | +6 适配器 | +8 适配器 |
| 纯 Python 零编译 | ✅ 核心优势 | 保持 | 保持 |
| asyncio 原生异步 | ✅ 全链路（chat_async + 并行全部 asyncio） | 保持 | 保持 |

---

> **本计划将随项目进展持续迭代。每个里程碑完成后回顾并修订下一阶段计划。**
>
> **当前焦点：Phase 3 v0.16.0 — Telegram / Discord / Slack 适配器 + Profile 隔离。**

---

## 附录 A：消息网关专项路线图

> ClawHermes 的消息网关定位：**SDK 驱动的可嵌入消息路由层**，而非 OpenClaw 式的全渠道平台。
> 核心策略：Channel Adapter SDK 标准化 → 少量高质量适配器 → 社区贡献长尾渠道。

### A.0 渠道适配器实现策略（多级优先级）

消息渠道适配器遵循**多级实现策略**，从复用已有实现到自主实现逐级降级，
优先利用现有生态，降低维护成本：

| 级别 | 策略 | 说明 | 示例 |
|:---:|:---|:---|:---|
| **1** | 🔍 **官方 SDK** | 优先查找并使用平台官方维护的 SDK（pip/npm/Maven） | 飞书 `lark-oapi`、微信 `wechatpy`、QQ 官方 Bot SDK |
| **2** | 🌐 **社区实现** | 无官方 SDK 或官方 SDK 不满足需求时，使用成熟社区项目 | Hermes 集成的飞书/QQ/微信 SDK |
| **3** | 📦 **Git 子仓库复刻** | 无可用社区实现时，新建 git 子仓库，参考官方 SDK 逻辑复刻 | `@larksuite/openclaw-lark`、`@tencent-weixin/openclaw-weixin-cli` |
| **4** | 🛠️ **裸 API 调用** | 无任何 SDK 可用时，新建 git 子仓库直接调用 REST/WebSocket API | 极少数新平台或冷门渠道 |

**决策流程**：

```
新渠道需求
    │
    ▼
┌─────────────────┐    有    ┌──────────────────┐
│ 1. 有官方 SDK？  │────────►│ pip install +     │
└────────┬────────┘         │ 封装 ChannelAdapter│
         │ 无                └──────────────────┘
         ▼
┌─────────────────┐    有    ┌──────────────────┐
│ 2. 有社区实现？   │────────►│ 引入依赖 +        │
└────────┬────────┘         │ 适配 ChannelAdapter│
         │ 无                └──────────────────┘
         ▼
┌─────────────────┐    可    ┌──────────────────┐
│ 3. 可复刻官方？   │────────►│ git submodule +   │
└────────┬────────┘         │ 复刻核心逻辑       │
         │ 不可              └──────────────────┘
         ▼
┌─────────────────┐         ┌──────────────────┐
│ 4. 裸 API 实现   │────────►│ git submodule +   │
└─────────────────┘         │ HTTP/WS 客户端    │
                            └──────────────────┘
```

**各渠道分级明细**：

| 渠道 | 实现级别 | SDK 来源 | Git 子仓库 | 备注 |
|:---|:---:|:---|:---|:---|
| **飞书** | ✅ 1 | `lark-oapi`（官方 SDK） | `clawhermes-lark` | ✅ v0.14.1 26 字段全部生效，权限门控 + Webhook 签名 + WS 可配 + 去重 LRU |
| **微信** | ✅ 1 | `wechatpy`（社区 SDK）+ 企微 Webhook | `clawhermes-weixin` | ✅ v0.14.1 个人微信长轮询 + 企微 Webhook 双模式 |
| **QQ** | 1 → 3 | QQ Bot 官方 API | `clawhermes-qq` | 官方仅提供 HTTP API，复用 Hermes QQ SDK 逻辑 |
| **Telegram** | 1 | `python-telegram-bot`（社区） | — | 社区 SDK 成熟稳定 |
| **Discord** | 1 | `discord.py`（社区） | — | 社区 SDK 成熟稳定 |
| **Slack** | 1 | `slack-bolt`（官方） | — | 官方 SDK 完善 |

> **子仓库命名规范**：`clawhermes-{platform}`，统一放在 `github.com/brekov/` 下，
> 通过 `git submodule` 或 `pip` extras 引入。

### A.1 当前状态（v0.15.0）

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
```

### A.2 与 OpenClaw 消息网关的架构对比

| 维度 | OpenClaw | ClawHermes（当前） | ClawHermes（v1.0 目标） |
|:---|:---|:---|:---|
| 渠道数 | 22+ 生产可用 | 3（CLI/REST/WS） | 8+ |
| 协议 | 自研 WebSocket（3 帧类型） | REST + WebSocket | REST + WebSocket + SSE |
| 消息队列 | steer/followup/collect/interrupt | ✅ 4 模式完整 | ✅ |
| Block Streaming | ✅ 完成即发送 | ✅ SSE v0.15.0 | ✅ |
| DM 配对安全 | ✅ 签名挑战 v3 | ❌ | ✅ v0.15.0 |
| 渠道热加载 | ✅ | ❌ | ✅ v0.16.0 |
| 媒体处理 | ✅ | ❌ | ✅ v0.16.0 |
| Dashboard | ✅ 渠道状态监控 | ❌ | ✅ Phase 4 |
| SDK 抽象 | ❌ 无标准化接口 | ✅ ChannelAdapter ABC | ✅ |
| Gateway 中心化 | ✅ 单一 Gateway 实例 | ✅ GatewayState 类 | ✅ + 连接池 |

### A.3 消息网关分阶段计划

#### Phase 3 中期（v0.14.0~v0.15.0）— 夯实地基 ✅ 已达成

| 任务 | 说明 | 优先级 |
|:---|:---|:---:|
| Channel Router 异步全链路 | `_on_message` 同步回调 → 完整 async/await 链路 | P0 |
| 消息可靠性 | 消息持久化到 SQLite（防丢失）+ 重试机制 | P0 |
| Gateway WebSocket 端点 | `/ws` 端点，真正双向实时推送 | P1 |
| **Block Streaming（SSE）** | ✅ `/chat/stream` SSE 端点，完成即发送，首字延迟 < 500ms（v0.15.0 已完成） | P1 |

#### Phase 3 后期（v0.16.0）— 渠道扩展

| 任务 | 说明 | 优先级 | 实现级别 |
|:---|:---|:---:|:---:|
| **Telegram 适配器** | 社区  → ChannelAdapter 封装 | P2 | 1 (社区 SDK) |
| **Discord 适配器** | 社区  → ChannelAdapter 封装 | P2 | 1 (社区 SDK) |
| **Slack 适配器** | 官方  → ChannelAdapter 封装 | P2 | 1 (官方 SDK) |
| ✅ **飞书适配器** | 分层架构 lark-oapi + Hermes vendor 消息引擎；WebSocket 长连接 + Token管理 + 媒体消息；clawhermes-lark 子仓库 | P0 | ✅ 完成 |
| ✅ **微信适配器** | clawhermes-weixin 子仓库 + wechatpy；ChannelAdapter + Gateway 集成 | P0 | ✅ 完成 |
| **QQ 适配器** | QQ Bot 官方 HTTP API + Hermes QQ SDK 逻辑复刻 | P1 | 3 (子仓库复刻) |
| **Telegram 适配器** | 社区 `python-telegram-bot` → ChannelAdapter 封装 | P2 | 1 (社区 SDK) |
| **Discord 适配器** | 社区 `discord.py` → ChannelAdapter 封装 | P2 | 1 (社区 SDK) |
| **Slack 适配器** | 官方 `slack-bolt` → ChannelAdapter 封装，Socket Mode | P2 | 1 (官方 SDK) |
| 渠道连接健康检查 | `health()` 方法，断线自动重连 | P2 | — |

#### Phase 3 收尾（v0.17.0）— 完善体验

| 任务 | 说明 | 优先级 |
|:---|:---|:---:|
| WebChat 适配器 | 基于 WebSocket 的 Web 聊天 UI | P2 |
| 渠道配置热加载 | YAML 变更自动检测 + 新渠道即插即用 | P2 |
| 媒体处理 | 图片/文件/语音消息的接收与响应 | P2 |
| 渠道消息统计 | 消息量/延迟/错误率埋点 | P2 |

#### Phase 4（v1.0.0）— 可观测 + 安全

| 任务 | 说明 | 优先级 |
|:---|:---|:---:|
| Dashboard 渠道面板 | 实时展示各渠道连接状态、消息吞吐、错误率 | P0 |
| 渠道权限审计 | 工具调用来源追踪 + 权限变更记录 | P1 |
| 签名挑战 v2 | 绑定 platform + deviceFamily + nonce | P2 |
| 多渠道消息广播 | 一条消息 → 多平台同步 | P3 |

### A.4 消息流完整路径（v1.0.0 目标）

```
外部平台                    ClawHermes Gateway                    Agent
─────────                  ──────────────────                    ─────

飞书 ────┐                ┌──────────────────┐
           │   WebSocket   │                  │
微信 ────┼──────────────►│  Channel Router  │
           │   Webhook     │                  │
QQ ──────┘                │  ┌────────────┐  │
                           │  │ DM 配对    │  │
                           │  │ 安全验证   │──┼──► allowlist 过滤
                           │  └────────────┘  │
                           │  ┌────────────┐  │
                           │  │ 消息队列    │  │
                           │  │ steer/     │  │
                           │  │ followup/  │──┼──► _process_queue()
                           │  │ collect/   │  │         │
                           │  │ interrupt  │  │         ▼
                           │  └────────────┘  │    Agent.chat()
                           │  ┌────────────┐  │         │
                           │  │Session     │  │         │
                           │  │ Router     │  │◄────────┘
                           │  │(channel+   │  │
                           │  │ chat_id →  │  │
                           │  │ session_id)│  │
                           │  └────────────┘  │
                           │                  │
                           │  ┌────────────┐  │
                           │  │Block       │  │
飞书 ◄───────────────────┼──│Streaming   │  │
微信 ◄───────────────────┼──│(SSE/chunk) │  │
QQ   ◄───────────────────┼──│            │  │
                           │  └────────────┘  │
                           └──────────────────┘
```

### A.5 渠道适配器实现模板

每个外部平台适配器只需实现 4 个方法（< 200 行）：

```python
from clawhermes.channel import ChannelAdapter, ChannelType, ChannelUser, ChannelMessage, ChannelResponse

class MyPlatformAdapter(ChannelAdapter):
    def __init__(self, config):
        super().__init__(ChannelType.CUSTOM, config)
        self._client = None  # 平台 SDK 客户端

    async def start(self) -> None:
        """启动：连接平台、注册 webhook / 开始 poll"""
        self._client = PlatformSDK(token=self.config["token"])
        self._client.on_message(self._on_platform_message)
        self._running = True

    async def stop(self) -> None:
        """停止：断开连接、清理资源"""
        await self._client.close()
        self._running = False

    async def send_response(self, response: ChannelResponse, original: ChannelMessage) -> None:
        """发送：将 Agent 回复推回平台"""
        chat_id = original.metadata.get("chat_id", original.user.user_id)
        await self._client.send_message(chat_id, response.content)

    async def get_user_info(self, user_id: str) -> ChannelUser | None:
        """用户信息：查询平台用户"""
        user = await self._client.get_user(user_id)
        return ChannelUser(user_id=user.id, display_name=user.name) if user else None

    def _on_platform_message(self, raw_msg) -> None:
        """内部：平台消息 → ChannelMessage → dispatch"""
        msg = ChannelMessage(
            message_id=raw_msg.id,
            channel_type=self.channel_type,
            user=ChannelUser(user_id=raw_msg.sender_id, display_name=raw_msg.sender_name),
            content=raw_msg.text,
            metadata={"chat_id": raw_msg.chat_id},
        )
        self._dispatch_message(msg)   # → ChannelRouter._on_message → 消息队列 → Agent
```
