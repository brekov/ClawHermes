# ClawHermes v0.15.0 — Release Notes (Draft)

> 发布日期：2026-06-23
> Tag: v0.15.0 (Draft)
> Phase 3 续：渠道适配器强化 + 文档审计修正

---

## 概览

v0.15.0 延续 Phase 3 渠道适配器建设，飞书 LarkConfig 26/26 字段全部生效，微信双模式完善，同时完成全项目文档审计与修正。
## 新增特性

| 里程碑 | 特性 | 说明 |
|:---:|------|------|
| M3.6l | **ChannelConfigLoader** | `channel/config.py`：YAML + ${VAR} 环境变量插值 + 内置默认值 |
| M3.6l | **配置分层** | `.env`（6 个密钥）→ ${VAR} 插值 → `channels/<name>.yaml` |
| M3.6e | **飞书权限门控** | 5 策略 + 白名单 + 管理员绕过 + Bot 过滤 + @提及门控 |
| M3.6e | **Webhook 签名** | SHA256 + hmac.compare_digest 时序安全校验 |
| M3.6e | **WS 重连可配** | `ws_reconnect_nonce/interval` 替换硬编码 5s；`ws_ping_interval/timeout` 注入 lark.ws.Client |
| M3.6e | **消息去重 LRU** | OrderedDict 限界去重（`dedup_cache_size` 可配） |
| M3.6e | **按 chat 串行锁** | 对齐 Hermes `_chat_locks`，1000 槽 LRU 驱逐 |

## Phase 3 续

| 里程碑 | 特性 | 说明 |
|:---:|------|------|
| M3.6e | **飞书适配器强化** | LarkConfig 26/26 字段全部生效（+15 死字段操作逻辑） |
| M3.6l | **配置架构重构** | 环境变量裸读 → YAML + ${VAR} 单一来源 |

## 质量指标

| 指标 | v0.14.0 | v0.14.1 | 变化 |
|------|:---:|:---:|:---:|
| 测试用例 | 373 | 373 | — |
| 源文件 | 30 | 31 | +config.py |
| 内置工具 | 35 | 35 | — |
| API 端点 | 18 | 23 | +channels +MCP |
| 渠道适配器 | 3 | 5 | +飞书 +微信 |
| .env FEISHU_ 变量 | 27 | 6 | -78% |
| ruff | 0 | 0 | ✅ |
| mypy | 0 | 0 | ✅ |

## 核心模块覆盖率

| 模块 | 覆盖率 |
|------|:---:|
| exceptions.py | 100% |
| ace.py | 97% |
| session.py | 96% |
| scheduler.py | 90% |
| channel/ | 87% |
| loop.py | 86% |
| memory.py | 85% |
| prompt.py | 83% |
| sandbox.py | 76% |

## 破坏性变更

无。`.env` 中已废弃的非敏感 FEISHU_* 操作变量自动被 YAML 内置默认值覆盖，无需手动迁移。

## 升级指南

```bash
git pull origin main --tags
git checkout v0.14.1
pip install -e .
pip install -e ./clawhermes-lark    # 飞书渠道
pip install -e ./clawhermes-weixin  # 微信渠道
```

新增环境变量（仅敏感值）：

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 事件订阅令牌 |
| `FEISHU_ENCRYPT_KEY` | 推送加密密钥 |

## Gateway 端点 (23 个)

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| POST | `/init` | 初始化 Agent |
| POST | `/chat` | 对话 |
| GET | `/health` | 健康检查 |
| GET | `/tools` | 工具列表 |
| POST | `/memory/save` | 保存记忆 |
| GET | `/memory/search` | 搜索记忆 |
| GET | `/skills` | 技能列表 |
| POST | `/skills/create` | 创建技能 |
| POST | `/curator/run` | 运行 Curator |
| GET | `/sessions` | 会话列表 |
| GET | `/sessions/{id}` | 会话详情 |
| DELETE | `/sessions/{id}` | 删除会话 |
| POST | `/cron/jobs` | 创建调度任务 |
| GET | `/cron/jobs` | 列出调度任务 |
| GET | `/cron/jobs/{id}` | 任务详情 |
| DELETE | `/cron/jobs/{id}` | 删除任务 |
| POST | `/cron/jobs/{id}/pause` | 暂停 |
| POST | `/cron/jobs/{id}/resume` | 恢复 |
| GET | `/channels` | 渠道列表 |
| GET | `/channels/sessions` | 渠道会话 |
| POST | `/mcp/servers` | MCP Server 注册 |
| GET | `/mcp/servers` | MCP Server 列表 |
| DELETE | `/mcp/servers/{name}` | 删除 MCP Server |
