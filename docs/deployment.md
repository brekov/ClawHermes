# ClawHermes · 部署指南

> 版本：v2.1 | 日期：2026-06-17

---

## 方式一：Docker（推荐）

```bash
# 构建
docker build -t clawhermes .

# 运行
docker run -d \
  --name clawhermes \
  -e DEEPSEEK_API_KEY=sk-xxx \
  -e CH_TOOLS_PROFILE=standard \
  -p 18789:18789 \
  --restart unless-stopped \
  clawhermes

# 验证
curl http://localhost:18789/health
```

### docker-compose

```bash
# 配置 key
echo "DEEPSEEK_API_KEY=sk-xxx" > .env

# 启动
docker compose up -d

# 查看日志
docker compose logs -f
```

## 方式二：直接运行

```bash
# 安装
git clone https://github.com/brekov/ClawHermes.git
cd ClawHermes
pip install -e .

# 配置
echo "DEEPSEEK_API_KEY=sk-xxx" > .env

# 启动 Gateway（REST API 服务）
clawhermes gateway start --host 0.0.0.0
```

## 方式三：一键安装

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
```

---

## Gateway 说明

ClawHermes Gateway 是一个 **REST API** 服务，提供 26 个端点，通过 HTTP API 暴露 Agent 核心能力。

### 启动

```bash
# 启动 Gateway 服务
clawhermes gateway start --host 0.0.0.0

# 配置 LLM Provider
clawhermes gateway setup

# 交互式对话
clawhermes chat
```

### 常见 HTTP API 用法

```bash
# 健康检查
curl http://localhost:18789/health
# {"status":"ok","version":"0.14.0","uptime":3600,"tools":35}

# 初始化 Agent
curl -X POST http://localhost:18789/init \
  -H "Content-Type: application/json" \
  -d '{"api_key":"sk-xxx","model":"deepseek/deepseek-chat","profile":"standard"}'

# 对话
curl -X POST http://localhost:18789/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好"}'

# 列出会话
curl http://localhost:18789/sessions

# 定时任务
curl -X POST http://localhost:18789/cron/jobs \
  -H "Content-Type: application/json" \
  -d '{"name":"daily","task":"send report","mode":"cron","hour":"9","minute":"0"}'
```

## 环境变量

完整配置参考见 [env-reference.md](env-reference.md)。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | — |
| `CH_GATEWAY_PORT` | Gateway 端口 | 18789 |
| `CH_TOOLS_PROFILE` | 工具集级别 | standard |
| `CH_DATA_DIR` | 数据目录 | ~/.clawhermes |
