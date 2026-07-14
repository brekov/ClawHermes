## 🏷️ 版本信息

| 项目 | 值 |
|:---|:---|
| 版本号 | v0.15.1 |
| 发布日期 | 2026-07-14 |
| 版本类型 | PATCH — 安全修复 + 并发加固 + Agent Loop 重构 |
| 语义化版本 | 0.15.1 |

## 🔒 安全修复

### T1.1 _calc eval RCE 消除
- `eval()` → AST 白名单求值器（5 节点 + 16 函数 + 3 常量）
- 显式拒绝属性访问、lambda、列表推导、关键字参数

### T1.2 shell=True 注入消除
- `_web_fetch`：curl + sed → httpx + Python 正则
- `_web_search_fallback`：curl + grep → httpx + 正则提取
- `_grep`：shell grep → Python `re` + `pathlib.rglob`
- `_exec_command`：保留 shell=True，增加危险命令黑名单 + 审计日志

## 🔄 代码重构

### T1.3 _run_maybe_async 废弃
- 删除线程创建函数，改为内联 `asyncio.run()`

### T1.4 Agent Loop 重构
- 抽取 3 个辅助方法（`_build_messages` / `_should_loop_continue` / `_finalize_response`）
- 消除 ~80 行重复代码，净减 52 行

## 🛡️ 并发安全加固

### T1.6 DMPairingManager 锁修复
- `asyncio.Lock` → `threading.RLock`，12 个方法全部加锁

### T1.7 SkillManager 文件锁
- 新增 `threading.RLock`，4 个写方法加锁

## 📊 质量指标

| 指标 | v0.15.0 | v0.15.1 | 变化 |
|:---|:---|:---|:---|
| 测试用例 | 416 | 659 | +243 |
| 源文件 | 31 | 44 | +13 |
| 内置工具 | 35 | 35 | — |
| API 端点 | 33 | 33 | — |
| ruff | 0 | 0 | ✅ |
| mypy | 0 | 0 | ✅ |

## 📝 文档更新

- **全部 11 个文档** 更新至 v0.15.1 基线
- 新增并发安全模型章节（data-model.md / architecture.md）
- 新增工具安全策略表（architecture.md / FEATURES.md）

---

> **子仓库**：[clawhermes-lark](https://github.com/brekov/clawhermes-lark)（6,863 行）| [clawhermes-weixin](https://github.com/brekov/clawhermes-weixin)（308 行）| [clawhermes-qq](https://github.com/brekov/clawhermes-qq)

**Full Changelog**: https://github.com/brekov/ClawHermes/compare/v0.15.0...v0.15.1
