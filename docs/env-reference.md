# ClawHermes · 环境变量参考

> 版本：v2.0
> 日期：2026-06-17
> 配置原则：**敏感值在 .env，操作配置在 YAML**（见 `docs/architecture.md` 渠道配置格式）

---

## 配置分层

```
.env                        ← 敏感值（API Key / Secret / Token）
config.yaml                 ← 主配置（非敏感）
channels/<name>.yaml        ← 渠道操作配置 + ${VAR} 引用 .env
```

YAML 中通过 `${FEISHU_APP_ID}` 语法引用环境变量，程序启动时自动注入。

---

## LLM Provider（选一个即可）

| 变量 | 说明 | 示例 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | `sk-xxx` |
| `DEEPSEEK_BASE_URL` | DeepSeek 自定义端点 | `https://api.deepseek.com` |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-xxx` |
| `GOOGLE_API_KEY` | Google AI API Key | `AIza...` |
| `ANTHROPIC_API_KEY` | Anthropic API Key | `sk-ant-...` |
| `CH_DEFAULT_MODEL` | 默认模型名 | `deepseek/deepseek-chat` |

## Gateway

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CH_GATEWAY_HOST` | 绑定地址 | `127.0.0.1` |
| `CH_GATEWAY_PORT` | 端口 | `18789` |
| `CH_GATEWAY_SECRET` | 非回环绑定时必须设置 | `""` |
| `CH_GW_API_KEY` | Gateway 自动初始化 API Key | — |
| `CH_GW_MODEL` | Gateway 自动初始化模型 | `deepseek/deepseek-chat` |
| `CH_TOOLS_PROFILE` | 工具集级别 | `standard` |

## 存储

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CH_DATA_DIR` | 数据目录 | `~/.clawhermes` |

## 渠道

### 飞书（Feishu / Lark）

需先安装子仓库：`pip install -e ./clawhermes-lark`

#### `.env` — 敏感值（密钥/Token）

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 事件订阅 Verification Token |
| `FEISHU_ENCRYPT_KEY` | 事件推送 Encrypt Key |
| `FEISHU_BOT_OPEN_ID` | Bot 的 open_id（可选，用于 @提及 匹配） |
| `FEISHU_BOT_USER_ID` | Bot 的 user_id（可选，tenant-scoped，需 contact 权限） |

#### `channels/feishu.yaml` — 操作配置（非敏感）

完整示例见 `config/channels/feishu.yaml.example`。

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `domain` | 平台域名 | `feishu` |
| `connection_mode` | 连接方式 | `websocket` |
| `bot_name` | Bot 显示名称 | `""` |
| `group_policy` | 群聊权限策略 | `allowlist` |
| `allowed_group_users` | 白名单/黑名单 open_id | `[]` |
| `admins` | 管理员 open_id | `[]` |
| `allow_bots` | Bot 消息过滤 | `none` |
| `require_mention` | 群聊 @提及门控 | `true` |
| `webhook_host` | Webhook 绑定地址 | `0.0.0.0` |
| `webhook_port` | Webhook 端口 | `8080` |
| `webhook_path` | Webhook 路径 | `/feishu/webhook` |
| `ws_reconnect_nonce` | 重连抖动上限（秒） | `30` |
| `ws_reconnect_interval` | 重连间隔（秒） | `120` |
| `ws_ping_interval` | 心跳间隔 | `null` |
| `ws_ping_timeout` | 心跳超时 | `null` |
| `log_level` | 日志级别 | `20` |
| `max_retries` | API 重试次数 | `3` |
| `retry_delay` | 重试基础延迟 | `1.0` |
| `dedup_cache_size` | 去重 LRU 容量 | `1024` |
| `reactions_enabled` | "正在输入"状态 | `true` |

> 环境变量可覆盖 YAML 配置（优先级：环境变量 > YAML > 默认值）
> 飞书 Webhook 由子仓库 `clawhermes-lark` 管理，路由在 Gateway 外部注册。

### 微信（WeChat / WeCom）

需先安装子仓库：`pip install -e ./clawhermes-weixin`

#### `.env` — 敏感值

| 变量 | 说明 |
|------|------|
| `WECHAT_SESSION_KEY` | 个人微信 iLink Bot session_key |
| `WECOM_BOT_KEY` | 企业微信机器人 Webhook Key |

#### `channels/wechat.yaml` — 操作配置

完整示例见 `config/channels/wechat.yaml.example`。

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `sub_type` | personal / enterprise | `personal` |

> 微信 Webhook 由子仓库 `clawhermes-weixin` 管理，路由在 Gateway 外部注册。

### QQ Bot

需先安装子仓库：`pip install -e ./clawhermes-qq`

#### `.env` — 敏感值

| 变量 | 说明 |
|------|------|
| `QQ_APP_ID` | QQ Bot AppID（uint64 string） |
| `QQ_TOKEN` | QQ Bot Token |
| `QQ_SECRET` | QQ Bot Secret（签名校验，可选） |

#### `channels/qq.yaml` — 操作配置

完整示例见 `config/channels/qq.yaml.example`。

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `sandbox` | 沙箱环境（true=沙箱, false=正式） | `true` |
| `auto_reconnect` | 断线自动重连 | `true` |
| `heartbeat_interval` | 心跳间隔（毫秒） | `40000` |
| `max_retries` | API 重试次数 | `3` |
| `retry_delay` | 重试基础延迟 | `1.0` |

#### DM 配对安全

| 变量 | 说明 |
|------|------|
| `ADMIN_KEY` | 管理员密钥，用于 DM 配对鉴权（必填，启用 DM 配对时） |

> QQ Webhook 由子仓库 `clawhermes-qq` 管理，路由在 Gateway 外部注册。

## 模型命名规则

通过 litellm 接入 132 个 provider，格式为 `provider/model`：

```bash
# 常用模型
deepseek/deepseek-chat
openai/gpt-4o
anthropic/claude-sonnet-4
gemini/gemini-2.5-pro
groq/llama-4
openrouter/anthropic/claude-sonnet-4
ollama/qwen2.5
```

完整 provider 列表见 [litellm 文档](https://docs.litellm.ai/docs/providers)。
