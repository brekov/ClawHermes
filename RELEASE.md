# ClawHermes v0.14.1 — Release Notes

> 发布日期：2026-06-23
> Tag: v0.14.1
> Phase 3 续：渠道配置架构重构 + 飞书适配器强化

---

## 概览

v0.14.1 聚焦渠道配置架构两大修复：(1) 配置从环境变量裸读重构为 YAML + ${VAR} 插值，
敏感值/操作配置严格分层；(2) 飞书适配器 LarkConfig 从 11 字段生效提升至 26/26 全部操作化，
权限门控、Webhook 签名、WS 重连等高级能力真正可用。

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
| API 端点 | 26 | 26 | — |
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

## 新增 API 端点

```
POST   /feishu/webhook     飞书消息事件回调
POST   /wechat/webhook     个人微信消息回调
POST   /wecom/webhook      企业微信消息回调
```
