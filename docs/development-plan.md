# ClawHermes · 项目开发计划

> 版本：v1.1
> 日期：2026-06-16
> 状态：Phase 1 ✅ 已完成 | Phase 2 📋 规划中

---

## 一、竞争分析

### 1.1 Hermes Agent 深度研究

**技术架构：**
- 语言：Python，~3万行代码，80+模块
- 核心循环：conversation_loop.py 约3900行（单文件过大）
- 构造函数：60+参数（配置复杂）
- LLM接入：自实现统一接口，200+ Provider
- 自进化：Background Review + Curator 闭环
- 技能系统：SKILL.md 标准，agentskills.io Hub
- 调度：Cron 定时任务
- 用户建模：Honcho 个性化
- 终端：6种终端后端
- 迁移：OpenClaw 迁移工具

**市场定位：** 自进化 Agent 研究框架，面向研究者和高级开发者

**核心优势：**
1. 三层 System Prompt（Stable/Context/Volatile）— prefix cache 友好，省 token
2. Background Review + Curator 自进化闭环 — 越用越聪明
3. ContextEngine 可插拔设计 — 压缩策略可替换
4. CredentialPool 多凭证池 — 高可用，错误码感知冷却（401/429）
5. 200+ LLM Provider — 覆盖面最广
6. agentskills.io 技能市场 — 社区生态
7. Cron 调度 — 定时任务能力
8. Honcho 用户建模 — 个性化体验

**主要劣势：**
1. conversation_loop.py 3900行 — 维护困难
2. 60+ 构造参数 — 使用门槛高
3. GIL 限制 — 同步架构性能瓶颈
4. 无钩子拦截层 — 工具调用无审批机制
5. 无工具策略引擎 — 缺少权限控制
6. 配置无 fail-fast — 错误配置运行时才暴露
7. 无 Docker 支持 — 部署不便
8. 无健康检查 — 运维困难

### 1.2 OpenClaw 深度研究

**技术架构：**
- 语言：TypeScript (Node.js)，~50+子目录，编译链复杂
- 架构：Gateway 中心化 + 插件体系
- 消息渠道：22+ 渠道支持
- 工具系统：40+ 内置工具，tool profiles (minimal/coding/full)
- 钩子：before/after tool_call
- 技能市场：ClawHub
- 沙箱：Docker sandbox 执行
- Web UI：Dashboard 管理面板

**市场定位：** 生产级个人/团队 AI 助手，面向终端用户和团队

**核心优势：**
1. 22+ 消息渠道 — 覆盖所有主流平台
2. 40+ 内置工具 — 功能最完整
3. tool profiles (minimal/coding/full) — 场景化工具集
4. before/after tool_call 钩子 — 工具级拦截/审批/改写
5. ClawHub 技能市场 — 社区生态
6. Docker sandbox — 安全执行环境
7. Web Dashboard — 可视化管理
8. 配置 fail-fast — 不带病运行
9. 双层持久化 — 树形 transcript

**主要劣势：**
1. TypeScript 编译链 — 开发环境复杂
2. 钩子同步阻塞 — 影响性能
3. 配置爆炸 — 配置项过多
4. 无三层 Prompt — 每次重建，浪费 token
5. 无向量记忆 — 缺少语义搜索
6. 无自进化机制 — 不会越用越聪明
7. 无多凭证池 — 单凭证故障无转移

### 1.3 ClawHermes 现状评估

**已实现优势：**
- 纯 Python 零编译
- 三层 System Prompt（借鉴 Hermes）
- 双存储记忆（JSON + ChromaDB）
- 多凭证池（借鉴 Hermes）
- 自进化机制（Background Review + Curator）
- 钩子系统（借鉴 OpenClaw）
- Pydantic Settings 类型安全配置
- Docker + 一键安装

