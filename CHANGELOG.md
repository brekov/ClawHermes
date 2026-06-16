# Changelog

## v0.1.0 (2026-06-16)

首个生产版本发布。

### 核心功能

- **Agent 核心循环**：思考-行动主循环，支持多轮工具调用
- **三层 System Prompt**：stable/context/volatile 分层，缓存友好
- **钩子系统**：工具调用前后拦截、改写、审批
- **工具注册与调度**：自动注册，并行/串行规则引擎
- **8个内置工具**：文件读写、命令执行、时间日期、Web 搜索、记忆读写
- **记忆系统**：多 Provider 架构，JSON 文件存储，关键词检索
- **多凭证池**：轮询/最少使用策略，故障自动冷却

### 基础设施

- **类型安全配置**：Pydantic Settings，fail-fast 校验
- **CLI 交互**：`chat` / `setup` / `doctor` 命令
- **litellm 集成**：100+ LLM 模型统一接口
- **完整测试套件**：MockProvider 不依赖真实 API
