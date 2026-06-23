# ClawHermes · 数据模型文档

> 版本：v2.2（新增 ChannelConfig 实体）
> 日期：2026-06-17

---

## 1. 核心实体关系

```
┌──────────┐    1:N    ┌───────────┐    1:N    ┌───────────┐
│  Session  │──────────▶│  Message   │──────────▶│ ToolCall  │
└──────────┘            └───────────┘            └───────────┘
     │                                                │
     │                                              1:1
     │                                                │
     │                                        ┌───────▼───────┐
     │                                        │   ToolResult  │
     │                                        └───────────────┘
     │
     │ 1:1
     │
┌────▼───────┐    1:N    ┌───────────┐
│  Agent      │──────────▶│  Memory   │
└────────────┘            └───────────┘
     │
     │ 1:1
     │
┌────▼───────┐    1:N    ┌───────────┐
│  SkillMgr   │──────────▶│   Skill   │
└────────────┘            └───────────┘
```

## 2. 核心数据模型

### 2.1 Session（会话）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `session_id` | string | PK, UUID | 全局唯一会话ID |
| `chat_id` | string | NOT NULL | 对话标识ID |
| `messages` | Message[] | | 会话消息列表 |
| `metadata` | dict | | 扩展属性（用户画像、标签等） |
| `token_count` | int | DEFAULT 0 | 累计token用量 |
| `created_at` | datetime | NOT NULL | 创建时间 |
| `updated_at` | datetime | NOT NULL | 最后活动时间 |

### 2.2 Message（消息）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | string | PK, UUID hex[:12] | 消息唯一ID |
| `role` | enum(MessageRole) | NOT NULL | SYSTEM/USER/ASSISTANT/TOOL |
| `content` | string | NOT NULL | 消息文本内容 |
| `tool_calls` | ToolCall[] | NULLABLE | 助手消息附带的工具调用 |
| `tool_call_id` | string | NULLABLE | 工具消息对应的调用ID |
| `name` | string | NULLABLE | 工具消息对应的工具名 |
| `timestamp` | datetime | NOT NULL | 消息时间戳 |

### 2.3 ToolCall（工具调用）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | string | PK | LLM返回的调用ID |
| `name` | string | NOT NULL | 工具名 |
| `args` | dict | NOT NULL | 调用参数（JSON） |
| `status` | enum | DEFAULT pending | pending/running/success/failed/blocked |
| `result` | any | NULLABLE | 执行结果 |
| `error` | string | NULLABLE | 错误信息 |
| `duration_ms` | float | DEFAULT 0 | 执行耗时 |

### 2.4 Memory（记忆）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | string | PK, UUID hex | 记忆唯一ID |
| `content` | string | NOT NULL | 记忆内容 |
| `scope` | enum(MemoryScope) | DEFAULT user | session/user/global |
| `importance` | float | [0, 1] | 重要性评分 |
| `metadata` | dict | | 扩展属性 |
| `embedding` | float[] | NULLABLE | 向量（ChromaDB自动生成） |
| `created_at` | datetime | NOT NULL | 创建时间 |

### 2.5 Skill（技能）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `name` | string | PK | 技能名（文件名） |
| `content` | string | NOT NULL | SKILL.md 内容 |
| `description` | string | DEFAULT "" | 技能描述 |
| `category` | string | DEFAULT general | 分类 |
| `version` | int | DEFAULT 1 | 版本号 |
| `usage_count` | int | DEFAULT 0 | 使用次数 |
| `last_used` | float | NULLABLE | 最后使用时间戳 |
| `status` | enum | DEFAULT active | active/stale/archived |
| `source` | enum | DEFAULT user | user/bundled/review |

