# ============================================
# ClawHermes 配置文件示例
# ============================================
#
# 运行时目录：~/.clawhermes/
#
# ~/.clawhermes/
# ├── config.yaml              ← 主配置（示例见 config.yaml.example）
# ├── default_agent.txt        ← 默认 Agent 名（如 "default"）
# ├── providers/
# │   └── deepseek.yaml        ← LLM Provider 配置（示例见 providers/）
# ├── agents/
# │   └── <name>/
# │       ├── SOUL.md           ← Agent 人格
# │       ├── AGENTS.md         ← 行为指令
# │       ├── USER.md           ← 用户信息
# │       └── config.json       ← Agent 配置
# ├── channels/
# │   ├── slack.yaml.example   ← 渠道配置（示例见 channels/）
# │   ├── feishu.yaml.example
# │   └── discord.yaml.example
# ├── skills/                  ← 技能文件目录
# └── sessions.db              ← SQLite 会话持久化
#
# 初始化：clawhermes setup
# 查看配置：clawhermes config show