**关键差距：**
| 项目 | ClawHermes | OpenClaw | Hermes | 优先级 |
|------|-----------|----------|--------|--------|
| 内置工具数 | 9 | 40+ | 40+ | 🔴 高 |
| 工具 profiles | ❌ | ✅ | ❌ | 🟡 中 |
| 技能 Hub | ❌ | ClawHub | agentskills.io | 🟡 中 |
| Web UI | ❌ | Dashboard | ❌ | 🟢 低 |
| 消息渠道 | 0 | 22+ | 6 | 🟢 低 |
| 技能审核流 | ❌ | ✅ | ❌ | 🟡 中 |

**代码质量问题：**
1. 3个内置工具是存根（memory_search, memory_save, delegate_task）
2. Gateway `_auto_init()` 和 `initialize()` 代码重复
3. 宽泛的 `except Exception` 捕获，无自定义异常类层次
4. 4个声明依赖未使用（sqlalchemy, sqlite-utils, beautifulsoup4, markdownify）
5. `chat_async()` 方法是 TODO 存根
6. 会话存储为内存 dict，重启丢失
7. 无 CI 测试流水线
8. mypy strict=false，类型检查过于宽松

---

## 二、优势融合方案

### 2.1 取 Hermes 之长（8项）

| # | Hermes 优势 | 融合方案 | 当前状态 |
|---|------------|---------|---------|
| H1 | 三层 System Prompt | 已实现 StableLayer/ContextLayer/VolatileLayer | ✅ 已完成 |
| H2 | Background Review | 已实现 SkillManager + BackgroundReview | ✅ 已完成 |
| H3 | Curator 自动维护 | 已实现 7天/30天/90天 自动归档 | ✅ 已完成 |
| H4 | ContextEngine 可插拔 | 已实现 ABC + LLMCompressor + NoopCompressor | ✅ 已完成 |
| H5 | CredentialPool 多凭证 | 已实现 4种调度策略 + 错误码冷却 | ✅ 已完成 |
| H6 | 200+ LLM Provider | 通过 litellm 支持 132+ Provider | ✅ 已完成 |
| H7 | Cron 调度 | Phase 2 实现：APScheduler 集成 | 📋 Phase 2 |
| H8 | Honcho 用户建模 | Phase 3 实现：用户画像持久化 | 📋 Phase 3 |

### 2.2 取 OpenClaw 之长（9项）

| # | OpenClaw 优势 | 融合方案 | 当前状态 |
|---|-------------|---------|---------|
| O1 | before/after tool_call 钩子 | 已实现 HookManager 7个钩子点 | ✅ 已完成 |
| O2 | 工具策略引擎 | 已实现 allow/deny + 并行/串行调度 | ✅ 已完成 |
| O3 | tool profiles | Phase 1 实现：minimal/standard/full | 📋 Phase 1 |
| O4 | 40+ 内置工具 | Phase 1-2 扩展至 25+ | 📋 Phase 1-2 |
| O5 | 配置 fail-fast | 已实现 Pydantic field_validator | ✅ 已完成 |
| O6 | 双层持久化 | Phase 1 实现：SQLite + JSONL | 📋 Phase 1 |
| O7 | ClawHub 技能市场 | Phase 3 实现：Federated Skill Hub | 📋 Phase 3 |
| O8 | Docker sandbox | Phase 2 实现：容器化工具执行 | 📋 Phase 2 |
| O9 | Web Dashboard | Phase 4 实现：Observability Dashboard | 📋 Phase 4 |

---

## 三、劣势规避策略

### 3.1 规避 Hermes 短板（8项）

| # | Hermes 短板 | 规避方案 | 状态 |
|---|------------|---------|------|
| 1 | 循环 3900 行 | 拆分为小模块，单文件不超 500 行 | ✅ |
| 2 | 60+ 构造参数 | Pydantic Settings 类型化配置 | ✅ |
| 3 | GIL 限制 | asyncio 异步架构 | ✅ |
| 4 | 无钩子拦截 | HookManager 7个钩子点 | ✅ |
| 5 | 无工具策略 | allow/deny + 并行/串行调度 | ✅ |
| 6 | 配置无 fail-fast | field_validator fail-fast | ✅ |
| 7 | 无 Docker | Dockerfile + compose | ✅ |
| 8 | 无健康检查 | /health 端点 | ✅ |