### 2.6 SkillManifest（技能清单）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `name` | string | NOT NULL | 技能名称 |
| `version` | string | NOT NULL | 语义化版本（如 "1.0.0"） |
| `description` | string | NOT NULL | 技能描述 |
| `author` | string | NOT NULL | 作者 |
| `license` | string | DEFAULT "MIT" | 许可证 |
| `category` | string | NOT NULL | 分类标签 |
| `dependencies` | list[str] | DEFAULT [] | 依赖的其他技能 |
| `checksum` | string | NOT NULL | SHA-256 内容校验和 |
| `signature` | string | NOT NULL | GPG 数字签名 |

### 2.7 AgentConfig（Agent 配置）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | "clawhermes" | Agent名称 |
| `max_iterations` | int | 50 | 最大思考-行动轮次 |
| `max_tool_calls_per_round` | int | 10 | 单轮最大工具调用数 |
| `queue_mode` | enum | "steer" | 消息队列模式 |
| `context_window` | int | 64000 | 上下文窗口大小 |
| `compress_threshold` | float | 0.75 | 压缩触发阈值 |

### 2.8 CronJob（定时任务）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `job_id` | str | 自动生成 | 任务唯一标识 |
| `name` | str | — | 任务名称 |
| `spec` | ScheduleSpec | — | 调度规格（cron/interval/oneshot） |
| `task` | str | — | 任务内容（Agent 提示词） |
| `session_id` | str | "" | 关联的会话 ID |
| `status` | JobStatus | "pending" | 任务状态 |
| `created_at` | float | 当前时间 | 创建时间戳 |
| `last_run` | float | 0.0 | 最后执行时间戳 |
| `next_run` | float | 0.0 | 下次执行时间戳 |
| `run_count` | int | 0 | 已执行次数 |
| `error_count` | int | 0 | 失败次数 |
| `last_error` | str | "" | 最后错误信息 |

### 2.9 ChannelMessage（渠道消息）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `message_id` | str | — | 消息唯一标识 |
| `channel_type` | ChannelType | — | 渠道类型 |
| `user` | ChannelUser | — | 用户信息 |
| `content` | str | — | 消息内容 |
| `session_id` | str | "" | 关联的会话 ID |
| `reply_to` | str \| None | None | 回复的消息 ID |
| `metadata` | dict | {} | 额外元数据 |

### 2.10 ChannelUser（渠道用户）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | str | — | 用户唯一标识 |
| `display_name` | str | "" | 显示名称 |
| `metadata` | dict | {} | 额外元数据 |

## 3. 枚举定义

### MessageRole
```
SYSTEM = "system"      # 系统提示
USER = "user"          # 用户输入
ASSISTANT = "assistant" # 助手回复
TOOL = "tool"          # 工具结果
```

### ToolCallStatus
```
PENDING = "pending"    # 等待执行
RUNNING = "running"    # 执行中
SUCCESS = "success"    # 执行成功
FAILED = "failed"      # 执行失败
BLOCKED = "blocked"    # 被钩子阻止
```

### MemoryScope
```
SESSION = "session"    # 仅当前会话
USER = "user"          # 用户级（跨会话）
GLOBAL = "global"      # 全局
```

### QueueMode（来自 OpenClaw）
```
STEER = "steer"        # 注入当前轮次
FOLLOWUP = "followup"  # 排队等下一轮
COLLECT = "collect"    # 安静窗口后合并
INTERRUPT = "interrupt" # 中止当前执行
```

### ChannelType
```
CLI = "cli"            # 命令行
REST = "rest"          # REST API
WEBSOCKET = "websocket" # WebSocket
SLACK = "slack"        # Slack
DISCORD = "discord"    # Discord
FEISHU = "feishu"      # 飞书
WECHAT = "wechat"      # 微信
TELEGRAM = "telegram"  # Telegram
CUSTOM = "custom"      # 自定义渠道
```

### JobStatus
```
PENDING = "pending"    # 等待执行
RUNNING = "running"    # 执行中
COMPLETED = "completed" # 已完成
FAILED = "failed"      # 执行失败
PAUSED = "paused"      # 已暂停
CANCELLED = "cancelled" # 已取消
```
