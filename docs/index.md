# ClawHermes

> 融合 **Hermes** 自进化能力与 **OpenClaw** Gateway 体系的 Python AI Agent 框架
> 纯 Python，零外部依赖

---

<div style="display: flex; gap: 8px; flex-wrap: wrap;">
  <a href="https://github.com/brekov/ClawHermes"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"></a>
  <a href="docs/PRD.md"><img src="https://img.shields.io/badge/PRD-12%E2%81%8F12-green" alt="PRD 12/12"></a>
  <img src="https://img.shields.io/badge/tests-56%E2%81%8F56-brightgreen" alt="tests 56/56">
  <a href="https://github.com/brekov/ClawHermes/releases"><img src="https://img.shields.io/github/v/release/brekov/ClawHermes" alt="release"></a>
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
| **Agent 核心** | 多 LLM 接入(132个)、三层 Prompt、上下文压缩、子 Agent 委派、多 Agent |
| **工具系统** | 9 个内置工具、钩子系统(before/after)、并行/串行调度 |
| **记忆系统** | JSON + ChromaDB 双存储、语义搜索、跨会话持久化 |
| **技能系统** | SkillManager、Background Review(自进化)、Curator(自动维护) |
| **配置管理** | config.yaml 主配置、providers/*.yaml、.env 密钥分离 |

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
| 三层 System Prompt (缓存友好) | 插件钩子体系 (工具级拦截) |
| Background Review (自进化) | 工具策略引擎 (精细权限) |
| ContextEngine 可插拔 | 配置校验 fail-fast |
| Curator (技能库维护) | 双层持久化 (树形 transcript) |
| 多凭证池 (高可用) |  |

## 五、文档

| 文档 | 说明 |
|:---|---:|
| [产品需求](PRD.md) | 功能需求与非功能需求 |
| [架构设计](architecture.md) | 系统架构与模块划分 |
| [数据模型](data-model.md) | 核心实体与字段规格 |
| [接口契约](api-contract.md) | 模块接口定义 |
| [时序图](sequence-diagrams.md) | 关键流程 |
| [部署指南](deployment.md) | Docker/裸机部署 |
| [环境变量](env-reference.md) | 配置项参考 |
| [开发指南](development.md) | 开发环境与规范 |
| [对比分析](comparison.md) | ClawHermes vs OpenClaw vs Hermes |
| [开发计划](development-plan.md) | 竞争分析、路线图、质量标准 |
| [变更日志](changelog.md) | 版本记录 |

---

*ClawHermes · 融合 Hermes 与 OpenClaw 的 AI Agent 框架 · MIT License*
