> 版本：v1.0
> 日期：2026-06-16
---

# ClawHermes · 部署指南

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

# 启动
clawhermes gateway --host 0.0.0.0
```

## 方式三：一键安装

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
```

## 渠道接入

### 交互式配置（推荐）

参照 OpenClaw 的 `openclaw gateway setup`，ClawHermes 也通过向导配置：

```bash
# 交互式向导，按提示填入渠道凭证
clawhermes gateway setup
```

配置保存在 `~/.clawhermes/channels.json`。

### 启动 Gateway（自动连接已配置的渠道）

```bash
clawhermes gateway start --host 0.0.0.0
```

### 查看已配置的渠道

```bash
clawhermes gateway status
```

### 备用：API 方式（临时启动）

也支持通过 API 动态启停渠道：

```bash
curl -X POST http://127.0.0.1:18789/channels/feishu/start?app_id=cli_xxx&app_secret=xxx
curl -X POST "http://127.0.0.1:18789/channels/telegram/start?token=xxx"
```

### 查看已连接的渠道

```bash
curl http://127.0.0.1:18789/channels
```

### 备用：API 方式（临时启动）

也支持通过 API 动态启停渠道：

```bash
# 飞书
curl -X POST http://127.0.0.1:18789/channels/feishu/start?app_id=cli_xxx&app_secret=xxx

# Telegram
curl -X POST "http://127.0.0.1:18789/channels/telegram/start?token=xxx"

# 微信 / QQ 同理
```

### Channel Bridge（复用 OpenClaw 微信 SDK）

```bash
FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx \
  node scripts/channel-bridge.cjs
```

## 健康检查

```bash
curl http://localhost:18789/health
# {"status":"ok","version":"0.6.0","tools":9,"skills":0,"sessions":0}
```

## 环境变量

所有配置项见 [env-reference.md](env-reference.md)。
