# ClawHermes vs OpenClaw vs Hermes 对比分析

> 日期：2026-06-16
> 说明：从架构设计、功能完整度、实现方式三个维度对比

---

## 一、概况

| 维度 | OpenClaw | Hermes Agent | ClawHermes |
|:---|:---|:---|:---|
| 语言 | TypeScript (Node.js) | Python | **Python** |
| 代码规模 | ~50+ 子目录，编译链复杂 | ~3 万行，80+ 模块 | ~4,400 行，23 模块 |
| 架构 | Gateway 中心化 + 插件 | Agent 核心 + 技能系统 | **Gateway + Agent + 插件** |
| 定位 | 生产级个人/团队 AI 助手 | 自进化 Agent 研究框架 | 融合两者设计的生产级框架 |
| GitHub Stars | 高 | 106k+ | 新项目 |
| 许可证 | MIT | MIT | MIT |

---

## 二、架构对比

### 2.1 整体架构

```
OpenClaw:         Gateway → Agent(单进程) → 22+渠道 / CLI / API
Hermes:           CLI → Agent → Skills → Memory → Gateway(多渠道)
ClawHermes:       Gateway → Agent → 工具/记忆/技能 → 6渠道 / CLI / API
```

### 2.2 System Prompt

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 分层设计 | ❌ 每次重建 | ✅ **三层(stable/context/volatile)** | ✅ 三层(借鉴 Hermes) |
| 缓存机制 | ❌ 无 | ✅ prefix cache 友好 | ✅ stable 层缓存 |
| 身份文件 | ✅ SOUL.md / AGENTS.md / USER.md | ✅ SOUL.md / AGENTS.md | ✅ SOUL.md / AGENTS.md / USER.md |
| 多 Agent | ✅ 多 workspace | ❌ 单 Agent | ✅ 多 Agent 目录 |

### 2.3 代码组织

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 主循环 | ~500 行 | **conversation_loop.py 3900 行** | loop.py ~300 行 |
| 构造函数参数 | 适中 | **60+ 参数** | ~10 参数（Pydantic 配置） |
| 模块拆分 | 50+ 子目录 | 80+ 模块 | 23 模块 |
| 编译 | TypeScript 编译 | 纯 Python | **纯 Python，零编译** |

---

## 三、功能对比

### 3.1 LLM 接入

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| Provider 数 | 20+ | 200+ | **132 (litellm)** |
| 统一接口 | 自实现 | 自实现 | ✅ litellm |
| 多凭证池 | ❌ 单凭证 | ✅ **CredentialPool** | ✅ CredentialPool(借鉴 Hermes) |
| 故障转移 | ❌ | ✅ 错误码感知冷却 | ✅ 401/429 冷却 |

### 3.2 Agent 核心

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 思考-行动循环 | ✅ | ✅ | ✅ |
| 迭代上限 | 可配置 | 默认 90 | 默认 50 |
| 子 Agent 委派 | ❌ | ✅ delegate_task | ✅ **DelegateManager(F12)** |
| 上下文压缩 | ✅ LLM 摘要 | ✅ ContextEngine 可插拔 | ✅ **LLMCompressor(F10)** |
| 中断保护 | ✅ | ✅ | ✅ |

### 3.3 工具系统

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 内置工具数 | 40+ | 40+ | **9 个** |
| 工具注册 | 自动发现 | 自动注册 | ToolDef 注册 |
| 工具分组 | ✅ tool groups | ✅ toolsets | ✅ group 字段 |
| 钩子系统 | ✅ **before/after tool call** | ❌ 无拦截层 | ✅ HookManager(借鉴 OpenClaw) |
| 工具策略 | ✅ **allow/deny/profile** | ❌ | ✅ 并行/串行调度 |
| 并行执行 | ✅ | ❌ 串行 | ✅ PARALLEL_SAFE 规则 |
| 工具 profiles | ✅ minimal/coding/full | ❌ | ❌ 未实现 |

### 3.4 记忆系统

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 持久化 | ✅ Session + Transcript | ✅ MemoryProvider | ✅ **双存储(JSON+ChromaDB)** |
| 向量检索 | ❌ | ❌ | ✅ **ChromaDB 语义搜索** |
| 关键词搜索 | ❌ | ❌ | ✅ JSON 文件 |
| 记忆快照 | ❌ | ✅ volatile 层注入 | ✅ snapshot() |
| 跨会话记忆 | ✅ | ✅ | ✅ |

### 3.5 技能 / 自进化

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 技能系统 | ✅ **Skill Workshop** | ✅ SKILL.md 标准 | ✅ SkillManager |
| Background Review | ❌ | ✅ **自进化核心** | ✅ Background Review(借鉴 Hermes) |
| Curator 维护 | ❌ | ✅ 7 天自动归档 | ✅ Curator(stale→archived) |
| 技能 Hub | ✅ ClawHub | ✅ agentskills.io | ❌ 未实现 |
| 技能审核流 | ✅ 提案→审批 | ❌ 直接写入 | ❌ 直接写入 |

