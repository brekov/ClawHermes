# Changelog

## v0.10.0 (2026-06-16)

回归 Agent 框架本分 — 移除全部消息渠道代码

### 变更说明

> ClawHermes 不再是一个消息网关/Gateway，而是一个纯 Python AI Agent 框架，通过 REST API 暴露能力。
> 消息渠道集成（飞书、微信、QQ、Telegram 等）属于 OpenClaw 的范畴，两者分工明确。

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
