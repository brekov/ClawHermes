# ClawHermes · 完整功能介绍

> 版本：v0.10.0 | 代码：~2,700 行 | 测试：56/56 ✅
> GitHub：https://github.com/brekov/ClawHermes

---

## 一、Agent 核心能力

### 1.1 多 LLM 接入
通过 litellm 支持 **132 个 LLM Provider**，格式 `provider/model`：
- DeepSeek、OpenAI、Anthropic、Google Gemini、Groq、Ollama、vLLM、OpenRouter…
- 实测 DeepSeek 全链路可用
- 支持自定义 `base_url`（接入本地模型）

### 1.2 思考-行动循环（Agent Loop）
- 系统提示 → LLM 调用 → 工具调度 → 结果合并 → 迭代/结束
- 默认 50 次迭代上限，可配置
- `before_tool_call` / `after_tool_call` / `before_agent_reply` / `after_agent_end` 等 7 个钩子点
- 工具调用自动判断并行/串行

### 1.3 Agent 身份设定（SOUL.md / AGENTS.md / USER.md）
- 每个 Agent 独立的身份文件：`SOUL.md`（人格）、`AGENTS.md`（行为指令）、`USER.md`（用户信息）
- 启动时自动注入 SystemPrompt 的 StableLayer
- 交互式设定：`clawhermes agent set-persona`

### 1.4 多 Agent 管理
- `clawhermes agent create` — 创建/克隆 Agent
- `clawhermes agent list` — 列出所有 Agent
- `clawhermes agent show` — 查看 Agent 详情
- `clawhermes agent switch` — 切换默认 Agent
- `clawhermes agent delete` — 删除 Agent
- Gateway 自动读取当前默认 Agent

### 1.5 上下文压缩（F10）
- `ContextEngine` 抽象基类，可插拔
- `LLMCompressor`：LLM 摘要压缩，保护前 3 条 + 后 6 条消息
- 摘要预算控制（内容 × 20%，上限 12K tokens）
- Agent Loop 中自动触发

### 1.6 子 Agent 委派（F12）
- `DelegateManager`：子 Agent 并行执行
- 防递归深度限制（MAX_DEPTH=2）
- 子 Agent 禁用 `delegate_task` / `clarify` / `memory` / `exec`
- 最大并发 3 个子 Agent
- 支持暂停/恢复

---

## 二、工具系统

### 2.1 9 个内置工具

| 工具 | 说明 | 并行安全 |
|:---|:---|---:|
| `get_time` | 获取当前日期和时间 | ✅ |
| `web_search` | 搜索互联网信息 | ✅ |
| `memory_search` | 搜索记忆库 | ✅ |
| `read_file` | 读取文件内容 | ✅ |
| `session_status` | 会话状态信息 | ✅ |
| `write_file` | 写入文件（覆盖） | ❌ |
| `exec` | 执行 shell 命令 | ❌ |
| `memory_save` | 保存记忆 | ❌ |
| `delegate_task` | 委派子任务给子 Agent 并行执行 | ❌ |

### 2.2 工具注册机制
- `ToolRegistry`：自动注册 + 手动注册
- JSON Schema 自动生成（OpenAI-compatible）
- 工具分组（group），支持 profile 控制

### 2.3 工具调度
- `ToolDispatcher`：并行/串行规则引擎
- `NEVER_PARALLEL`：交互式工具（clarify）
- `PARALLEL_SAFE`：只读无状态工具
- `PATH_SCOPED`：路径不重叠可并行

### 2.4 钩子系统
- `HookManager`：注册/触发
- `before_tool_call`：可改写参数、阻止执行
- `after_tool_call`：可记录耗时
- `before_agent_reply`：可改写回复

---

## 三、记忆系统

### 3.1 双存储后端
- **JSONMemoryProvider**：文件存储，关键词搜索（零依赖）
- **ChromaMemoryProvider**：向量存储，语义搜索（自动嵌入）

### 3.2 MemoryManager
- 多 Provider 编排，保存时写入全部后端
- 搜索时从全部后端合并结果，按 importance 排序
- 快照生成（供 VolatileLayer 使用）

### 3.3 记忆属性
- 作用域：`session` / `user` / `global`
- 重要性评分：0~1
- 创建时间 / 元数据

