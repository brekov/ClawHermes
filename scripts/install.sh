#!/usr/bin/env bash
set -euo pipefail

# ClawHermes 一键部署脚本
# 使用: bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)

REPO="https://github.com/brekov/ClawHermes.git"
INSTALL_DIR="${HOME:-/tmp}/clawhermes"

echo "🚀 ClawHermes 一键安装"
echo "====================="

# 检测 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 需要 Python 3.12+"
    exit 1
fi
echo "✅ Python $(python3 --version)"

# 检测 pip
if ! command -v pip3 &>/dev/null; then
    echo "❌ 需要 pip3"
    exit 1
fi

# 克隆或更新
if [ -d "$INSTALL_DIR" ]; then
    echo "📦 更新已有安装..."
    cd "$INSTALL_DIR" && git pull
else
    echo "📦 克隆项目..."
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 安装
echo "📦 安装依赖..."
pip3 install -e . --quiet

# 初始化
echo "📋 初始化配置..."
clawhermes setup

# 检测 API Key
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    if [ -f .env ]; then
        echo "✅ 检测到 .env 文件"
    else
        echo ""
        echo "⚠️  未设置 DEEPSEEK_API_KEY"
        echo "   请运行: echo 'DEEPSEEK_API_KEY=sk-xxx' > .env"
        echo ""
    fi
fi

echo ""
echo "✅ 安装完成！"
echo ""
echo "运行方式:"
echo "  CLI 对话:   clawhermes chat"
echo "  HTTP 服务:  clawhermes gateway --host 0.0.0.0 --port 18789"
echo "  Docker:     docker build -t clawhermes . && docker run -p 18789:18789 clawhermes"
echo ""
