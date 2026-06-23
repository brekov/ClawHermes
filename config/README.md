# ============================================
# ClawHermes 配置文件
# ============================================

## 配置分层原则

```
.env                        ← 纯敏感值（API Key / Secret / Token）
config.yaml                 ← 主配置（非敏感）
channels/<name>.yaml        ← 渠道操作配置 + ${VAR} 引用 .env 敏感值
```

设计依据：`docs/architecture.md` "渠道配置格式：YAML + 环境变量引用"

## 快速开始

```bash
# 1. 环境变量
cp config/.env.example .env
# 编辑 .env 填入 API Key 和渠道密钥

# 2. 渠道配置（可选，不配则从环境变量读取）
mkdir -p ~/.clawhermes/channels
cp config/channels/feishu.yaml.example ~/.clawhermes/channels/feishu.yaml
# 编辑 feishu.yaml 调整操作参数（策略/重连/去重等）

# 3. 初始化运行时目录
clawhermes setup
clawhermes config show
```

## 运行时目录

`~/.clawhermes/`（`clawhermes setup` 自动生成）：

```
~/.clawhermes/
├── config.yaml              ← 主配置（示例见 config.yaml.example）
├── providers/
│   └── deepseek.yaml        ← LLM Provider 配置
├── agents/<name>/
│   ├── SOUL.md              ← Agent 人格
│   ├── AGENTS.md            ← 行为指令
│   └── config.json          ← Agent 配置
├── channels/
│   ├── feishu.yaml          ← 飞书 P0 ✅（clawhermes-lark 子仓库）
│   ├── wechat.yaml          ← 微信/企微 P0 ✅（clawhermes-weixin 子仓库）
│   ├── slack.yaml           ← Slack P2（规划中）
│   └── discord.yaml         ← Discord P2（规划中）
├── skills/                  ← 技能文件目录
└── sessions.db              ← SQLite 会话持久化
```

## YAML 环境变量引用语法

```yaml
# feishu.yaml — 敏感值通过 ${VAR} 注入
app_id: "${FEISHU_APP_ID}"          # 从 .env 读取
app_secret: "${FEISHU_APP_SECRET}"  # 从 .env 读取

# 非敏感值直接写在 YAML
domain: feishu
group_policy: allowlist

# 带默认值（.env 未设置时使用默认值）
bot_name: "${FEISHU_BOT_NAME:-ClawHermes}"
```

## 配置优先级

```
环境变量 > YAML 文件 > 默认值
```

环境变量始终可以覆盖 YAML 中的任何值，保持向后兼容。
