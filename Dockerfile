FROM python:3.12-slim

WORKDIR /app

# ── 渠道构建参数 ──
ARG WITH_LARK=""
ARG WITH_WEIXIN=""
ARG WITH_QQ=""

# 系统依赖
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制项目（.dockerignore 排除不必要文件）
COPY . .

# ── 拉取渠道子仓库 ──
RUN if [ -n "$WITH_LARK" ]; then \
        git submodule update --init --depth 1 clawhermes-lark; \
    fi && \
    if [ -n "$WITH_WEIXIN" ]; then \
        git submodule update --init --depth 1 clawhermes-weixin; \
    fi && \
    if [ -n "$WITH_QQ" ]; then \
        git submodule update --init --depth 1 clawhermes-qq; \
    fi

# 安装 ClawHermes 核心
RUN pip install --no-cache-dir -e .

# ── 安装渠道子仓库 ──
RUN if [ -n "$WITH_LARK" ] && [ -d clawhermes-lark ]; then \
        pip install --no-cache-dir -e ./clawhermes-lark; \
    fi && \
    if [ -n "$WITH_WEIXIN" ] && [ -d clawhermes-weixin ]; then \
        pip install --no-cache-dir -e ./clawhermes-weixin; \
    fi && \
    if [ -n "$WITH_QQ" ] && [ -d clawhermes-qq ]; then \
        pip install --no-cache-dir -e ./clawhermes-qq; \
    fi

# 初始化
RUN clawhermes setup --non-interactive

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:18789/health || exit 1

# Gateway 端口
EXPOSE 18789

# 默认启动 Gateway
CMD ["clawhermes", "gateway", "start", "--host", "0.0.0.0"]
