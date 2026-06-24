# ClawHermes

> 融合 **Hermes** 自进化能力与 **OpenClaw** Gateway 体系的 Python AI Agent 框架
> v0.15.0 · 31 个源文件 + 3 个子仓库 · 416 个测试 · 35 个工具 · 飞书/微信/QQ 渠道

---

<div>
  <a href="https://github.com/brekov/ClawHermes"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"></a>
  <img src="https://img.shields.io/badge/tests-373%2F373-brightgreen" alt="tests 416/416">
  <img src="https://img.shields.io/badge/coverage-73%25-yellow" alt="coverage 73%">
  <a href="https://github.com/brekov/ClawHermes/releases"><img src="https://img.shields.io/github/v/release/brekov/ClawHermes" alt="release v0.15.0"></a>
</div>

---

## 一、快速开始

```bash
pip install -e .
echo "DEEPSEEK_API_KEY=sk-xxx" >> .env
clawhermes chat
```

## 二、核心能力

| 模块 | 能力 |
|:---|:---|
| **Agent 核心** | 多 LLM 接入(132)、三层 Prompt、ACE 自适应压缩、子 Agent 委派、多 Agent |
| **工具系统** | 35 个内置工具、3 级 Profile、MCP 动态工具发现、MCP 动态工具、钩子系统(async + 超时)、并行/串行调度 |
| **记忆系统** | JSON + ChromaDB 双存储、语义搜索、跨会话持久化 |
| **技能系统** | SkillManager + Background Review(自进化) + Curator(维护) + SkillHub(发布) |
| **基础设施** | Cron 调度器、Docker 沙箱、Channel SDK + 飞书/微信/QQ 适配器、mypy 严格类型 |
| **渠道配置** | YAML ${VAR} 单一来源、权限门控、Webhook 签名校验、消息去重 LRU |

## 三、部署

```bash
# Docker
docker build -t clawhermes .
docker run -e DEEPSEEK_API_KEY=sk-xxx -p 18789:18789 clawhermes

# 一键安装
bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
```

## 四、设计理念

| 来自 **Hermes** | 来自 **OpenClaw** |
|:---|:---|
| 三层 System Prompt (缓存友好) | 插件钩子体系 (async + 超时保护) |
| Background Review (自进化) | 工具策略引擎 (精细权限) |
| ContextEngine 可插拔 | 配置校验 fail-fast |
| Curator (技能库维护) | |
| ACE 自适应压缩 | |
| Federated Skill Hub | |

## 五、文档

| 文档 | 说明 |
|:---|---:|
| [产品需求](PRD.md) | 功能需求与非功能需求（Phase 3 进行中） |
| [架构设计](architecture.md) | 系统架构与模块划分 |
| [开发计划](development-plan.md) | 竞争分析、路线图、质量标准 |
| [功能介绍](FEATURES.md) | 完整功能清单 |
| [数据模型](data-model.md) | 核心实体与字段规格 |
| [接口契约](api-contract.md) | 模块接口定义 |
| [部署指南](deployment.md) | Docker/裸机/一键部署 |
| [环境变量](env-reference.md) | 配置项参考 |
| [开发指南](development.md) | 开发环境与规范 |
| [对比分析](comparison.md) | ClawHermes vs OpenClaw vs Hermes |
| [变更日志](../CHANGELOG.md) | 版本记录 |
| [发布说明](../RELEASE.md) | 最新 Release |
| [贡献指南](../CONTRIBUTING.md) | 贡献方式与规范 |

---

*ClawHermes · 融合 Hermes 与 OpenClaw 的 AI Agent 框架 · v0.15.0 · MIT License*
