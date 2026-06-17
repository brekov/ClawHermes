# ClawHermes · 环境变量参考

> 版本：v2.0
> 日期：2026-06-16

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
