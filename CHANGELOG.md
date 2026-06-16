# Changelog

## v0.6.0 (2026-06-16)

软件工程补全 + F10/F12

### 新增中间产物

- `docs/data-model.md` — 6个核心实体 + 字段规格 + 枚举
- `docs/api-contract.md` — 8大模块接口契约
- `docs/sequence-diagrams.md` — 6个关键流程时序图

### 新增功能模块

- **F10 上下文压缩**：ContextEngine 抽象基类 + LLMCompressor（LLM摘要，保护头尾消息）
- **F12 子Agent委派**：DelegateManager（并行执行，深度限制 MAX=2，防死锁）

### PRD 对齐
12 项功能全部实现。

## v0.5.0 (2026-06-16)

兼容层 — 复用 OpenClaw Node SDK

### 新增

- `scripts/channel-bridge.cjs` — Node.js 桥接服务
- 复用 `@tencent-weixin/openclaw-weixin` SDK 的 `sendMessageWeixin` 等发送函数
- 复用 `@larksuite/openclaw-lark` API，飞书 HTTP 直连

## v0.4.0 (2026-06-16)

三渠道对齐 OpenClaw/Hermes

### 新增

- `gateway/platforms/feishu.py` — 飞书适配器（lark-oapi WebSocket）
- `gateway/platforms/wechat.py` — 微信适配器（企业微信 + 公众号）
- `gateway/platforms/qq.py` — QQ 适配器（OneBot/go-cqhttp）
- Gateway 新增 9 个渠道 API 端点

## v0.3.0 (2026-06-16)

四大功能补齐

### 新增

- ChromaDB 向量检索（语义搜索记忆）
- 技能系统（SkillManager + 上下文注入）
- Background Review（对话后自动审查沉淀记忆/技能）
- Curator（30天 stale → 90天归档）
- 多渠道消息网关（Telegram + Webhook）

### Agent 改造

- Agent 注入 memory/skills 支持
- after_agent_end 钩子触发 Review

## v0.2.1 (2026-06-16)

经过真实 API 验证的稳定版本

### 修复

- pyproject.toml litellm 版本修正
- 全链路通过真实 DeepSeek API 验证

## v0.2.0 (2026-06-16)

可部署版本 — 常驻 Gateway + Docker

### 新增

- Gateway 常驻服务（FastAPI, 8 个 REST 端点）
- Dockerfile + docker-compose.yml + HEALTHCHECK
- 一键安装脚本 `scripts/install.sh`
- Gateway 自动初始化
- 56 个全链路测试

### 变更

- 默认绑定地址改为 127.0.0.1（更安全）

## v0.1.0 (2026-06-16)

首个生产版本

### 核心功能

- Agent 核心循环：思考-行动主循环
- 三层 System Prompt：stable/context/volatile
- 钩子系统：工具调用前后拦截
- 8 个内置工具：文件、命令、搜索、记忆
- 记忆系统：多 Provider，关键词检索
- 多凭证池：故障自动冷却

### 基础设施

- 类型安全配置（Pydantic Settings）
- CLI 交互（chat/setup/doctor）
- litellm 集成
- 完整测试套件