### 3.2 规避 OpenClaw 短板（7项）

| # | OpenClaw 短板 | 规避方案 | 状态 |
|---|-------------|---------|------|
| 1 | TS 编译链 | 纯 Python，零编译 | ✅ |
| 2 | 钩子同步阻塞 | 异步钩子执行 | ⚠️ 基础版 |
| 3 | 配置爆炸 | 分组配置 + preset | ✅ |
| 4 | 无三层 Prompt | 三层架构 + stable 缓存 | ✅ |
| 5 | 无向量记忆 | ChromaDB 语义搜索 | ✅ |
| 6 | 无自进化 | Background Review + Curator | ✅ |
| 7 | 无多凭证池 | CredentialPool 4种策略 | ✅ |

### 3.3 规避 ClawHermes 自身短板（8项）

| # | 短板 | 规避方案 | 阶段 |
|---|------|---------|------|
| 1 | 3个存根工具 | 接入实际 MemoryManager/DelegateManager | Phase 1 |
| 2 | Gateway 代码重复 | 提取公共初始化方法 | Phase 1 |
| 3 | 无异常类层次 | 自定义 ClawHermesError 层次 | Phase 1 |
| 4 | 4个未用依赖 | 清理 pyproject.toml | Phase 1 |
| 5 | chat_async 存根 | 实现异步对话接口 | Phase 1 |
| 6 | 会话内存存储 | SQLite 持久化 | Phase 1 |
| 7 | 无 CI 流水线 | GitHub Actions CI | Phase 1 |
| 8 | mypy 过于宽松 | 逐步收紧 strict 模式 | Phase 1-2 |

---

## 四、创新功能设计

### 4.1 Adaptive Context Engine (ACE) — 自适应上下文引擎

**核心理念：** 根据对话类型自动选择最优压缩策略

- 代码对话 → 保留代码块，压缩闲聊
- 知识问答 → 保留引用，压缩推理过程
- 创意写作 → 保留风格描述，压缩技术细节
- 实现：ContextEngine ABC 新增 `detect_conversation_type()` 方法
- Phase 2 实现

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
- Phase 3 实现

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
- Phase 2 实现

### 4.8 Prompt Playground — 提示词实验场

**核心理念：** A/B 测试 System Prompt 效果

- 多版本 Prompt 并行测试
- 自动评估：响应质量 / 工具调用准确率 / token 效率
- Prompt 模板变量注入
- Phase 4 实现

---

## 五、分阶段开发路线图

### Phase 1: 代码质量与稳定性（v0.11.0）

**目标：** 修复已知问题，补齐核心功能，建立工程基础设施

**里程碑：**
| 里程碑 | 交付物 | 验收标准 |
|--------|--------|---------|
| M1.1 | 存根工具接入 | memory_search/memory_save/delegate_task 接入实际管理器 |
| M1.2 | 异常类层次 | ClawHermesError → LLMError/ToolError/MemoryError/ConfigError |
| M1.3 | Gateway 去重 | _auto_init() 与 initialize() 合并为单一方法 |
| M1.4 | 依赖清理 | 移除 4 个未用依赖 |
| M1.5 | chat_async 实现 | 异步对话接口完整可用 |
| M1.6 | 会话持久化 | SQLite 持久化，重启不丢失 |
| M1.7 | CI 流水线 | GitHub Actions: lint + typecheck + test |
| M1.8 | 工具 profiles | minimal(5)/standard(9)/full(15+) 三级工具集 |
| M1.9 | 内置工具扩展 | 新增 6+ 实用工具（web_fetch/list_dir/patch_file/grep/search_replace/code_eval） |
| M1.10 | 测试增强 | 测试用例从 56 增至 100+，覆盖率 > 80% |

**关键指标：**
- 测试用例：56 → 100+
- 测试覆盖率：~40% → > 80%
- 内置工具：9 → 15+
- 代码质量：0 个 ruff 错误，0 个 mypy 错误
- CI：全绿

### Phase 2: 功能增强与扩展（v0.12.0 - v0.13.0）

