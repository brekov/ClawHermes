# ClawHermes

融合 Hermes 自进化能力与 OpenClaw Gateway 体系的 Python AI Agent 框架。

## 快速开始

```bash
# 安装
pip install -e .

# 初始化
clawhermes setup

# CLI 对话
clawhermes chat

# 启动 Gateway
clawhermes gateway
```

## 项目结构

```
src/clawhermes/
├── __init__.py
├── cli.py          # CLI 入口
├── config.py       # 类型安全配置
├── types.py        # 核心类型定义
├── agent/          # Agent 核心层
├── llm/            # LLM Provider 层
├── tools/          # 工具系统
├── gateway/        # 消息网关
├── storage/        # 持久化
└── api/            # REST API
```

## 设计理念

- **三层 System Prompt**: stable/context/volatile → 缓存友好
- **Background Review**: 对话后自动沉淀记忆/技能
- **插件钩子体系**: before/after tool call 拦截
- **工具策略引擎**: profile + allow/deny 精细控制
- **Gateway 统一控制面**: 多渠道一致性体验
