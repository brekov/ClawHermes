# ClawHermes v0.12.0 — Release Notes

> 发布日期：2026-06-17
> Tag: v0.12.0
> Phase 2: 功能增强与扩展

---

## 概览

v0.12.0 完成 Phase 2 全部 7 个里程碑，并启动了 Phase 3 的 M3.1 Skill Hub。
新增 Channel SDK、Cron 调度、Docker 沙箱、ACE 自适应引擎、11 个新工具、异步钩子、
mypy selective strict、SkillHub（技能发布/安装/验证）。

## 新增特性

| 里程碑 | 特性 | 说明 |
|:---:|------|------|
| M2.1 | **Channel Adapter SDK** | ChannelAdapter ABC + CLI/REST/WebSocket 适配器 + ChannelManager |
| M2.2 | **Cron 调度器** | 标准库 sched 零依赖，cron/interval/oneshot，JSON 持久化，6 个 API 端点 |
| M2.3 | **Docker Sandbox** | 容器化安全执行，Python + Shell，资源限制，SandboxPool 预热 |
| M2.4 | **ACE 自适应引擎** | 对话类型检测（code/qa/creative/mixed），策略自动选择 |
| M2.5 | **工具扩展** | 15 → 26 个内置工具（compress_file/http_request/git_status/calc 等） |
| M2.6 | **异步钩子** | async handler + 超时保护 + trigger_async / trigger_sync_with_async |
| M2.7 | **mypy strict** | 6 项严格检查，零 `typing.Any`，`assert isinstance()` 运行时守卫 |

## Phase 3 启动

| 里程碑 | 特性 | 说明 |
|:---:|------|------|
| M3.1 | **Federated Skill Hub** | SkillManifest + SkillHub，Git 仓库技能发布/安装/验证，SHA-256 校验 + GPG 签名 |

## 质量指标

| 指标 | v0.11.0 | v0.12.0 | 变化 |
|------|:---:|:---:|:---:|
| 测试用例 | 73 | 152 | +108% |
| 覆盖率 | 57% | 67% | +10pp |
| 源文件 | 18 | 24 | +33% |
| 内置工具 | 15 | 26 | +73% |
| API 端点 | 13 | 18 | +38% |
| 渠道适配器 | 0 | 3 | — |
| ruff | 0 | 0 | ✅ |
| mypy | 0 (loose) | 0 (6 strict) | ✅ |

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

无。v0.11.0 → v0.12.0 完全向后兼容。

## 升级指南

```bash
git pull origin main --tags
git checkout v0.12.0
pip install -e .
```

新增环境变量：

| 变量 | 说明 |
|------|------|
| `CH_GW_API_KEY` | Gateway 自动初始化 API Key |
| `CH_GW_MODEL` | Gateway 自动初始化模型 |
| `CH_TOOLS_PROFILE` | 工具集级别（minimal/standard/full） |

## 新增 API 端点

```
POST   /cron/jobs         创建定时任务
GET    /cron/jobs         列出定时任务
GET    /cron/jobs/{id}    获取任务详情
DELETE /cron/jobs/{id}    删除任务
POST   /cron/jobs/{id}/pause   暂停
POST   /cron/jobs/{id}/resume  恢复
```
