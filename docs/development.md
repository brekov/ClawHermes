> 版本：v1.0
> 日期：2026-06-16

# ClawHermes · 开发指南

## 环境准备

```bash
# Python 3.12+
python3 --version

# 克隆
git clone https://github.com/brekov/ClawHermes.git
cd ClawHermes

# 安装依赖
pip install -e ".[dev]"

# 验证
clawhermes doctor
```

## 项目结构

```
src/clawhermes/
├── agent/          # Agent 核心（循环/提示词/记忆/上下文/委派）
├── llm/            # LLM Provider
├── tools/          # 工具系统
├── skills/         # 技能系统
├── storage/        # 存储
├── gateway/        # 消息网关（API + 平台适配器）
├── cli.py          # CLI 入口
├── config.py       # 配置管理
└── types.py        # 核心类型
```

## 开发流程

1. **设计**：先在 `docs/` 下写设计文档
2. **类型**：在 `types.py` 中定义数据结构
3. **实现**：按模块目录写代码
4. **测试**：在 `tests/` 添加测试，保持 56+ 通过
5. **文档**：更新 README 和对应文档
6. **提交**：`git commit -m "feat: 说明" && git tag -a v0.x.0`

## 测试

```bash
# 完整测试（不需要 API Key）
python tests/test_all.py

# 集成测试（MockProvider）
python tests/test_integration.py
```

## 代码规范

- Python 3.12+，类型注解全覆盖
- 单文件不超过 500 行
- ruff lint（`pip install ruff && ruff check src/`）
- 提交前确保 56 个测试全通过

## 添加新工具

1. 在 `tools/builtin.py` 中实现 handler 函数
2. 在 `register_builtin_tools()` 中注册 ToolDef
3. 在 `tests/test_all.py` 中验证

## 添加新渠道

1. 在 `gateway/platforms/` 下创建适配器（继承 PlatformAdapter）
2. 实现 `send_text` / `start` / `stop`
3. 在 `gateway/app.py` 中注册 API 端点

## 发布流程

```bash
# 1. 更新版本号
sed -i 's/version = "0.x.0"/version = "0.y.0"/' pyproject.toml

# 2. 更新 CHANGELOG.md

# 3. 提交 + 打 tag
git add -A && git commit -m "release: v0.y.0"
git tag -a v0.y.0 -m "v0.y.0"
git push origin main --tags

# 4. 创建 GitHub Release
```
