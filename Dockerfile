FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制项目
COPY . .

# 安装 ClawHermes
RUN pip install --no-cache-dir -e ".[dev]" && \
    clawhermes setup

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:18789/health || exit 1

# Gateway 端口
EXPOSE 18789

# 默认启动 Gateway
CMD ["clawhermes", "gateway", "start", "--host", "0.0.0.0"]
