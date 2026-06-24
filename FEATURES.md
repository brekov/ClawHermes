# ClawHermes · 完整功能介绍

> 版本：v0.15.0 | 源文件：31 个 + 3 个子仓库 | 测试：416/416 ✅
> GitHub：https://github.com/brekov/ClawHermes

---

## 一、Agent 核心能力

### 1.1 多 LLM 接入（F1）
通过 litellm 支持 **132 个 LLM Provider**，格式 `provider/model`：
- DeepSeek、OpenAI、Anthropic、Google Gemini、Groq、Ollama、vLLM、OpenRouter…
- 支持自定义 `base_url`（接入本地模型）
- 多凭证池（CredentialPool）：轮询/最少使用策略，401/429 故障冷却

### 1.2 思考-行动循环（F2）
- 系统提示 → LLM 调用 → 工具调度 → 结果合并 → 迭代/结束
- 默认 50 次迭代上限，可配置
- 7 个钩子点：`before_tool_call` / `after_tool_call` / `before_agent_reply` / `after_agent_end` / `before_agent_run` / `model_call_started` / `model_call_ended`
- 工具调用自动判断并行/串行
- 异步钩子支持，超时保护

### 1.3 Agent 身份设定
- 每个 Agent 独立的身份文件：`SOUL.md`（人格）、`AGENTS.md`（行为指令）、`USER.md`（用户信息）
- 启动时自动注入 SystemPrompt 的 StableLayer
- 三层 System Prompt：StableLayer + ContextLayer + VolatileLayer
- 多 Agent 管理：创建/列出/切换/查看/删除

### 1.4 上下文压缩（F10）+ ACE（F17）
- `ContextEngine` 抽象基类，可插拔
- `LLMCompressor`：LLM 摘要压缩，保护前 3 条 + 后 6 条消息
- `AdaptiveContextEngine`（ACE）：自动检测对话类型（代码/问答/创意/混合），选择最优压缩策略

### 1.5 子 Agent 委派（F12）
- `DelegateManager`：子 Agent 并行执行，防递归深度限制（MAX_DEPTH=2）
- 最大并发 3 个子 Agent

### 1.6 会话持久化（F5）
- `SessionManager`：SQLite WAL 模式，重启不丢失
- 会话 CRUD + 过期自动清理 + 消息历史持久化

### 1.7 异步接口（F13）
- `Agent.chat_async()` + `LLMProvider.chat_async()`
- 基于 litellm.acompletion
- **v0.14.0**：全链路 asyncio 原生，消除全部 `threading.Thread`

### 1.8 Block Streaming（M3.6c）✅
- `LLMProvider.chat_stream()` — litellm 流式封装 + 块缓冲（800-1200 chars）
- `Agent.chat_stream()` — 异步迭代器产出 SSE 事件
- `POST /chat/stream` SSE 端点 — `text/event-stream` + 首字延迟降低 50%+
- 事件类型：`text` | `tool_call` | `tool_result` | `error` | `done`

### 1.9 DM 配对安全（M3.6d）✅
- `POST /dm/pair/generate` — 生成配对码（8位，1小时有效）
- `POST /dm/pair/verify` — HMAC 挑战验证
- `GET /dm/pair/status` — 查询配对状态
- `GET /dm/pair/list` — 列出已配对用户
- `DELETE /dm/pair/{user_id}` — 撤销配对
- `ADMIN_KEY` 环境变量鉴权，管理员审批放行

---

## 二、工具系统（F3, F8, F9）

### 2.1 35 个内置工具（按 Profile 分级）

#### minimal（5 个）
| 工具 | 说明 |
|:---|:---|
| `session_status` / `read_file` / `write_file` / `exec` / `get_time` |

#### standard（9 个）— minimal + 4
| 工具 | 说明 |
|:---|:---|
| `web_search` / `memory_search` / `memory_save` / `delegate_task` |

