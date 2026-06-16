# Changelog

## v0.9.0 (2026-06-16)

配置体系重构 — 对齐 OpenClaw/Hermes

### 配置文件结构

```
~/.clawhermes/
├── config.yaml              # 主配置（agent/gateway/memory…）
├── channels/*.yaml          # 每个渠道独立文件
├── providers/*.yaml         # 每个 LLM Provider 独立文件
├── agents/<name>/           # 每个 Agent 独立目录
│   ├── SOUL.md / AGENTS.md / USER.md
└── skills/
```

### 新增

- `config.yaml` 主配置文件（`clawhermes config show/init/path`）
- 渠道配置从 channels.json 迁移到 `channels/*.yaml`，每个渠道独立文件
- LLM Provider 配置独立为 `providers/*.yaml`，增删 provider 不影响其他配置
- 对比分析文档 `docs/comparison.md`（ClawHermes vs OpenClaw vs Hermes）

### 变更

- Agent 设定文件对齐 OpenClaw/Hermes：`persona.md → SOUL.md`、`instructions.md → AGENTS.md`
- `gateway setup` 写入 `channels/<name>.yaml` 而非 channels.json
- 自动迁移旧版 channels.json
- `clawhermes setup` 自动生成 config.yaml

### 功能全景

| 模块 | 能力 |
|:---|:---|
| Agent 核心 | 多LLM接入(132)、三层Prompt、上下文压缩(F10)、子Agent委派(F12)、多Agent |
| 工具系统 | 9内置工具、钩子系统(before/after)、并行/串行调度、策略引擎 |
| 记忆系统 | JSON+ChromaDB双存储、语义搜索、跨会话持久化 |
| 技能系统 | SkillManager、Background Review(自进化)、Curator(自动维护) |
| 消息渠道 | 个人微信(扫码)、企业微信、飞书、QQ(OneBot)、Telegram、Webhook |
| 配置管理 | config.yaml主配置、channels/*.yaml、providers/*.yaml、.env密钥分离 |

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
- 渠道配置声明式（channels.json → 后改为 channels/*.yaml）

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
