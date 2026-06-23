# ClawHermes · 环境变量参考

> 版本：v2.0
> 日期：2026-06-17

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

需先安装子仓库：`git submodule update --init && pip install -e ./clawhermes-lark`

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FEISHU_APP_ID` | 飞书应用 App ID | —（不设置则不启用） |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret | — |
| `FEISHU_VERIFICATION_TOKEN` | 事件订阅 Verification Token | — |
| `FEISHU_ENCRYPT_KEY` | 事件推送 Encrypt Key | — |

> Webhook 端点：`POST /feishu/webhook`

### 微信（WeChat / WeCom）

需先安装子仓库：`git submodule update --init && pip install -e ./clawhermes-weixin`

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WECHAT_SESSION_KEY` | 个人微信 iLink Bot session_key | —（不设置则不启用） |
| `WECOM_BOT_KEY` | 企业微信机器人 Webhook Key | —（不设置则不启用） |

> Webhook 端点：`POST /wechat/webhook`、`POST /wecom/webhook`

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
