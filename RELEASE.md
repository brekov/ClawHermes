# ClawHermes v0.14.1 — Release Notes

> 发布日期：2026-06-23
> Tag: v0.14.1
> Phase 3 续：渠道配置架构重构 + 飞书适配器强化

---

## 概览

v0.14.1 聚焦渠道配置架构两大修复：(1) 配置从环境变量裸读重构为 YAML + ${VAR} 插值，敏感值/操作配置严格分层；
(2) 飞书适配器 LarkConfig 从 11 字段生效提升至 26/26 全部操作化，权限门控、Webhook 签名、WS 重连等高级能力真正可用。

## 新增特性

| 里程碑 | 特性 | 说明 |
|:---:|------|------|
| M3.6l | **ChannelConfigLoader** | `channel/config.py`：YAML + ${VAR} 环境变量插值 + 内置默认值 |
| M3.6l | **配置分层** | `.env`（6 个密钥）→ ${VAR} 插值 → `channels/<name>.yaml` → `build_adapter_config()` |
| M3.6e | **飞书权限门控** | 5 策略（open/allowlist/blacklist/admin_only/disabled）+ 白名单 + 管理员绕过 + Bot 过滤 |
| M3.6e | **@提及匹配** | `bot_open_id` 精确匹配 + `bot_user_id` 回退，双重身份识别 |
| M3.6e | **Webhook 签名** | SHA256(timestamp+nonce+encrypt_key+body) + hmac.compare_digest 时序安全校验 |
| M3.6e | **WS 重连可配** | `ws_reconnect_nonce/interval` 替换硬编码 5s；`ws_ping_interval/timeout` 注入 lark.ws.Client |
| M3.6e | **消息去重 LRU** | OrderedDict 限界去重（`dedup_cache_size` 可配），对齐 Hermes `_seen_message_ids` |
| M3.6e | **按 chat 串行锁** | 对齐 Hermes `_chat_locks`，1000 槽 LRU 驱逐 |

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

渠道配置（可选）：

```bash
cp config/channels/feishu.yaml.example ~/.clawhermes/channels/feishu.yaml
```

新增环境变量（仅敏感值）：

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 事件订阅令牌 |
| `FEISHU_ENCRYPT_KEY` | 推送加密密钥 |

> 非敏感操作配置（domain、group_policy 等 20 项）移至 `channels/feishu.yaml`。详情见 `config/channels/feishu.yaml.example`。

## 子仓库

| 仓库 | 行数 | 说明 |
|------|:---:|------|
| [clawhermes-lark](https://github.com/brekov/clawhermes-lark) | 6,863 | 飞书适配器（lark-oapi + Hermes vendor 消息引擎 5,512 行） |
| [clawhermes-weixin](https://github.com/brekov/clawhermes-weixin) | 308 | 微信适配器（iLink Bot + 企微 Webhook） |
