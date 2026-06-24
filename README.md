# ClawHermes

融合 **Hermes** 自进化能力与 **OpenClaw** 钩子体系的 Python AI Agent 框架。

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests: 373 passed](https://img.shields.io/badge/tests-416%20passed-brightgreen)](tests/)
[![Coverage: 73%](https://img.shields.io/badge/coverage-73%25-yellow)](tests/)
[![Ruff](https://img.shields.io/badge/ruff-0%20errors-brightgreen)](pyproject.toml)
[![v0.15.0](https://img.shields.io/badge/version-0.15.0-blue)](CHANGELOG.md)

---

## 设计理念

| 来自 **Hermes**（自进化） | 来自 **OpenClaw**（Gateway + 钩子） |
|:---|:---|
| 三层 System Prompt → 缓存友好，省 token | 插件钩子体系 → 工具级拦截/改写/审批 |
| Background Review → 对话后自动沉淀记忆/技能 | 工具策略引擎 → profile + allow/deny 精细权限 |
| ContextEngine 可插拔 → 压缩策略可替换 | 配置校验 fail-fast → 不带病运行 |
| Curator → 技能库自动维护（stale→archived） | |
| 多凭证池 → 高可用（故障自动冷却） | |

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
docker run -e DEEPSEEK_API_KEY=sk-xxx -p 18789:18789 clawhermes
```

### HTTP API

```bash
# 初始化（可选指定工具 profile）
curl -X POST http://127.0.0.1:18789/init \
  -H "Content-Type: application/json" \
  -d '{"api_key":"sk-xxx","model":"deepseek/deepseek-chat","profile":"standard"}'

# 对话
curl -X POST http://127.0.0.1:18789/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好"}'

# 查看会话
curl http://127.0.0.1:18789/sessions
```

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                      Gateway 层（REST API）                   │
│  CLI / HTTP（FastAPI · 33 个 REST 端点 · Cron调度 · Docker沙箱 · MCP） │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│                    Agent 核心层                               │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │        三层 System Prompt (stable/context/volatile)    │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │          Agent Loop (思考-行动循环)                    │   │
│  │  LLM → 工具 → LLM → ... → 回复                        │   │
│  │  ← ACE 自适应压缩 ← ← ← ← (F17)                       │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │
│  │ 工具系统  │ │ 记忆系统  │ │ 技能系统  │ │ 子Agent委派  │    │
│  │ 35工具   │ │ JSON+    │ │ Manager+ │ │ 并行执行     │    │
│  │ 3级Profile│ │ ChromaDB │ │ Review+  │ │ 防死锁(F12)  │    │
│  │ 钩子+策略 │ │ 向量搜索  │ │ Curator  │ │              │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘    │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────┐  │
│  │ Cron调度 │ │ Docker  │ │   异常体系 (5大类10子类)      │  │
│  │ interval │ │ 沙箱执行 │ │   ClawHermesError → ...      │  │
│  │ cron一次 │ │ 资源隔离 │ │                              │  │
│  └──────────┘ └──────────┘ └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 功能全景

| # | 功能 | 说明 |
|:---:|:---|:---|
| F1 | **多 LLM 接入** | litellm 驱动，132 个 provider，`provider/model` 格式切换 |
| F2 | **对话主循环** | 思考-行动循环，50 次迭代上限，自动中断保护 |
| F3 | **工具系统** | 35 个内置工具，3 级 Profile，JSON Schema 生成 |
| F4 | **持久化记忆** | JSON 文件 + ChromaDB 双存储，语义搜索 |
| F5 | **会话持久化** | SQLite WAL 模式，重启不丢失，过期自动清理 |
| F6 | **技能系统** | SkillManager，元数据持久化，上下文注入 |
| F7 | **自进化** | Background Review，对话后自动审查沉淀记忆/技能 |
| F8 | **钩子系统** | 7 个钩子点（before/after tool_call、agent run/reply、model_call） |
| F9 | **工具策略** | 并行/串行调度，路径冲突检测，allow/deny 精细权限 |
| F10 | **上下文压缩** | ContextEngine 抽象，LLM 摘要，保护头尾 |
| F11 | **多凭证池** | 轮询/最少使用策略，401/429 故障冷却 |
| F12 | **子Agent委派** | 并行执行，深度限制(MAX=2)，防死锁 |
| F13 | **异步接口** | Agent.chat_async() + LLMProvider.chat_async() |
| F14 | **异常体系** | ClawHermesError → 5大类10子类，结构化错误信息 |
| F15 | **Cron 调度** | 标准库零依赖调度器，cron/interval/oneshot，JSON 持久化 |
| F16 | **Docker 沙箱** | 容器化安全执行，资源限制，网络隔离 |
| F17 | **ACE 自适应压缩** | 对话类型检测（代码/问答/创意），策略自动切换 |
| F18 | **Channel SDK** | 渠道适配器 ABC，内置 CLI/REST/WebSocket 适配器 |
| F19 | **Federated Skill Hub** | Git 仓库技能发布/安装/验证，SHA-256 校验 + GPG 签名 |

---

## 内置工具（35个）

### minimal（5个）— 轻量场景

| 工具 | 说明 | 可并行 |
|:---|:---|:----:|
| `get_time` | 获取当前日期和时间 | ✅ |
| `read_file` | 读取文件内容 | ✅ |
| `session_status` | 会话状态信息 | ✅ |
| `write_file` | 写入文件（覆盖） | ❌ |
| `exec` | 执行 shell 命令 | ❌ |

### standard（9个）— 默认

在 minimal 基础上增加：

| 工具 | 说明 | 可并行 |
|:---|:---|:----:|
| `web_search` | 搜索互联网信息 | ✅ |
| `memory_search` | 搜索记忆库 | ✅ |
| `memory_save` | 保存记忆 | ❌ |
| `delegate_task` | 委派子任务给子 Agent 并行执行 | ❌ |

### full（35个）— 完整能力

在 standard 基础上增加：

| 工具 | 说明 | 可并行 |
|:---|:---|:----:|
| `web_fetch` | 获取网页内容 | ✅ |
| `list_dir` | 列出目录内容 | ✅ |
| `grep` | 文件文本搜索 | ✅ |
| `patch_file` | 文件差异补丁 | ❌ |
| `search_replace` | 文件搜索替换 | ❌ |
| `code_eval` | 执行 Python 代码片段 | ❌ |
| `compress_file` | gzip 压缩文件 | ✅ |
| `http_request` | HTTP GET/POST 请求 | ❌ |
| `json_query` | JSON 路径查询提取 | ❌ |
| `git_status` | Git 工作区状态 | ✅ |
| `git_diff` | Git 差异对比 | ❌ |
| `git_log` | Git 提交记录 | ✅ |
| `env_list` | 环境变量列表（脱敏） | ✅ |
| `timer` | 定时器/秒表 | ❌ |
| `url_encode` | URL 编码 | ✅ |
| `url_decode` | URL 解码 | ✅ |
| `sqlite_query` | 查询 SQLite 数据库 | ❌ |
| `csv_parse` | 解析 CSV 文件 | ✅ |
| `hash_file` | 文件哈希 (md5/sha1/sha256) | ✅ |
| `disk_usage` | 磁盘使用情况 | ✅ |
| `base64_codec` | Base64 编解码 | ✅ |
| `process_list` | 系统进程列表 | ✅ |
| `image_info` | 图片信息 (需 Pillow) | ✅ |
| `pdf_extract` | PDF 文本提取 (需 pypdf) | ❌ |
| `markdown_render` | Markdown → HTML | ✅ |

配置方式：
```bash
export CH_TOOLS_PROFILE=full  # minimal / standard / full
```

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
│   └── provider.py         # LLM 调用封装 + CredentialPool + chat_async
│
├── agent/
│   ├── loop.py             # Agent 核心循环 + HookManager + ToolDispatcher
│   ├── prompt.py           # 三层 System Prompt
│   ├── memory.py           # 记忆系统（MemoryManager + JSONProvider）
│   ├── context.py          # F10: 上下文压缩引擎
│   ├── delegate.py         # F12: 子 Agent 委派
│   ├── exceptions.py       # 异常类层次（5大类10子类）
│   ├── session.py          # 会话持久化（SQLite WAL）
│   ├── scheduler.py        # 定时任务调度（cron/interval/oneshot）
│   ├── ace.py              # 自适应上下文引擎（代码/问答/创意）
│   └── agent_mgr.py        # 多 Agent 管理
│
├── channel/
│   ├── __init__.py         # Channel Adapter SDK
│   └── adapter.py          # 渠道适配器 ABC + CLI/REST/WebSocket 适配器
│
├── tools/
│   └── builtin.py          # 35 个内置工具 + 3 级 Profile
│
├── skills/
│   ├── manager.py          # 技能系统 + Background Review + Curator
│   └── hub.py              # 联邦技能中心（发布/安装/验证）
│
├── mcp/
│   ├── __init__.py           # MCP 集成
│   └── client.py             # MCP 客户端 (stdio + HTTP)
│
├── storage/
│   └── chroma_memory.py    # ChromaDB 向量记忆
│
└── gateway/
    ├── app.py              # FastAPI Gateway（33 个 REST 端点）
    └── setup.py            # Provider 配置管理
```

---

## 聊天渠道集成

> ClawHermes 的最终目标是支持多平台聊天渠道集成（飞书、微信、Discord、Slack、Telegram 等）。
>
> 目前已实现 **Channel Adapter SDK**（`src/clawhermes/channel/`），定义了标准化的渠道适配器接口，
> 并内置 CLI / REST / WebSocket 三个适配器。
>
> - ✅ **飞书**（clawhermes-lark · lark-oapi 驱动）
> - ✅ **微信**（clawhermes-weixin · wechatpy 驱动）
> - ✅ **QQ**（clawhermes-qq · QQ Bot API）
>
> 更多平台适配器（Telegram / Discord / Slack）将在 v0.16.0 中提供。
>
> - **Phase 2**：Channel Adapter SDK 完善 + 示例适配器（Slack / Discord / 飞书）
> - **Phase 3**：Federated Skill Hub + 社区适配器生态
>
> 如果你想为 ClawHermes 贡献渠道适配器，只需实现 `ChannelAdapter` ABC 的 4 个方法：
>
> ```python
> from clawhermes.channel import ChannelAdapter, ChannelType
>
> class MyChannelAdapter(ChannelAdapter):
>     async def start(self) -> None: ...
>     async def stop(self) -> None: ...
>     async def send_response(self, response, original) -> None: ...
>     async def get_user_info(self, user_id) -> ChannelUser | None: ...
> ```

---

## 测试

```bash
# 单元测试 + 集成测试（416 个测试，全部通过 ✅）
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=src/clawhermes --cov-report=term-missing

# 代码质量检查
ruff check src/
mypy src/
```

---

## 文档

| 文档 | 说明 |
|:---|:---|
| [PRD.md](docs/PRD.md) | 产品需求文档（Phase 1 ✅ 已完成） |
| [architecture.md](docs/architecture.md) | 架构设计文档（含 v1.0 目标架构） |
| [development-plan.md](docs/development-plan.md) | 开发计划（竞争分析 + 4阶段路线图） |
| [comparison.md](docs/comparison.md) | ClawHermes vs OpenClaw vs Hermes 对比 |
| [data-model.md](docs/data-model.md) | 数据模型（6实体+枚举） |
| [api-contract.md](docs/api-contract.md) | 接口契约（8模块） |
| [sequence-diagrams.md](docs/sequence-diagrams.md) | 5个关键流程时序图 |
| [deployment.md](docs/deployment.md) | 部署指南（Docker/裸机/一键） |
| [env-reference.md](docs/env-reference.md) | 环境变量手册 |
| [development.md](docs/development.md) | 开发指南 |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志（v0.1~v0.11） |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南 |

---

## 开发路线图

| Phase | 版本 | 目标 | 状态 |
|:------|:-----|:-----|:----:|
| Phase 1 | v0.11.0 | 代码质量与稳定性 | ✅ |
| Phase 2 | v0.12.0~v0.13.0 | 功能增强 | ✅（Channel SDK / Cron / Docker Sandbox / ACE） | ✅ |
| Phase 3 | v0.15.0 | 生态建设 + 异步化 | ✅（MCP / 异步化 / 工具35 / 测试357） | 🔄 |
| Phase 3 续 | v0.15.0~v0.16.0 | Block Streaming + DM 配对 + 飞书/微信/QQ 渠道 | ✅ / 🔄
| Phase 4 | v1.0.0 | 体验与差异化（Dashboard / Workflow Builder） | 📋 |

详见 [开发计划](docs/development-plan.md)

---

## License

MIT