#### full（35 个）— standard + 26
| 工具 | 说明 | 并行 |
|:---|:---|---:|
| `web_fetch` | 获取网页内容 | ✅ |
| `list_dir` | 列出目录内容 | ✅ |
| `grep` | 文件正则搜索 | ✅ |
| `patch_file` | 文件差异补丁 | — |
| `search_replace` | 文件搜索替换 | — |
| `code_eval` | Python 代码执行 | — |
| `compress_file` | gzip 压缩 | ✅ |
| `http_request` | HTTP GET/POST | — |
| `json_query` | JSON 路径查询 | — |
| `git_status` | Git 工作区状态 | ✅ |
| `git_diff` | Git 差异对比 | — |
| `git_log` | Git 提交记录 | ✅ |
| `env_list` | 环境变量（脱敏） | ✅ |
| `timer` | 定时器/秒表 | — |
| `url_encode` / `url_decode` | URL 编解码 | ✅ |
| `calc` | 安全数学计算 | ✅ |

| `sqlite_query` | 查询 SQLite 数据库 | — |
| `csv_parse` | 解析 CSV 文件 | ✅ |
| `hash_file` | 文件哈希 (md5/sha1/sha256) | ✅ |
| `disk_usage` | 磁盘使用情况 | ✅ |
| `base64_codec` | Base64 编解码 | ✅ |
| `process_list` | 系统进程列表 | ✅ |
| `image_info` | 图片信息 (Pillow) | ✅ |
| `pdf_extract` | PDF 文本提取 (pypdf) | — |
| `markdown_render` | Markdown → HTML | ✅ |

### 2.2 钩子系统（F8）
- 异步 handler 自动检测 + 超时保护（默认 10s）
- `trigger_async()` / `trigger_sync_with_async()` / `remove()`
- 工具级拦截、改写、阻止

### 2.3 工具策略（F9）
- 并行/串行调度，路径冲突检测
- 13 个并行安全工具 + 需确认工具

### 2.4 MCP 集成（F13）✨ 新增
- **MCPClient**：支持 stdio（子进程）和 HTTP 两种传输方式，JSON-RPC 2.0 协议
- **MCPRegistry**：管理多个 MCP Server 连接，自动发现工具并注册到 ToolRegistry
- **MCPServerSpec**：声明式 MCP Server 配置
- **Gateway 端点**：`POST /mcp/servers`、`GET /mcp/servers`、`DELETE /mcp/servers/{name}`

---

## 三、记忆系统（F4）

- **JSONMemoryProvider**：文件存储（零依赖）
- **ChromaMemoryProvider**：向量存储，语义搜索
- MemoryManager 多后端编排，按 importance 排序
- 作用域：`session` / `user` / `global`

---

## 四、技能系统（F6, F7, F19）

### 4.1 SkillManager（F6）
- 创建/读取/更新/删除技能，使用次数统计
- 技能上下文注入 SystemPrompt

### 4.2 Background Review（F7）
- 对话后自动审查，LLM 分析是否有值得记忆的内容
- 自动创建/更新技能，异步执行不阻塞主对话

### 4.3 Curator
- 定期检查（默认每 7 天），30 天未用 → stale，90 天 → 归档

### 4.4 Federated Skill Hub（F19）
- `SkillHub`：Git 仓库技能发布/安装/搜索
- `SkillManifest`：版本/校验和/签名/依赖元数据
- SHA-256 完整性验证，多仓库 failover

---

## 五、Gateway API（33 个端点）

### Agent 核心（12 个）
| 端点 | 方法 | 说明 |
|:---|:---:|:---|
| `/init` | POST | 初始化 Agent（支持 profile 参数） |
| `/chat` | POST | 对话（支持 session_id） |
| `/health` | GET | 健康检查 |
| `/tools` | GET | 工具列表 |
| `/memory/save` | POST | 保存记忆 |
| `/memory/search` | GET | 搜索记忆 |
| `/skills` | GET | 技能列表 |
| `/skills/create` | POST | 创建技能 |
| `/curator/run` | POST | 运行 Curator |
| `/sessions` | GET | 会话列表 |
| `/sessions/{id}` | GET | 会话详情 + 消息历史 |
| `/sessions/{id}` | DELETE | 删除会话 |