**目标：** 扩展工具生态，增强 Agent 能力

**里程碑：**
| 里程碑 | 交付物 | 验收标准 |
|--------|--------|---------|
| M2.1 | Channel Adapter SDK | ABC + 3个内置适配器(CLI/REST/WebSocket) |
| M2.2 | Cron 调度 | APScheduler 集成，支持定时/周期任务 |
| M2.3 | Docker Sandbox | 容器化工具执行环境 |
| M2.4 | ACE 自适应压缩 | 对话类型检测 + 策略自动切换 |
| M2.5 | 内置工具扩展至 25+ | 新增代码分析/数据处理/系统管理工具 |
| M2.6 | 异步钩子完善 | 全钩子点异步执行，超时保护 |
| M2.7 | mypy strict | 逐步收紧至 strict=true |

### Phase 3: 生态建设（v0.14.0 - v0.15.0）

**目标：** 建立技能生态，增强记忆与用户建模

**里程碑：**
| 里程碑 | 交付物 | 验收标准 |
|--------|--------|---------|
| M3.1 | Federated Skill Hub | Git-based 技能仓库 + 签名验证 |
| M3.2 | Skill Evolution Graph | DAG 技能演化图谱 |
| M3.3 | Multi-Modal Memory | 图片/代码/结构化记忆 |
| M3.4 | 用户画像持久化 | Honcho 式用户建模 |
| M3.5 | 技能审核流 | 提案→审批→发布流程 |
| M3.6 | 示例渠道适配器 | Slack/Discord/飞书适配器 |

### Phase 4: 体验与差异化（v1.0.0）

**目标：** 打造差异化竞争优势，发布 v1.0

**里程碑：**
| 里程碑 | 交付物 | 验收标准 |
|--------|--------|---------|
| M4.1 | Observability Dashboard | Web UI 实时监控 |
| M4.2 | Agent Workflow Builder | 可视化工作流编排 |
| M4.3 | Prompt Playground | A/B 测试 + 自动评估 |
| M4.4 | 性能优化 | 响应延迟 < 2s，内存 < 512MB |
| M4.5 | 文档完善 | API 文档 + 教程 + 示例 |
| M4.6 | v1.0.0 发布 | 全部功能验收通过 |

---

## 六、质量标准与测试流程

### 6.1 代码质量标准

| 指标 | 当前值 | Phase 1 目标 | v1.0 目标 |
|------|--------|-------------|----------|
| ruff lint 错误 | 0 | 0 | 0 |
| mypy 错误 | 未知 | 0 | 0 |
| 测试用例数 | 56 | 100+ | 200+ |
| 测试覆盖率 | ~40% | > 80% | > 90% |
| 单文件行数上限 | 300 | 500 | 500 |
| 文档覆盖率 | ~60% | > 80% | > 95% |

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

### 6.3 CI/CD 流水线

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  lint:     ruff check src/
  typecheck: mypy src/
  test:     pytest --cov=src/clawhermes --cov-fail-under=80
  build:    docker build -t clawhermes .
