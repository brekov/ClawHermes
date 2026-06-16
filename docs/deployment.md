# ClawHermes · 部署指南

> 版本：v2.0
> 日期：2026-06-16

---

## 方式一：Docker（推荐）

```bash
# 构建
docker build -t clawhermes .

# 运行
docker run -d \
  --name clawhermes \
  -e DEEPSEEK_API_KEY=sk-xxx \
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

> ClawHermes 的 Gateway 是一个 **REST API** 服务，用于 Agent 交互，**并非**聊天平台网关。
> 
> Gateway 提供 10 个 REST 端点，通过 HTTP API 暴露 Agent 核心能力（对话、工具、记忆、技能等）。
> 上层应用可以通过这些 API 接入 ClawHermes 的 Agent 能力，无需依赖任何特定聊天平台。

```bash
# 启动 Gateway 服务
clawhermes gateway start --host 0.0.0.0

# 配置 LLM Provider
clawhermes gateway setup
```

## 健康检查

```bash
curl http://localhost:18789/health
# {"status":"ok","version":"0.10.0","tools":9,"skills":0,"sessions":0}
```

## 环境变量

所有配置项见 [env-reference.md](env-reference.md)。