---

## 四、技能系统

### 4.1 SkillManager
- 创建/读取/更新/删除技能
- 使用次数统计
- 最后使用时间追踪
- 技能上下文注入 SystemPrompt

### 4.2 Background Review（自进化核心）
- 对话后自动审查
- LLM 分析是否有值得记忆的内容
- 自动创建/更新技能
- 异步执行，不阻塞主对话

### 4.3 Curator（技能库维护）
- 定期检查（默认每 7 天）
- 30 天未用 → 标记 stale
- 90 天未用 → 归档（可恢复）
- 不动 bundled 技能

---

## 五、Gateway API（10 个 Agent 核心端点）

| 端点 | 方法 | 说明 |
|:---|:---:|:---|
| `/init` | POST | 初始化 Agent |
| `/chat` | POST | 对话 |
| `/health` | GET | 健康检查 |
| `/tools` | GET | 工具列表 |
| `/memory/save` | POST | 保存记忆 |
| `/memory/search` | GET | 搜索记忆 |
| `/skills` | GET | 技能列表 |
| `/skills/create` | POST | 创建技能 |
| `/curator/run` | POST | 运行 Curator 维护 |
| `/sessions` | GET | 会话列表 |

ClawHermes 通过 REST API 暴露 Agent 能力，消息渠道集成由部署者自行对接。

---

## 六、基础设施

### 6.1 配置管理
- Pydantic Settings 类型安全配置
- fail-fast 校验（上下文窗口 < 16K 拒绝启动）
- 环境变量 + .env 文件双加载
- 配置项分组（Agent / Gateway / Memory / Skills / Tools / Context）

### 6.2 LLM Provider
- 统一 `chat()` 接口
- 多凭证池（CredentialPool）：轮询/最少使用策略
- 错误码感知冷却（401→5min / 429→60min）
- 支持自定义 base_url

### 6.3 CLI
```bash
clawhermes chat                       # 交互式对话
clawhermes chat --one-shot "问题"     # 一次性提问
clawhermes doctor                     # 系统诊断
clawhermes setup                      # 初始化
clawhermes gateway start              # 启动 Gateway
clawhermes config show                # 查看配置
clawhermes config path                # 配置文件路径
clawhermes agent list                 # 列出 Agent
clawhermes agent create <name>        # 创建 Agent
clawhermes agent set-persona          # 设定身份
clawhermes agent switch <name>        # 切换 Agent
clawhermes agent show [name]          # 查看 Agent
```

### 6.4 部署

```bash
# Docker
docker build -t clawhermes .
docker run -e DEEPSEEK_API_KEY=sk-xxx -p 18789:18789 clawhermes

# 直接运行
pip install -e .
export DEEPSEEK_API_KEY=sk-xxx
clawhermes gateway start --host 0.0.0.0
```

---

## 七、文档体系（10 份）

| 文档 | 说明 | 版本 |
|:---|:---|---:|
| docs/PRD.md | 产品需求文档（含实现状态） | v2.0 |
| docs/architecture.md | 架构设计文档 | v2.0 |
| docs/data-model.md | 数据模型（6 实体 + 枚举） | v2.0 |
| docs/api-contract.md | 接口契约 | v2.0 |
| docs/sequence-diagrams.md | 关键流程时序图 | v2.0 |
| docs/deployment.md | 部署指南 | v2.0 |
| docs/env-reference.md | 环境变量手册 | v2.0 |
| docs/development.md | 开发指南 | v2.0 |
| CHANGELOG.md | 变更日志（v0.1~v0.10） | — |
| CONTRIBUTING.md | 贡献指南 | — |

---

## 八、测试

- 56 个单元测试（全部通过 ✅）
- MockProvider 不依赖真实 API
- 集成测试覆盖 Agent 循环、工具、记忆全链路
- 已通过真实 DeepSeek API 验证

## 九、关于消息渠道

ClawHermes **不内置**任何消息渠道适配器（飞书、微信、QQ、Telegram 等）。它是一个纯 AI Agent 框架，通过 REST API 暴露所有能力。消息渠道集成由部署者自行解决 —— 可配合 OpenClaw、自建 webhook、或任意前端。
