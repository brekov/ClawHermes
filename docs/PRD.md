# ClawHermes · 产品需求文档

> 版本：v0.1-draft
> 日期：2026-06-16
> 状态：设计阶段

---

## 1. 产品定位

**ClawHermes** 是一个 Python 实现的 AI Agent 框架，融合 Hermes Agent 的"自进化"能力和 OpenClaw 的"Gateway 中心化 + 插件钩子体系"，同时规避两者的工程短板。

### 核心价值主张

> "一个开箱即用、越用越聪明、可嵌入任何聊天渠道的 AI 助手框架"

### 目标用户

- 想拥有个人 AI 助理的开发者
- 需要团队级 AI 助手的团队
- 想研究 Agent 框架设计的学习者

---

## 2. 功能需求

### 2.1 核心能力

| # | 功能 | 优先级 | 来源 |
|---|------|--------|------|
| F1 | 多 LLM 提供商接入（OpenAI/DeepSeek/Anthropic/本地） | P0 | OpenClaw |
| F2 | 对话主循环（思考-行动） | P0 | 两者共有 |
| F3 | 工具系统（注册/调度/执行） | P0 | 两者共有 |
| F4 | 持久化记忆（跨会话） | P0 | Hermes |
| F5 | 多渠道消息网关 | P1 | OpenClaw |
| F6 | 技能系统（Skills） | P1 | Hermes |
| F7 | 自进化机制（Background Review） | P1 | Hermes |
| F8 | 工具钩子系统（before/after tool call） | P1 | OpenClaw |
| F9 | 工具策略引擎（profile + allow/deny） | P1 | OpenClaw |
| F10 | 上下文压缩 | P2 | 两者共有 |
| F11 | 多凭证池与故障转移 | P2 | Hermes |
| F12 | 子 Agent 委派 | P2 | Hermes |

### 2.2 非功能需求

| # | 要求 | 指标 |
|---|------|------|
| N1 | 可扩展性 | 新 LLM 提供商/新渠道/新工具均通过插件注册 |
| N2 | 安全性 | 密钥与配置分离，支持 SecretRef |
| N3 | 可靠性 | 配置校验 fail-fast，凭证故障自动转移 |
| N4 | 可观测性 | 关键路径有钩子暴露，支持耗时/用量监控 |
| N5 | 易用性 | 单命令 setup，配置文件有 schema 校验 |

---

## 3. 用户场景

### 场景一：个人助理
用户通过微信/Telegram 与 Agent 对话，Agent 能记住用户偏好，越用越了解用户。

### 场景二：代码助手
程序员在终端通过 CLI 与 Agent 交互，Agent 能够读写文件、执行命令、安装依赖、提交代码。

### 场景三：团队机器人
Agent 接入团队 Slack/Discord，成员可以 @Agent 提问、分配任务、查询信息。

---

## 4. 与 Hermes/OpenClaw 的差异

### 取 Hermes 之长
- 三层 System Prompt → 缓存友好，省 token
- Background Review → 对话后自动沉淀记忆/技能
- Curator → 技能库自动维护
- ContextEngine 可插拔 → 压缩策略可替换
- 多凭证池 → 高可用

### 取 OpenClaw 之长
- 插件钩子体系 → 工具级拦截/审批/改写
- 工具策略引擎 → 精细权限控制
- Gateway 统一控制面 → 多渠道一致性
- 双层持久化 → 树形 transcript
- 配置校验 fail-fast → 不带病运行

### 规避两者短板

| 短板 | 规避方案 |
|------|---------|
| Hermes conversation_loop.py 3900 行 | 按职责拆分为多个小模块，单文件不超过 500 行 |
| Hermes 60+ 构造参数 | 使用 Pydantic Settings 类型化配置，默认值覆盖 90% 场景 |
| Hermes 单进程 GIL 限制 | 异步架构 + asyncio，CPU 密集任务通过子进程委托 |
| OpenClaw TypeScript 编译链复杂 | 纯 Python，零编译步骤 |
| OpenClaw 插件钩子同步阻塞 | 钩子支持异步执行，可配置超时 |
| OpenClaw 配置项爆炸 | 分组配置，提供 preset（minimal/standard/full） |

---

## 5. 里程碑

| 阶段 | 产出 | 预计轮次 |
|------|------|---------|
| M1: 需求与架构 | PRD + 架构文档 + 技术选型 | 当前 |
| M2: 项目骨架 | 目录结构 + 配置 + CI + 核心类型 | 下一步 |
| M3: LLM + Agent 循环 | Provider 层 + 对话主循环 | 第三步 |
| M4: 工具系统 | 注册/钩子/策略/调度 | 第四步 |
| M5: 记忆 + 技能 | Memory + Skills + 自进化 | 第五步 |
| M6: Gateway | 消息网关 + 渠道接入 | 第六步 |
| M7: 测试 + 提交 | 单元测试 + GitHub | 收尾 |
