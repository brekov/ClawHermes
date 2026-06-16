# ClawHermes

融合 **Hermes** 自进化能力与 **OpenClaw** Gateway 体系的 Python AI Agent 框架。

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 设计理念

| 来自 Hermes | 来自 OpenClaw |
|:---|:---|
| 三层 System Prompt → 缓存友好 | 插件钩子体系 → 工具级拦截 |
| Background Review → 自进化 | 工具策略引擎 → 精细权限 |
| ContextEngine 可插拔 | Gateway 统一控制面 |
| 多凭证池 → 高可用 | 双层持久化 → 树形 transcript |

## 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配 API Key
echo "DEEPSEEK_API_KEY=sk-xxx" > .env

# 3. 初始化
clawhermes setup

# 4. 对话
clawhermes chat
```

### 一次性提问

```bash
clawhermes chat --one-shot "用 Python 写一个快速排序"
```

## 架构

```
用户 → Gateway → Session 路由 → Agent Loop
                                    │
                          ┌─────────▼─────────┐
                          │ 三层 System Prompt │
                          │  stable/context/   │
                          │  volatile          │
                          └─────────┬─────────┘
                                    │
                          ┌─────────▼─────────┐
                          │  思考-行动循环     │
                          │  LLM → 工具 → LLM │
                          └─────────┬─────────┘
                                    │
                     ┌──────────────┼──────────────┐
                     ▼              ▼              ▼
                工具系统         记忆系统        技能系统
              钩子+策略        多Provider     自进化
```

## 内置工具（8个）

| 工具 | 说明 | 可并行 |
|:---|:---|:----:|
| `get_time` | 获取当前时间 | ✅ |
| `web_search` | 搜索互联网 | ✅ |
| `memory_search` | 搜索记忆库 | ✅ |
| `memory_save` | 保存记忆 | ❌ |
| `read_file` | 读取文件 | ✅ |
| `write_file` | 写入文件 | ❌ |
| `exec` | 执行命令 | ❌ |
| `session_status` | 会话状态 | ✅ |

## 项目结构

```
src/clawhermes/
├── cli.py              # CLI 入口
├── config.py           # 类型安全配置
├── types.py            # 核心类型
├── llm/provider.py     # LLM 调用 + 多凭证池
├── agent/
│   ├── loop.py         # Agent 核心循环 + 钩子 + 工具调度
│   ├── prompt.py       # 三层 System Prompt
│   └── memory.py       # 记忆系统
└── tools/builtin.py    # 8个内置工具
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python tests/test_integration.py
```

## License

MIT
