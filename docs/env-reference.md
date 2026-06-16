# ClawHermes · 环境变量参考

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

## 存储

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CH_DATA_DIR` | 数据目录 | `~/.clawhermes` |

## 渠道

| 变量 | 说明 | 示例 |
|------|------|------|
| `FEISHU_APP_ID` / `LARK_APP_ID` | 飞书应用 ID | `cli_xxx` |
| `FEISHU_APP_SECRET` / `LARK_APP_SECRET` | 飞书应用 Secret | `xxx` |
| `CH_WECHAT_CORP_ID` | 企业微信 Corp ID | `wwxxx` |
| `CH_WECHAT_CORP_SECRET` | 企业微信 Corp Secret | `xxx` |
| `CH_WECHAT_AGENT_ID` | 企业微信应用 Agent ID | `1000001` |
| `CH_TG_BOT_TOKEN` | Telegram Bot Token | `xxx:xxx` |
| `CH_QQ_WS_URL` | go-cqhttp WebSocket 地址 | `ws://127.0.0.1:6700` |

## Channel Bridge

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CH_BRIDGE_PORT` | Bridge 端口 | `18788` |
| `CH_GATEWAY_URL` | ClawHermes Gateway 地址 | `http://127.0.0.1:18789` |

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
