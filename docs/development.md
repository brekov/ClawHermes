# ClawHermes · 开发指南

> 版本：v2.2 | 日期：2026-06-24

## 环境准备

```bash
# Python 3.12+
python3 --version

# 克隆
git clone https://github.com/brekov/ClawHermes.git
cd ClawHermes

# 安装依赖（含开发工具）
pip install -e ".[dev]"

# 验证
clawhermes doctor
```

## 项目结构

```
src/clawhermes/
├── agent/              # Agent 核心
│   ├── loop.py         #   对话主循环 + HookManager + ToolDispatcher
│   ├── prompt.py       #   三层 System Prompt
│   ├── memory.py       #   记忆系统（MemoryManager + JSONProvider）
│   ├── context.py      #   F10: 上下文压缩引擎
│   ├── ace.py          #   F17: 自适应上下文引擎（ACE）
│   ├── delegate.py     #   F12: 子 Agent 委派
│   ├── exceptions.py   #   F14: 异常类层次（5大类17子类）
│   ├── session.py      #   F5: 会话持久化（SQLite WAL）
│   ├── scheduler.py    #   F15: Cron 调度器
│   └── agent_mgr.py    #   多 Agent 管理
├── channel/            # F18: Channel Adapter SDK
├── llm/                # F1: LLM Provider + CredentialPool
├── tools/
│   ├── builtin.py      # F3: 35 个内置工具 + 3 级 Profile
│   └── sandbox.py      # F16: Docker 沙箱
├── skills/
│   ├── manager.py      # F6/F7: 技能系统 + Background Review + Curator
│   └── hub.py          # F19: Federated Skill Hub
├── storage/            # ChromaDB 向量记忆
├── gateway/            # FastAPI Gateway（33 个端点）
├── cli.py              # CLI 入口
├── config.py           # 配置管理
└── types.py            # 核心类型
```

## 开发流程

1. **设计**：先在 `docs/` 下写设计文档
2. **类型**：在 `types.py` 中定义数据结构
3. **实现**：按模块目录写代码
4. **测试**：在 `tests/` 添加测试
5. **文档**：更新 README 和对应文档
6. **提交**：`git commit -m "feat: 说明"`

## 测试

```bash
# 全部测试（MockProvider，不依赖真实 API）
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=src/clawhermes --cov-report=term-missing

# 单独运行某模块
pytest tests/test_ace.py -v
```

## 代码规范

- Python 3.12+，类型注解全覆盖
- mypy 6 项严格检查：`warn_return_any` / `unused_ignores` / `redundant_casts` / `check_untyped_defs` / `no_implicit_optional` / `strict_equality`
- ruff lint（零错误）
- 单文件不超过 500 行
- `json.loads()` 使用 `assert isinstance()` 做运行时守卫，禁止 `typing.Any`

## 添加新工具

1. 在 `tools/builtin.py` 中实现 handler 函数，更新 `FULL_TOOLS` 集合
2. 在 `register_builtin_tools()` 中注册 `ToolDef`，标记 `parallel_safe` / `require_confirm`
3. 在 `tests/test_unit_extended.py` 中添加测试

## 发布流程

```bash
# 1. 更新版本号
#    编辑 pyproject.toml: version = "0.y.0"

# 2. 更新 CHANGELOG.md

# 3. 运行全部检查
ruff check src/ tests/
mypy src/
pytest tests/ -v

# 4. 提交 + 打 tag
git add -A && git commit -m "release: v0.y.0"
git tag -a v0.y.0 -m "v0.y.0"
git push origin main --tags

# 5. 创建 GitHub Release
gh release create v0.y.0 --title "v0.y.0" --notes-file RELEASE.md
```