### 3.6 消息网关

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 总渠道数 | **22+** | 6 | **6** |
| 微信(个人) | ✅ 插件 | ❌ | ✅ **扫码登录**(复用 OpenClaw SDK) |
| 企业微信 | ✅ 插件 | ❌ | ✅ 扫码 + corp secret |
| 飞书 | ✅ 插件 | ❌ | ✅ lark-oapi WebSocket |
| QQ | ✅ 插件 | ❌ | ✅ OneBot/go-cqhttp |
| Telegram | ✅ 插件 | ✅ | ✅ 长轮询 |
| Discord | ✅ 插件 | ✅ | ❌ |
| Slack | ✅ 插件 | ✅ | ❌ |
| Signal | ✅ 插件 | ✅ | ❌ |
| Email | ❌ | ✅ | ❌ |
| 渠道统一抽象 | ✅ BasePlatformAdapter | ❌ | ✅ **PlatformAdapter** |
| 配置方式 | **config 声明式** | config 文件 | **gateway setup 交互式** |

### 3.7 多 Agent

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| 多 Agent | ✅ **多 workspace** | ❌ 单 Agent | ✅ 多 Agent 目录 |
| 身份设定 | ✅ SOUL.md/AGENTS.md/USER.md | ✅ SOUL.md/AGENTS.md | ✅ SOUL.md/AGENTS.md/USER.md |
| 交互式设定 | ❌ 手动编辑 | ❌ | ✅ **clawhermes agent set-persona** |
| Agent 切换 | ✅ workspace 切换 | ❌ | ✅ clawhermes agent switch |

### 3.8 部署

| 特性 | OpenClaw | Hermes | ClawHermes |
|:---|:---|:---|:---|
| Docker | ✅ | ❌ | ✅ **Dockerfile + compose** |
| 一键安装 | ❌ | ✅ install.sh | ✅ **install.sh** |
| 健康检查 | ✅ | ❌ | ✅ **/health** |
| WEB UI | ✅ Dashboard | ❌ | ❌ |
| 后台常驻 | ✅ Gateway | ✅ Gateway | ✅ Gateway |

---

## 四、实现差异总结

### 4.1 ClawHermes 做得好的

| 项目 | 说明 |
|:---|:---|
| **纯 Python 零编译** | 比 OpenClaw 的 TS 编译链简单得多 |
| **分层 Prompt 缓存** | 借鉴 Hermes 的三层设计，OpenClaw 没有 |
| **双存储记忆** | JSON + ChromaDB，OpenClaw 和 Hermes 都只有单一存储 |
| **多凭证池** | Hermes 有，OpenClaw 没有 |
| **自进化** | 借鉴 Hermes 的 Background Review + Curator |
| **钩子系统** | 借鉴 OpenClaw，Hermes 没有 |
| **渠道声明式配置** | 对齐 OpenClaw 的设计理念 |
| **微信扫码登录** | 复用 OpenClaw 的 ilink 协议，Hermes 不支持微信 |
| **Agent 身份设定** | 三者都对齐（SOUL.md/AGENTS.md/USER.md） |

### 4.2 ClawHermes 不足的

| 项目 | 说明 | 优先级 |
|:---|:---|:---:|
| **内置工具太少** | 9 个 vs OpenClaw 40+ | 🔴 高 |
| **渠道数太少** | 6 个 vs OpenClaw 22+ | 🔴 高 |
| **工具 profiles** | OpenClaw 的 minimal/coding/full 未实现 | 🟡 中 |
| **技能 Hub** | OpenClaw 有 ClawHub，Hermes 有 agentskills.io | 🟡 中 |
| **技能审核流** | OpenClaw 有提案→审批流程 | 🟡 中 |
| **WEB UI** | OpenClaw 有管理面板 | 🟢 低 |
| **Discord/Slack** | Hermes 和 OpenClaw 都支持 | 🟢 低 |
| **并行执行深度** | 子 Agent 默认最多 3 并发 | 🟢 低 |

### 4.3 三者都没有的

| 项目 | 说明 |
|:---|:---|
| **完善的 CLI Agent 配置向导** | ClawHermes 的 `agent set-persona` 是独创 |
| **ChromaDB 向量记忆** | 三个项目中唯一实现语义搜索的 |
| **微信扫码一键配置** | 只有 ClawHermes 支持（复用 OpenClaw 协议） |

---

## 五、定位总结

```
OpenClaw:    最成熟的 Gateway + 最多渠道 → 生产首选
Hermes:      最强的自进化学习闭环 → 研究/学习
ClawHermes:  融合两者设计 + Python 纯原生 → 轻量级替代
```

**一句话：** ClawHermes 在核心能力上对齐了 OpenClaw 和 Hermes 的设计精华，在工具数量和渠道数量上还有明显差距，但在 Python 生态、向量记忆、扫码配置等方面有自己的优势。
