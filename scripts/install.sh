#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# ClawHermes 安装脚本
# 使用: bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
# ============================================================

REPO="https://github.com/brekov/ClawHermes.git"
INSTALL_DIR="${HOME:-/tmp}/clawhermes"

echo "==> ClawHermes 安装"

# ── 检测依赖 ──
command -v python3 >/dev/null 2>&1 || { echo "需要 Python 3.12+"; exit 1; }
PY_VER=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
echo "  python   $(python3 --version)"

command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1 || { echo "需要 pip"; exit 1; }
echo "  pip      $($(command -v pip3 || echo pip) --version | head -1)"

command -v git >/dev/null 2>&1 || { echo "需要 git"; exit 1; }
echo "  git      $(git --version)"

# ── 下载 ──
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR" && git pull --ff-only
else
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 安装 ──
PIP=$(command -v pip3 || echo pip)
$PIP install -e . -q

# ── 初始化 ──
mkdir -p "$HOME"/.clawhermes/{channels,providers,skills}
python3 -m clawhermes.cli setup >/dev/null 2>&1

# ── 验证 ──
python3 -c "import litellm, fastapi, rich, yaml" 2>/dev/null && \
    echo -e "\n==> ClawHermes 安装完成"
echo "  运行 clawhermes --help 查看命令"
