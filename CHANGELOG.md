# Changelog

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
