## 🏷️ 版本信息

| 项目 | 值 |
|:---|:---|
| 版本号 | v0.15.2 |
| 发布日期 | 2026-07-16 |
| 版本类型 | PATCH — 系统性安全修复（35 项评审问题） |
| 语义化版本 | 0.15.2 |
| 评审基线 | `review.md` + `fix-plan.md` |
| PR 数量 | 6（PR1-PR5 分阶段修复 + PR6 CI 修复） |

## 🔒 安全修复（9 Critical + 10 High）

### Critical 修复（9 项）

| ID | 问题 | 方案 | PR |
|:---|:---|:---|:---|
| C1 | DelegateManager `with self._pool` 销毁池 | 移除 with，新增 `shutdown()` | #55 |
| C2 | CronScheduler executor 满载阻塞 /health | `asyncio.to_thread` + `asyncio.gather` | #55 |
| C3 | 上下文压缩 `last_prompt_tokens` 从未赋值 | 改 `max_context_tokens` 绝对阈值 | #55 |
| C4 | exec/code_eval 无沙箱隔离 | DockerSandbox 优先 + 硬化参数 | #56 |
| C5 | exec 黑名单仅注释无强制 | 沙箱优先 + 黑名单审计化 | #56 |
| C6 | DM 配对不校验 user_id | user_id 必填 + Ed25519 签名 + 限流 | #57 |
| C7 | execute 在运行循环内崩溃 | `run_coroutine_threadsafe` + 明确异常 | #55 |
| C8 | 协程 handler 在运行循环内崩溃 | 检测运行循环分流处理 | #55 |
| C11 | setup.py `import requests` 不在依赖 | 改用 httpx | #57 |

### High 修复（10 项）

| ID | 问题 | 方案 | PR |
|:---|:---|:---|:---|
| H1 | 技能/Agent 名路径穿越 | ScopedPath 类（正则 + is_relative_to） | #56 |
| H2 | 文件工具无 workspace 限制 | 6 工具加 root 校验 + 1MB/10MB 限制 | #56 |
| H3 | SQLite 工具可读任意 db | 限定 data_dir + `mode=ro` URI | #56 |
| H4 | Gateway secret 比较 + CORS 互斥 | `compare_digest` + 启动 fail-fast | #57 |
| H5 | Session 读操作加锁阻塞并发 | 读去锁，仅写加锁 | #58 |
| H6 | SkillHub 无签名/版本校验 | Ed25519 签名 + `min_clawhermes` 比对 | #58 |
| H7 | .env 默认 0o644 泄露 | `chmod 0o600` | #57 |
| H8 | CODE_LENGTH=6 + 无限流 | 升至 8 + 漏桶 10/min | #57 |
| H9 | LLMProvider usage/retry_after 兼容 | `_usage_to_dict` + Retry-After 解析 | #57 |
| H10 | INTERRUPT 清空整队列 | 按 chat_id 过滤 | #57 |

## 🛠️ 健壮性提升（16 Medium）

| ID | 修复 | PR |
|:---|:---|:---|
| M1 | chat_stream 复用辅助方法 | #55 |
| M2 | 删除 AgentConfig 死字段 | #58 |
| M3 | `locals()` 判定改前置 `result = None` | #58 |
| M4 | `get_event_loop()` → `get_running_loop()` | #58 |
| M5 | JSONMemoryProvider 加锁 + FIFO + SQLite 版本 | #59 |
| M6 | scheduler 恒等赋值删除 | #58 |
| M7 | 原子文件写 `atomic_write`（5 处） | #58 |
| M8 | `_http_request` curl → httpx | #58 |
| M9 | `_patch_file` 描述语义修正 | #59 |
| M10 | DockerSandbox 硬化 + 默认禁网 | #56/#59 |
| M11 | `MemoryError` → `ClawHermesMemoryError` | #58 |
| M12 | `split("\n")[1]` 加长度判断 | #58 |
| M13 | `chat_stream` 显式 `aclose()` | #59 |
| M14 | gateway `_auto_init` 失败 503 + degraded | #58 |
| M17 | Skills 懒加载（双重检查锁定） | #59 |
| M18 | MCP Streamable-HTTP SSE 支持 | #59 |

## 🧪 测试增强

- **+96 个测试**（v0.15.1 659 → v0.15.2 755）
- **新建 `tests/test_security.py`**：14 个负例安全套件
  - 路径穿越（4）：`../../.ssh/authorized_keys` / `/etc/passwd` / null 字节 / agent 路径
  - SQL 注入（3）：默认只读拒 DROP / data_dir 外拒 / 写操作需 `allow_write=True`
  - 配对绕过（4）：缺 user_id / 错误 user_id / 限流 / code 长度
  - CORS Gateway（3）：wildcard+credentials 互斥 / `compare_digest` / init 失败 503
- **CI 修复 PR6 (#60)**：mypy 6 错误 + 沙箱权限 + cryptography 依赖

## 📊 质量指标

| 指标 | v0.15.1 | v0.15.2 | 变化 |
|:---|:---|:---|:---|
| 测试用例 | 659 | 755 | +96 |
| 源文件 | 44 | 48 | +4 |
| 内置工具 | 35 | 35 | — |
| API 端点 | 33 | 33 | — |
| ruff | 0 | 0 | ✅ |
| mypy | 0 | 0 | ✅ |
| 安全测试套件 | 0 | 14 | +14 |
| 评审问题修复 | 0 | 35 | +35（9C+10H+16M） |

## 📦 依赖变更

- **新增**：`cryptography>=42.0`（C6 Ed25519 挑战签名验证）
- **移除**：`requests`（C11 改用 httpx）

## 📝 文档更新

- **CHANGELOG.md**：新增 v0.15.2 章节（6 PR 详细记录）
- **RELEASE.md**：重写为 v0.15.2 发布说明
- **FEATURES.md**：更新版本号、测试数、安全章节
- **docs/index.md**：徽章与版本号同步
- **docs/development-plan.md**：版本历史表补 v0.15.1/v0.15.2

## ⏭️ 推迟到 v0.16.0

- Task 5.7: 重构 `agent/loop.py` 拆分为 4 文件 + 统一 `_iterate` generator — 高风险重构
- Task 5.9: ruff 开启 `S`/`B006`/`ASYNC` 严格规则 — 改动面大

---

> **子仓库**：[clawhermes-lark](https://github.com/brekov/clawhermes-lark)（6,863 行）| [clawhermes-weixin](https://github.com/brekov/clawhermes-weixin)（308 行）| [clawhermes-qq](https://github.com/brekov/clawhermes-qq)

**Full Changelog**: https://github.com/brekov/ClawHermes/compare/v0.15.1...v0.15.2