```

### 6.4 性能基准

| 指标 | 当前值 | v1.0 目标 |
|------|--------|----------|
| 首次响应延迟 | 未测 | < 3s |
| 工具调用延迟 | 未测 | < 1s |
| 记忆搜索延迟 | 未测 | < 200ms |
| 内存占用 | 未测 | < 512MB |
| 并发会话数 | 1 | 10+ |

### 6.5 发布门禁

每个版本发布前必须通过：
- [ ] 全部测试通过（0 失败）
- [ ] 覆盖率达标（Phase 1: 80%, v1.0: 90%）
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

### 7.2 Phase 1 任务分配

| 任务 | 负责人 | 优先级 | 依赖 |
|------|--------|--------|------|
| M1.1 存根工具接入 | 后端 | P0 | 无 |
| M1.2 异常类层次 | 后端 | P0 | 无 |
| M1.3 Gateway 去重 | 后端 | P1 | M1.2 |
| M1.4 依赖清理 | 基础设施 | P1 | 无 |
| M1.5 chat_async | 后端 | P1 | M1.2 |
| M1.6 会话持久化 | 后端 | P1 | M1.2 |
| M1.7 CI 流水线 | 基础设施 | P0 | 无 |
| M1.8 工具 profiles | 后端 | P1 | M1.1 |
| M1.9 内置工具扩展 | 后端 | P2 | M1.1 |
| M1.10 测试增强 | 测试 | P0 | M1.1-M1.9 |

---

## 八、v1.0 目标架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Observability Dashboard                    │
│              (Token追踪 / 工具热力图 / 记忆曲线)               │
├──────────────────────────────────────────────────────────────┤
│                    Channel Adapter SDK                        │
│           (CLI / REST / WebSocket / Slack / Discord)          │
├──────────────────────────────────────────────────────────────┤
│                      Gateway 层                               │
│          FastAPI REST + WebSocket + 事件推送                   │
├──────────────────────────────────────────────────────────────┤
│                      Agent 核心层                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ 三层Prompt  │ │ Agent Loop │ │ Workflow   │ │ Cron调度  │ │
│  │ (缓存友好)  │ │(Think-Act) │ │ Builder   │ │(APScheduler)│
│  └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ 工具系统    │ │ 记忆系统    │ │ 技能系统    │ │ 上下文引擎 │ │
│  │ 25+工具    │ │ 多模态记忆  │ │ 进化图谱    │ │ ACE自适应 │ │
│  │ profiles   │ │ 向量+关系   │ │ 联邦Hub    │ │ 智能压缩  │ │
│  │ 钩子+策略  │ │ 用户画像    │ │ 审核流     │ │           │ │
│  └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
├──────────────────────────────────────────────────────────────┤
│                      基础服务层                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐ │
│  │ LLM    │ │ 持久化  │ │ 凭证池 │ │ 沙箱   │ │ 会话管理  │ │
│  │132+Pro │ │SQLite+ │ │4策略   │ │Docker  │ │ 持久化    │ │
│  │viders  │ │ChromaDB│ │故障转移│ │Sandbox │ │           │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └───────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 九、关键指标对比

| 指标 | 当前 (v0.10.0) | Phase 1 (v0.11.0) | v1.0 目标 |
|------|---------------|-------------------|----------|
| 内置工具数 | 9 | 15+ | 25+ |
| 工具 profiles | 0 | 3 | 3+ |
| 测试用例 | 56 | 100+ | 200+ |
| 测试覆盖率 | ~40% | > 80% | > 90% |
| CI 流水线 | 无 | GitHub Actions | 完整 CI/CD |
| 会话持久化 | 内存 | SQLite | SQLite + Redis |
| 异常处理 | 宽泛 catch | 自定义层次 | 完整层次 |
| 异步支持 | 部分 | 完整 | 完整 |
| 技能 Hub | 无 | 无 | 联邦 Hub |
| Web UI | 无 | 无 | Dashboard |
| 文档覆盖率 | ~60% | > 80% | > 95% |

---

## 十、总结与行动建议

### 立即行动（Phase 1）

1. **修复存根工具** — memory_search/memory_save/delegate_task 接入实际管理器
2. **建立异常层次** — ClawHermesError → 子类
3. **清理依赖** — 移除未使用的 4 个依赖
4. **设置 CI** — GitHub Actions lint + typecheck + test
5. **实现 chat_async** — 异步对话接口
6. **会话持久化** — SQLite 存储
7. **工具 profiles** — minimal/standard/full
8. **扩展内置工具** — 新增 6+ 实用工具
9. **增强测试** — 覆盖率 > 80%

### 中期规划（Phase 2-3）

- Channel Adapter SDK + Cron 调度 + Docker Sandbox
- ACE 自适应压缩 + 异步钩子完善
- Federated Skill Hub + Skill Evolution Graph
- Multi-Modal Memory + 用户画像

### 远期愿景（Phase 4）

- Observability Dashboard
- Agent Workflow Builder
- Prompt Playground
- v1.0.0 正式发布
