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

渠道采用**声明式配置**——在 `.env` 中写好，Gateway 启动时自动连接。

### 配置方式（推荐）

在 `.env` 文件中添加：

```bash
# 飞书
CH_CHANNEL_FEISHU_ENABLED=true
CH_CHANNEL_FEISHU_APP_ID=cli_xxx
CH_CHANNEL_FEISHU_APP_SECRET=xxx

# 企业微信
CH_CHANNEL_WECHAT_ENABLED=true
CH_CHANNEL_WECHAT_CORP_ID=wwxxx
CH_CHANNEL_WECHAT_CORP_SECRET=xxx
CH_CHANNEL_WECHAT_AGENT_ID=1000001

# QQ（需先启动 go-cqhttp）
CH_CHANNEL_QQ_ENABLED=true
CH_CHANNEL_QQ_WS_URL=ws://127.0.0.1:6700

# Telegram
CH_CHANNEL_TELEGRAM_ENABLED=true
CH_CHANNEL_TELEGRAM_TOKEN=xxx:xxx
```

然后直接启动 Gateway，渠道自动连接：

```bash
clawhermes gateway --host 0.0.0.0
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
