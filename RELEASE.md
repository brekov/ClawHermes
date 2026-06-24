## 🏷️ 版本信息

| 项目 | 值 |
|:---|:---|
| 版本号 | v0.15.0 |
| 发布日期 | 2026-06-24 |
| 版本类型 | MINOR — Block Streaming + DM 配对 + QQ 适配器 |
| 语义化版本 | 0.15.0 |

## ✨ 新功能

### Block Streaming SSE（M3.6c）
- `POST /chat/stream` SSE 端点 — litellm 流式封装 + 块缓冲
- `Agent.chat_stream()` + `LLMProvider.chat_stream()`
- 事件类型：`text` | `tool_call` | `tool_result` | `error` | `done`
- 首字延迟降低 50%+

### DM 配对安全（M3.6d）
- 5 个新端点：`POST /dm/pair/generate`、`POST /dm/pair/verify`、`GET /dm/pair/status`、`GET /dm/pair/list`、`DELETE /dm/pair/{user_id}`
- `ADMIN_KEY` 环境变量鉴权，HMAC 挑战验证 + 管理员审批

### QQ Bot 渠道适配器（M3.6g）
- clawhermes-qq 子仓库：QQ Bot HTTP API + WebSocket 长连接
- `POST /qq/webhook` 端点
- 配置：`config/channels/qq.yaml.example`（`QQ_APP_ID` / `QQ_TOKEN` / `QQ_SECRET`）

### 端点计数修正（23 → 26）

上一版文档审计错误地将 3 个 webhook 端点标记为"缺失"并从文档中移除。经核实，`POST /feishu/webhook`、`POST /wechat/webhook`、`POST /wecom/webhook` 在 `gateway/app.py` 中实际存在且完整实现（含适配器检查 + 501/503 fallback）。

- 8 个文档中 23 → 26 端点：README、FEATURES、architecture、deployment、development、development-plan、PRD
- FEATURES.md 新增"Webhook 回调（3 个）"分类
- architecture.md 附录 A 补全 3 个 webhook 行
- development-plan.md 端点指标修正

### 渠道决策树"四级策略"措辞修正

全部文档中"四级实现策略"措辞与实际 5 级决策树不一致，统一改为"多级实现策略"：

- PRD §v0.10.0 决策块：四级 → 多级（官方 Agent SDK → 社区 Agent SDK → 复刻 → 官方其他 SDK → 裸 API）
- architecture.md §2.6 渠道适配器表、§3.6.1 标题
- comparison.md §3.9
- development-plan.md §A.0

### 渠道适配器实现级别修正

| 渠道 | 修正前 | 修正后 | 原因 |
|------|:---:|:---:|------|
| QQ | 3（复刻） | 2（社区 SDK: Hermes 集成） | Hermes 已有 QQ Bot SDK |
| Telegram | 1（社区 SDK） | 3（复刻 Hermes bot_telegram） | python-telegram-bot 非 Agent 专用 |
| Discord | 1（社区 SDK） | 4（社区 SDK） | discord.py 非 Agent 专用 |
| Slack | 1（官方 SDK） | 4（官方 SDK） | slack-bolt 非 Agent 专用 |

## ✨ 新功能

### 渠道决策树规格化（architecture.md §3.6.1）

重写为 5 级决策树，对齐项目渠道实现规范：

```
1. 有官方为Agent开发的SDK？ → git submodule + 适配  ← 首选（飞书 lark-oapi）
2. 有社区为Agent开发的SDK？ → git submodule + 适配  ← 次选（微信 wechatpy）
3. 可复刻官方Agent SDK？     → git submodule + 复刻  ← 三选（Telegram）
4. 有官方其他SDK？           → git submodule + 适配  ← 四选（Slack/Discord）
5. 裸API实现                  → git submodule + HTTP  ← 最后
```

- 新增**渠道优先级声明**：飞书 > 微信 > QQ（P0 国内生态优先）→ Telegram > Discord > Slack（P1 国际生态后续）
- §3.6.2 渠道状态图补全 P1 国际渠道说明

### FEATURES.md 渠道实现标注

- 飞书（clawhermes-lark，lark-oapi 驱动）— 已实现
- 微信 / 企业微信（clawhermes-weixin，wechatpy 驱动）— 已实现

## 📊 质量指标

| 指标 | v0.14.2 | v0.15.0 | 变化 |
|:---|:---|:---|:---|
| 测试用例 | 373 | 416 | +43 |
| 源文件 | 31 | 31 | — |
| 内置工具 | 35 | 35 | — |
| API 端点 | 26 | 33 | +7（5 DM 配对 + /chat/stream + /qq/webhook） |
| 渠道适配器 | 5 | 5 | — |
| ruff | 0 | 0 | ✅ |
| mypy | 0 | 0 | ✅ |

## 📝 文档更新

- **PRD.md**：定位描述 + 端点计数 + "四级→多级"措辞
- **architecture.md v2.1→v2.2**：端点 23→26、§3.6.1 决策树重写、渠道适配器级别修正、附录 A 补全
- **FEATURES.md**：端点 23→26、新增 Webhook 分类、飞书/微信已实现标注
- **README.md**：端点 23→26
- **deployment.md**：端点 23→26
- **development.md**：端点 23→26
- **development-plan.md**：端点 23→26、§A.0 四级→多级
- **comparison.md**：四级→多级

---

> **子仓库**：[clawhermes-lark](https://github.com/brekov/clawhermes-lark)（6,863 行）| [clawhermes-weixin](https://github.com/brekov/clawhermes-weixin)（308 行）

**Full Changelog**: https://github.com/brekov/ClawHermes/compare/v0.14.2...v0.15.0
