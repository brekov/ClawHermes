# ClawHermes v0.14.1 — Release Notes

> 发布日期：2026-06-23
> Tag: v0.14.1
> Phase 3 续：渠道配置架构重构 + 飞书适配器 15 死字段激活

---

## 概览

v0.14.1 修复渠道配置架构两个核心问题：(1) 配置架构从环境变量裸读改为 YAML ${VAR} 单一来源，对齐架构文档设计；
(2) 飞书适配器 LarkConfig 从 11/26 字段生效升级为 26/26 全部操作化，使权限门控、Webhook 签名、WS 重连、消息去重等配置真正生效。

## 新增特性

| 里程碑 | 特性 | 说明 |
|:---:|------|------|
| — | **ChannelConfigLoader** | `channel/config.py`：YAML + ${VAR} 环境变量插值，内置默认值 |
| — | **配置分层** | `.env`（6 个敏感值）→ ${VAR} 插值 → `channels/<name>.yaml` → `build_adapter_config()` |
| — | **飞书权限门控** | 5 策略（open/allowlist/blacklist/admin_only/disabled）+ 白名单 + 管理员绕过 + Bot 过滤 |
| — | **飞书 @提及匹配** | `bot_open_id` 精确匹配 + `bot_user_id` 回退，双重身份识别 |
| — | **Webhook 签名校验** | SHA256(timestamp+nonce+encrypt_key+body) + hmac.compare_digest 时序安全 |
| — | **WS 可配重连/心跳** | `ws_reconnect_nonce/interval` 替换硬编码 5s；`ws_ping_interval/timeout` 注入 lark.ws.Client |
| — | **消息去重 LRU** | OrderedDict 限界去重（`dedup_cache_size` 可配），对齐 Hermes `_seen_message_ids` |
| — | **按 chat 串行锁** | 对齐 Hermes `_chat_locks`，1000 槽 LRU 驱逐 |

## 死配置 → 生效

| LarkConfig 字段 | 实现 |
|:---|:---|
| `encrypt_key` | Webhook SHA256+HMAC 签名校验 |
| `bot_open_id` / `bot_user_id` | @提及双重匹配（open_id 首选，user_id 回退） |
| `bot_name` | `get_user_info()` Bot 自身查询 |
| `group_policy` | 5 策略门控 |
| `allowed_group_users` | 白/黑名单用户检查 |
| `admins` | 管理员绕过所有策略 |
| `allow_bots` | none/mentions/all 三档过滤 |
| `require_mention` | 群聊 @提及门控 |
| `ws_reconnect_nonce` / `ws_reconnect_interval` | 可配置重连策略 |
| `ws_ping_interval` / `ws_ping_timeout` | 注入 lark.ws.Client |
| `dedup_cache_size` | LRU 限界去重 |
| `reactions_enabled` | 反应事件开关 |

## 质量指标

| 指标 | v0.14.0 | v0.14.1 | 变化 |
|------|:---:|:---:|:---:|
| 测试用例 | 373 | 373 | — |
| 源文件 | 30 | 31 | +config.py |
| 内置工具 | 35 | 35 | — |
| API 端点 | 26 | 26 | — |
| 渠道适配器 | 3 | 5 | +飞书 +微信 |
| .env FEISHU_ 变量 | 27 | 6 | -78% |
| ruff | 0 | 0 | ✅ |
| mypy | 0 | 0 | ✅ |

## 子仓库

| 仓库 | 行数 | 说明 |
|:---|:---:|:---|
| [clawhermes-lark](https://github.com/brekov/clawhermes-lark) | 6,863 | 飞书适配器（lark-oapi + Hermes vendor 消息引擎） |
| [clawhermes-weixin](https://github.com/brekov/clawhermes-weixin) | 308 | 微信适配器（iLink Bot + 企微 Webhook） |

## 配置变更

| 变更 | 说明 |
|:---|:---|
| **新增** `channel/config.py` | YAML + ${VAR} 配置加载器 |
| **新增** `config/channels/feishu.yaml.example` | 26 字段完整操作配置 |
| **精简** `.env.example` | 27→6 个 FEISHU_ 变量（仅保留密钥） |
| **移除** app.py 27 处 `os.environ.get("FEISHU_*")` | 改为 `build_adapter_config("feishu")` 单调用 |

## 破坏性变更

无。`.env` 中已废弃的非敏感 FEISHU_* 操作变量自动被 YAML 内置默认值覆盖，无需手动迁移。

## 升级指南

```bash
git pull origin main --tags
git checkout v0.14.1
pip install -e .
pip install -e ./clawhermes-lark    # 飞书渠道
pip install -e ./clawhermes-weixin  # 微信渠道

# 渠道配置（可选）
cp config/channels/feishu.yaml.example ~/.clawhermes/channels/feishu.yaml
```