### Cron 调度（6 个）
| 端点 | 方法 | 说明 |
|:---|:---:|:---|
| `/cron/jobs` | POST | 创建定时任务 |
| `/cron/jobs` | GET | 列出任务 |
| `/cron/jobs/{id}` | GET | 任务详情 |
| `/cron/jobs/{id}` | DELETE | 删除任务 |
| `/cron/jobs/{id}/pause` | POST | 暂停 |
| `/cron/jobs/{id}/resume` | POST | 恢复 |

### Webhook 回调（4 个）
| 端点 | 方法 | 说明 |
|:---|:---:|:---|
| `/feishu/webhook` | POST | 飞书事件回调（需启用 clawhermes-lark） |
| `/wechat/webhook` | POST | 微信消息回调（需启用 clawhermes-weixin） |
| `/wecom/webhook` | POST | 企业微信消息回调（需启用 clawhermes-weixin） |
| `/qq/webhook` | POST | QQ 消息回调（需启用 clawhermes-qq） |

---

## 六、基础设施

### 6.1 Cron 调度器（F15）
- 零外部依赖（基于标准库 sched）
- 三种模式：cron / interval / oneshot
- JSON 持久化，重启不丢失

### 6.2 Docker 沙箱（F16）
- `DockerSandbox`：容器化安全执行，资源限制（内存/CPU/超时）
- `SandboxPool`：预热容器池，减少冷启动
- 支持 Python 代码 + Shell 命令

### 6.3 Channel Adapter SDK（F18）
- `ChannelAdapter` ABC + CLI/REST/WebSocket 内置适配器
- `ChannelManager` 统一管理，消息处理器注入
- 支持的渠道类型（配置模板见 `config/channels/`）：
  - CLI / REST / WebSocket — 已实现
  - 飞书（clawhermes-lark，lark-oapi 驱动）— 已实现
  - 微信 / 企业微信（clawhermes-weixin，wechatpy 驱动）— 已实现
- QQ（clawhermes-qq，QQ Bot API 驱动）— 已实现

### 6.4 异常体系（F14）
- `ClawHermesError` → 5 大类 17 子类
- SandboxError / ChannelError / ChannelConnectionError / ChannelMessageError 扩展异常

### 6.5 mypy 严格类型
- 6 项严格检查：warn_return_any / unused_ignores / redundant_casts / check_untyped_defs / no_implicit_optional / strict_equality
- 零 `typing.Any` 导入

---

## 七、CLI

```bash
clawhermes chat                       # 交互式对话
clawhermes chat --one-shot "问题"     # 一次性提问
clawhermes doctor                     # 系统诊断
clawhermes setup                      # 初始化配置
clawhermes gateway start              # 启动 Gateway
clawhermes config show                # 查看配置
clawhermes agent list                 # 列出 Agent
clawhermes agent create <name>        # 创建 Agent
clawhermes agent switch <name>        # 切换 Agent
clawhermes agent show [name]          # 查看 Agent
clawhermes agent set [name]          # 编辑 Agent 身份（默认当前 Agent）
```

### 8. 部署

```bash
# Docker
docker build -t clawhermes .
docker run -e DEEPSEEK_API_KEY=sk-xxx -p 18789:18789 clawhermes

# 直接运行
pip install -e .
export DEEPSEEK_API_KEY=sk-xxx
clawhermes gateway start --host 0.0.0.0

# 安装脚本
bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
```

### 9. 测试

- 416 个测试，全部通过 ✅
- ruff 0 errors | mypy 0 errors（6 strict checks）
- 覆盖率 73%（核心模块 > 80%）
- GitHub Actions CI：lint + typecheck + test + build
