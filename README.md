# ClawHermes

融合 **Hermes** 自进化能力与 **OpenClaw** Gateway 体系的 Python AI Agent 框架。

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PRD 12/12](https://img.shields.io/badge/PRD-12%E2%81%8F12-green)](docs/PRD.md)
[![tests: 56](https://img.shields.io/badge/tests-56%E2%81%8F56-brightgreen)](tests/test_all.py)

---

## 设计理念

| 来自 **Hermes**（自进化） | 来自 **OpenClaw**（Gateway + 钩子） |
|:---|:---|
| 三层 System Prompt → 缓存友好，省 token | 插件钩子体系 → 工具级拦截/改写/审批 |
| Background Review → 对话后自动沉淀记忆/技能 | 工具策略引擎 → profile + allow/deny 精细权限 |
| ContextEngine 可插拔 → 压缩策略可替换 | Gateway 统一控制面 → 多渠道一致性体验 |
| Curator → 技能库自动维护（stale→archived） | 双层持久化 → 树形 transcript |
| 多凭证池 → 高可用（故障自动冷却） | 配置校验 fail-fast → 不带病运行 |

---

## 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配 API Key
echo "DEEPSEEK_API_KEY=sk-xxx" >> .env

# 3. 对话
clawhermes chat
```

### Docker 部署

```bash
docker build -t clawhermes .
docker run -e DEEPSEEK_API_KEY=sk-xxx \
  -e CH_CHANNEL_FEISHU_ENABLED=true \
  -e CH_CHANNEL_FEISHU_APP_ID=cli_xxx \
  -e CH_CHANNEL_FEISHU_APP_SECRET=xxx \
  -p 18789:18789 clawhermes
```

### HTTP API

```bash
# 对话
curl -X POST http://127.0.0.1:18789/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好"}'
```

### 配置渠道（声明式）

编辑 `.env`，Gateway 启动时自动连接：

```bash
# 飞书
CH_CHANNEL_FEISHU_ENABLED=true
CH_CHANNEL_FEISHU_APP_ID=cli_xxx
CH_CHANNEL_FEISHU_APP_SECRET=xxx

# 企业微信
CH_CHANNEL_WECHAT_ENABLED=true
CH_CHANNEL_WECHAT_CORP_ID=wwxxx
CH_CHANNEL_WECHAT_CORP_SECRET=xxx
CH_CHANNEL_WECHAT_AGENT_ID=1000001
```

---

## 架构

```
┌────────────────────────────────────────────────────────────┐
│                    Gateway 层                              │
│  CLI / HTTP / 飞书 / 微信 / QQ / Telegram / Webhook       │
└────────────────────────┬───────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────┐
│                  Agent 核心层                               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          三层 System Prompt (stable/context/volatile)│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │        Agent Loop (思考-行动循环)                    │   │
│  │  LLM → 工具 → LLM → ... → 回复                      │   │
│  │  ← 上下文压缩 ←  ←  ←  ← (F10)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ 工具系统  │ │ 记忆系统  │ │ 技能系统  │ │ 子Agent委派  │  │
│  │ 9工具+钩 │ │ JSON+    │ │ Manager+ │ │ 并行执行     │  │
│  │ 子+策略   │ │ ChromaDB │ │ Review+  │ │ 防死锁(F12)  │  │
│  │          │ │ 向量搜索  │ │ Curator  │ │              │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
└────────────────────────────────────────────────────────────┘
```

---

## 功能全景（PRD 12/12 ✅）

| # | 功能 | 说明 |
|:---:|:---|:---|
| F1 | **多 LLM 接入** | litellm 驱动，132 个 provider，`provider/model` 格式切换 |
| F2 | **对话主循环** | 思考-行动循环，50 次迭代上限，自动中断保护 |
| F3 | **工具系统** | 9 个内置工具，自动注册，JSON Schema 生成 |
| F4 | **持久化记忆** | JSON 文件 + ChromaDB 双存储，语义搜索 |
| F5 | **多渠道网关** | 飞书(WebSocket) / 微信(SDK桥接) / QQ(OneBot) / Telegram |
| F6 | **技能系统** | SkillManager，元数据持久化，上下文注入 |
| F7 | **自进化** | Background Review，对话后自动审查沉淀记忆/技能 |
| F8 | **钩子系统** | before/after tool call，before/after agent run |
| F9 | **工具策略** | 并行/串行调度，路径冲突检测 |
| F10 | **上下文压缩** | ContextEngine 抽象，LLM 摘要，保护头尾 |
| F11 | **多凭证池** | 轮询/最少使用策略，401/429 故障冷却 |
| F12 | **子Agent委派** | 并行执行，深度限制(MAX=2)，防死锁 |

---

## 内置工具（9个）

| 工具 | 说明 | 可并行 |
|:---|:---|:----:|
| `get_time` | 获取当前日期和时间 | ✅ |
| `web_search` | 搜索互联网信息 | ✅ |
| `memory_search` | 搜索记忆库 | ✅ |
| `read_file` | 读取文件内容 | ✅ |
| `session_status` | 会话状态信息 | ✅ |
| `write_file` | 写入文件（覆盖） | ❌ |
| `exec` | 执行 shell 命令 | ❌ |
| `memory_save` | 保存记忆 | ❌ |
| `delegate_task` | 委派子任务给子 Agent 并行执行 | ❌ |

---

## 支持模型

通过 litellm 支持 **132 个 LLM provider**，覆盖主流模型：

```python
LLMProvider(model="deepseek/deepseek-chat")       # DeepSeek
LLMProvider(model="openai/gpt-4o")                # OpenAI
LLMProvider(model="anthropic/claude-sonnet-4")    # Anthropic
LLMProvider(model="gemini/gemini-2.5-pro")        # Google
LLMProvider(model="groq/llama-4")                 # Groq
LLMProvider(model="openrouter/...")               # OpenRouter
LLMProvider(model="ollama/qwen2.5")               # 本地 Ollama
```

配置环境变量即可切换：`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY`

---

## 项目结构

```
src/clawhermes/
├── cli.py                  # CLI 入口（chat/gateway/setup/doctor）
├── config.py               # Pydantic 类型安全配置（fail-fast）
├── types.py                # 核心类型定义
│
├── llm/
│   └── provider.py         # LLM 调用封装 + CredentialPool
│
├── agent/
│   ├── loop.py             # Agent 核心循环 + HookManager + ToolDispatcher
│   ├── prompt.py           # 三层 System Prompt
│   ├── memory.py           # 记忆系统（MemoryManager + JSONProvider）
│   ├── context.py          # F10: 上下文压缩引擎
│   └── delegate.py         # F12: 子 Agent 委派
│
├── tools/
│   └── builtin.py          # 9 个内置工具
│
├── skills/
│   └── manager.py          # 技能系统 + Background Review + Curator
│
├── storage/
│   └── chroma_memory.py    # ChromaDB 向量记忆
│
└── gateway/
    ├── app.py              # FastAPI Gateway（16+ REST 端点）
    ├── channels.py         # 渠道抽象层（PlatformAdapter/GatewayManager）
    └── platforms/
        ├── feishu.py       # 飞书适配器
        ├── wechat.py       # 微信适配器（企微+公众号）
        └── qq.py           # QQ 适配器（OneBot）

scripts/
├── channel-bridge.cjs      # Node.js 兼容层（复用 OpenClaw SDK）
└── install.sh              # 一键安装脚本
```

---

## 测试

```bash
# 完整测试套件（56 个测试，全部通过 ✅）
python tests/test_all.py

# 集成测试（MockProvider，不需要 API Key）
python tests/test_integration.py
```

---

## 文档

| 文档 | 说明 | 状态 |
|:---|:---|---:|
| [PRD.md](docs/PRD.md) | 产品需求文档（含实现状态）| ✅ v1.0 |
| [architecture.md](docs/architecture.md) | 架构设计文档 | ✅ v1.0 |
| [data-model.md](docs/data-model.md) | 数据模型（6实体+枚举）| ✅ |
| [api-contract.md](docs/api-contract.md) | 接口契约（8模块）| ✅ |
| [sequence-diagrams.md](docs/sequence-diagrams.md) | 6个关键流程时序图 | ✅ |
| [deployment.md](docs/deployment.md) | 部署指南（Docker/裸机/一键）| ✅ |
| [env-reference.md](docs/env-reference.md) | 环境变量手册 | ✅ |
| [development.md](docs/development.md) | 开发指南 | ✅ |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志（v0.1~v0.6）| ✅ |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南 | ✅ |

---

## License

MIT
