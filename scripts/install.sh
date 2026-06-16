#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# ClawHermes 一键安装脚本
# 完全独立，不依赖 OpenClaw 或任何外部系统
# 使用: bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
# ============================================================

REPO="https://github.com/brekov/ClawHermes.git"
INSTALL_DIR="${HOME:-/tmp}/clawhermes"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     ClawHermes 一键安装              ║${NC}"
echo -e "${CYAN}║     融合 Hermes + OpenClaw           ║${NC}"
echo -e "${CYAN}║     纯 Python，零外部依赖            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 环境检测 ──────────────────────────────────────────────

echo -e "${CYAN}🔍 检测环境...${NC}"

# Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ 未找到 Python3，请先安装 Python 3.12+${NC}"
    exit 1
fi

PY_VER=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo -e "${RED}❌ 需要 Python 3.12+，当前: $(python3 --version)${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python $(python3 --version)${NC}"

# pip
if command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
elif command -v pip &>/dev/null; then
    PIP_CMD="pip"
else
    echo -e "${RED}❌ 未找到 pip，请先安装 python3-pip${NC}"
    exit 1
fi
echo -e "${GREEN}✅ ${PIP_CMD}${NC}"

# git
if ! command -v git &>/dev/null; then
    echo -e "${RED}❌ 未找到 git${NC}"
    exit 1
fi
echo -e "${GREEN}✅ git${NC}"

# ── 下载项目 ──────────────────────────────────────────────

echo ""
echo -e "${CYAN}📦 下载项目...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    echo "   更新已有安装..."
    cd "$INSTALL_DIR" && git pull --ff-only
else
    echo "   克隆项目..."
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
echo -e "${GREEN}✅ 项目下载完成${NC}"

# ── 安装依赖 ──────────────────────────────────────────────

echo ""
echo -e "${CYAN}📦 安装 Python 依赖...${NC}"

$PIP_CMD install -e . --quiet 2>&1 | tail -1
echo -e "${GREEN}✅ 依赖安装完成${NC}"

# 验证核心依赖
echo ""
echo -e "${CYAN}🔍 验证核心依赖...${NC}"
python3 -c "import litellm; print('   litellm:', litellm.__version__)" 2>/dev/null && \
    echo -e "${GREEN}   ✅ litellm${NC}" || echo -e "${RED}   ❌ litellm${NC}"
python3 -c "import fastapi; print('   fastapi:', fastapi.__version__)" 2>/dev/null && \
    echo -e "${GREEN}   ✅ fastapi${NC}" || echo -e "${RED}   ❌ fastapi${NC}"
python3 -c "import rich; print('   rich:', rich.__version__)" 2>/dev/null && \
    echo -e "${GREEN}   ✅ rich${NC}" || echo -e "${RED}   ❌ rich${NC}"
python3 -c "import yaml; print('   yaml ok')" 2>/dev/null && \
    echo -e "${GREEN}   ✅ pyyaml${NC}" || echo -e "${RED}   ❌ pyyaml${NC}"

# ── 初始化 ────────────────────────────────────────────────

echo ""
echo -e "${CYAN}📋 初始化...${NC}"

# 创建数据目录
DATA_DIR="${HOME}/.clawhermes"
mkdir -p "$DATA_DIR"/{channels,providers,skills}
echo -e "${GREEN}✅ 数据目录: ${DATA_DIR}${NC}"

# 生成默认配置
python3 -m clawhermes.cli setup 2>&1 | head -5
echo -e "${GREEN}✅ 默认配置已生成${NC}"

# ── 检测 API Key ──────────────────────────────────────────

echo ""
echo -e "${CYAN}🔑 检测 API Key...${NC}"

# 扫描所有 *_API_KEY 环境变量
found_key=""
while IFS='=' read -r name value; do
    if [[ "$name" == *_API_KEY ]] && [ -n "$value" ]; then
        found_key="$name"
        break
    fi
done < <(env)

if [ -f "${INSTALL_DIR}/.env" ]; then
    echo -e "${GREEN}✅ 检测到 .env 文件${NC}"
elif [ -n "$found_key" ]; then
    echo "${found_key}=${!found_key}" > "${INSTALL_DIR}/.env"
    echo -e "${GREEN}✅ 已从环境变量 ${found_key} 写入 .env${NC}"
elif ls "${DATA_DIR}/providers/"*.yaml &>/dev/null 2>&1; then
    echo -e "${GREEN}✅ 已检测到 LLM Provider 配置${NC}"
else
    echo ""
    echo -e "${YELLOW}⚠️  未设置 API Key${NC}"
    echo "   设置任意 *_API_KEY 环境变量即可:"
    echo "     export DEEPSEEK_API_KEY=sk-xxx"
    echo "     export OPENAI_API_KEY=sk-xxx"
    echo ""
fi

# ── 验证 ──────────────────────────────────────────────────

echo ""
echo -e "${CYAN}🔍 验证安装...${NC}"
python3 -m clawhermes.cli doctor 2>&1 | head -10
echo ""

# ── 完成 ──────────────────────────────────────────────────

echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ ClawHermes 安装完成！             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}快速开始:${NC}"
echo ""
echo "  1. CLI 对话（需先配 API Key）"
echo -e "     ${YELLOW}clawhermes chat${NC}"
echo ""
echo "  2. 配置消息渠道"
echo -e "     ${YELLOW}clawhermes gateway setup${NC}"
echo ""
echo "  3. 启动常驻服务"
echo -e "     ${YELLOW}clawhermes gateway start${NC}"
echo ""
echo "  4. 设定 Agent 身份"
echo -e "     ${YELLOW}clawhermes agent set-persona${NC}"
echo ""
echo -e "详细文档: ${CYAN}https://github.com/brekov/ClawHermes${NC}"
echo ""
