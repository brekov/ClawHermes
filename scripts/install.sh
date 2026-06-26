#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# ClawHermes 安装脚本
# 使用: bash <(curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh)
# 渠道: bash <(curl -fsSL ...) -s -- --with-lark --with-qq
# ============================================================

REPO="https://github.com/brekov/ClawHermes.git"
INSTALL_DIR="${HOME:-/tmp}/clawhermes"

# ── 参数解析 ──
CHANNELS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-lark)    CHANNELS+=("lark"); shift ;;
        --with-weixin)  CHANNELS+=("weixin"); shift ;;
        --with-qq)      CHANNELS+=("qq"); shift ;;
        --all-channels) CHANNELS=("lark" "weixin" "qq"); shift ;;
        *) echo "未知参数: $1"; echo "用法: $0 [--with-lark] [--with-weixin] [--with-qq] [--all-channels]"; exit 1 ;;
    esac
done

echo "==> ClawHermes 安装"
if [ ${#CHANNELS[@]} -gt 0 ]; then
    echo "  渠道: ${CHANNELS[*]}"
else
    echo "  渠道: (无 — 仅核心)"
fi

# ── 检测依赖 ──
command -v python3 >/dev/null 2>&1 || { echo "需要 Python 3.12+"; exit 1; }
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
echo "  python   Python ${PY_MAJOR}.${PY_MINOR}"

command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1 || { echo "需要 pip"; exit 1; }
PIP=$(command -v pip3 || echo pip)
echo "  pip      $($PIP --version | head -1)"

command -v git >/dev/null 2>&1 || { echo "需要 git"; exit 1; }
echo "  git      $(git --version)"

# ── 下载 ──
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR" && git pull --ff-only
else
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 拉取渠道子仓库 ──
for ch in "${CHANNELS[@]}"; do
    SUBMODULE_PATH="clawhermes-${ch}"
    if git submodule status "$SUBMODULE_PATH" &>/dev/null; then
        git submodule update --init --depth 1 "$SUBMODULE_PATH"
    else
        echo "  ⚠️  $SUBMODULE_PATH 不是有效的 submodule，跳过"
    fi
done

# ── 安装核心 ──
echo -n "  📦 安装 clawhermes 核心 ... "
if $PIP install -e . > /tmp/clawhermes-pip.log 2>&1; then
    echo "✅"
else
    echo "❌"
    tail -30 /tmp/clawhermes-pip.log
    echo "安装失败, 查看完整日志: /tmp/clawhermes-pip.log"
    exit 1
fi

# ── 安装渠道子仓库 ──
for ch in "${CHANNELS[@]}"; do
    CH_DIR="$INSTALL_DIR/clawhermes-${ch}"
    if [ -d "$CH_DIR" ] && [ -f "$CH_DIR/pyproject.toml" ]; then
        echo -n "  📦 安装 clawhermes-${ch} ... "
        if $PIP install -e "$CH_DIR" > /tmp/clawhermes-pip-${ch}.log 2>&1; then
            echo "✅"
        else
            echo "❌"
            tail -20 /tmp/clawhermes-pip-${ch}.log
        fi
    else
        echo "  ⚠️  clawhermes-${ch} 未找到，跳过"
    fi
done

# ── 初始化 ──
echo ""

echo "==> 交互式配置"
echo ""
echo "  ClawHermes 提供交互式初始化向导:"
echo "    • 选择 LLM 提供商 + 模型"
echo "    • 配置消息渠道 (飞书/微信/QQ)"
echo "    • Gateway 服务设置"
echo ""
echo -n "  🚀 立即运行 clawhermes setup? [Y/n]: "
read -r RUN_SETUP
if [ "${RUN_SETUP:-y}" != "n" ] && [ "${RUN_SETUP:-y}" != "N" ]; then
    clawhermes setup
else
    echo "  稍后运行: clawhermes setup"
fi


# ── 验证 ──
echo ""
echo "==> 验证安装"
python3 -c "
import litellm, fastapi, rich, yaml
print('  ✅ 核心依赖')
"
for ch in "${CHANNELS[@]}"; do
    IMPORT_ERR=$(python3 -c "import clawhermes_${ch}" 2>&1)
    if [ $? -eq 0 ]; then
        echo "  ✅ clawhermes-${ch}"
    else
        echo "  ⚠️  clawhermes-${ch} 导入失败: ${IMPORT_ERR}"
    fi
done

echo ""
echo "==> ClawHermes 安装完成"
echo "  运行 clawhermes --help 查看命令"
