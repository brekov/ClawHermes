#!/usr/bin/env bash
# ============================================================================
# ClawHermes Installer
# ============================================================================
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/brekov/ClawHermes/main/scripts/install.sh | bash
#
# Options:
#   --with-lark        Install Feishu/Lark channel adapter
#   --with-weixin      Install WeChat channel adapter
#   --with-qq          Install QQ Bot channel adapter
#   --all-channels     Install all channel adapters
#   --no-venv          Skip virtual environment creation
#   --skip-setup       Skip interactive setup wizard
#   --non-interactive  Skip stages that require user input
#   --branch NAME      Git branch to install (default: main)
#   --stage NAME       Run one bootstrap stage
#   --json             Print JSON result frame for --stage
#   --manifest         Print bootstrap stage manifest as JSON
#   --dir PATH         Installation directory
#   --clawhermes-home PATH  Data directory (default: ~/.clawhermes)
#
# ============================================================================

set -e

# Guard against inherited env leakage
if [ -n "${PYTHONPATH:-}" ]; then
    echo "⚠ Ignoring inherited PYTHONPATH during install to avoid module shadowing"
    unset PYTHONPATH
fi
if [ -n "${PYTHONHOME:-}" ]; then
    echo "⚠ Ignoring inherited PYTHONHOME during install"
    unset PYTHONHOME
fi

export UV_NO_CONFIG=1

# ── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ── Configuration ───────────────────────────────────────────────────
REPO_URL="https://github.com/brekov/ClawHermes.git"
CLAWHERMES_HOME="${CLAWHERMES_HOME:-$HOME/.clawhermes}"
PYTHON_VERSION="3.12"

if [ -n "${CLAWHERMES_INSTALL_DIR:-}" ]; then
    INSTALL_DIR="$CLAWHERMES_INSTALL_DIR"
    INSTALL_DIR_EXPLICIT=true
else
    INSTALL_DIR=""
    INSTALL_DIR_EXPLICIT=false
fi

# ── Options ─────────────────────────────────────────────────────────
USE_VENV=true
RUN_SETUP=true
NON_INTERACTIVE=false
BRANCH="main"
JSON_OUTPUT=false
STAGE_NAME=""
MANIFEST_MODE=false
ROOT_FHS_LAYOUT=false
CHANNELS=()

# ── Parse arguments ─────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --with-lark)    CHANNELS+=("lark"); shift ;;
        --with-weixin)  CHANNELS+=("weixin"); shift ;;
        --with-qq)      CHANNELS+=("qq"); shift ;;
        --all-channels) CHANNELS=("lark" "weixin" "qq"); shift ;;
        --no-venv)      USE_VENV=false; shift ;;
        --skip-setup)   RUN_SETUP=false; shift ;;
        --non-interactive) NON_INTERACTIVE=true; shift ;;
        --branch)       BRANCH="$2"; shift 2 ;;
        --stage)        STAGE_NAME="$2"; shift 2 ;;
        --json)         JSON_OUTPUT=true; shift ;;
        --manifest)     MANIFEST_MODE=true; shift ;;
        --dir)          INSTALL_DIR="$2"; INSTALL_DIR_EXPLICIT=true; shift 2 ;;
        --clawhermes-home) CLAWHERMES_HOME="$2"; shift 2 ;;
        -h|--help)
            echo "ClawHermes Installer"
            echo ""
            echo "Usage: install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --with-lark        Install Feishu/Lark channel adapter"
            echo "  --with-weixin      Install WeChat channel adapter"
            echo "  --with-qq          Install QQ Bot channel adapter"
            echo "  --all-channels     Install all channel adapters"
            echo "  --no-venv          Skip virtual environment creation"
            echo "  --skip-setup       Skip interactive setup wizard"
            echo "  --non-interactive  Skip stages that require user input"
            echo "  --branch NAME      Git branch to install (default: main)"
            echo "  --stage NAME       Run one bootstrap stage"
            echo "  --json             Print JSON result frame for --stage"
            echo "  --manifest         Print bootstrap stage manifest as JSON"
            echo "  --dir PATH         Installation directory"
            echo "  --clawhermes-home PATH  Data directory (default: ~/.clawhermes)"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Helper functions ────────────────────────────────────────────────

print_banner() {
    echo ""
    echo -e "${MAGENTA}${BOLD}"
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│               🦞 ClawHermes Installer                  │"
    echo "├─────────────────────────────────────────────────────────┤"
    echo "│  An open source AI agent framework.                    │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
}

log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

is_termux() {
    [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == *"com.termux/files/usr"* ]]
}

json_escape() {
    printf '%s' "$1" | tr '\n' ' ' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

emit_stage_json() {
    local stage="$1" ok="$2" skipped="${3:-false}" reason="${4:-}"
    local escaped_reason
    escaped_reason="$(json_escape "$reason")"
    if [ -n "$escaped_reason" ]; then
        printf '{"ok":%s,"stage":"%s","skipped":%s,"reason":"%s"}\n' "$ok" "$stage" "$skipped" "$escaped_reason"
    else
        printf '{"ok":%s,"stage":"%s","skipped":%s}\n' "$ok" "$stage" "$skipped"
    fi
}

emit_manifest() {
    printf '%s' '{"protocol_version":1,"stages":[{"name":"prerequisites","title":"System prerequisites","category":"runtime","needs_user_input":false},{"name":"repository","title":"Download ClawHermes","category":"runtime","needs_user_input":false},{"name":"venv","title":"Create Python virtual environment","category":"runtime","needs_user_input":false},{"name":"python-deps","title":"Install Python dependencies","category":"runtime","needs_user_input":false},{"name":"channel-deps","title":"Install channel adapters","category":"runtime","needs_user_input":false},{"name":"path","title":"Install clawhermes command","category":"runtime","needs_user_input":false},{"name":"config","title":"Prepare config templates","category":"configuration","needs_user_input":false},{"name":"setup","title":"Configure API keys and settings","category":"configuration","needs_user_input":true},{"name":"gateway","title":"Configure gateway service","category":"configuration","needs_user_input":true},{"name":"complete","title":"Finish install","category":"runtime","needs_user_input":false}]}'
    printf '\n'
}

stage_needs_user_input() {
    case "$1" in
        setup|gateway) return 0 ;;
        *) return 1 ;;
    esac
}

# ── System detection ────────────────────────────────────────────────

detect_os() {
    case "$(uname -s)" in
        Linux*)
            if is_termux; then OS="android"; DISTRO="termux"
            else OS="linux"
                if [ -f /etc/os-release ]; then . /etc/os-release; DISTRO="$ID"; else DISTRO="unknown"; fi
            fi ;;
        Darwin*) OS="macos"; DISTRO="macos" ;;
        *) OS="unknown"; DISTRO="unknown"; log_warn "Unknown OS" ;;
    esac
    log_info "Detected: $OS ($DISTRO)"
}

# ── Install layout ──────────────────────────────────────────────────

resolve_install_layout() {
    if [ "$INSTALL_DIR_EXPLICIT" = true ]; then
        log_info "Install directory: $INSTALL_DIR (explicit)"
        return 0
    fi
    if is_termux; then
        INSTALL_DIR="$CLAWHERMES_HOME/clawhermes"
        return 0
    fi
    if [ "$OS" = "linux" ] && [ "$(id -u)" -eq 0 ]; then
        if [ -d "$CLAWHERMES_HOME/clawhermes/.git" ]; then
            INSTALL_DIR="$CLAWHERMES_HOME/clawhermes"
            log_info "Existing install at $INSTALL_DIR — keeping legacy layout"
            return 0
        fi
        INSTALL_DIR="/usr/local/lib/clawhermes"
        ROOT_FHS_LAYOUT=true
        log_info "Root install — FHS layout: $INSTALL_DIR"
        return 0
    fi
    INSTALL_DIR="$CLAWHERMES_HOME/clawhermes"
}

get_command_link_dir() {
    if is_termux && [ -n "${PREFIX:-}" ]; then echo "$PREFIX/bin"
    elif [ "$ROOT_FHS_LAYOUT" = true ]; then echo "/usr/local/bin"
    else echo "$HOME/.local/bin"; fi
}

# ── Managed uv ──────────────────────────────────────────────────────

install_uv() {
    if is_termux; then
        log_info "Termux: using stdlib venv + pip instead of uv"
        UV_CMD=""
        return 0
    fi
    local _managed_uv="$CLAWHERMES_HOME/bin/uv"
    if [ -x "$_managed_uv" ]; then
        UV_CMD="$_managed_uv"
        log_ok "Managed uv found ($($UV_CMD --version 2>/dev/null))"
        return 0
    fi
    log_info "Installing managed uv into $CLAWHERMES_HOME/bin ..."
    mkdir -p "$CLAWHERMES_HOME/bin"
    local _uv_log _uv_installer
    _uv_log="$(mktemp 2>/dev/null || echo "/tmp/clawhermes-uv.$$.log")"
    _uv_installer="$(mktemp 2>/dev/null || echo "/tmp/clawhermes-uv-installer.$$.sh")"
    if ! curl -LsSf https://astral.sh/uv/install.sh -o "$_uv_installer" 2>"$_uv_log"; then
        log_error "Failed to download uv installer"
        sed 's/^/    /' "$_uv_log" >&2
        rm -f "$_uv_log" "$_uv_installer"
        exit 1
    fi
    if env XDG_BIN_HOME="$CLAWHERMES_HOME/bin" sh "$_uv_installer" >>"$_uv_log" 2>&1; then
        rm -f "$_uv_installer" "$_uv_log"
        UV_CMD="$_managed_uv"
        log_ok "uv installed ($($UV_CMD --version 2>/dev/null))"
    else
        log_error "Failed to install uv"
        sed 's/^/    /' "$_uv_log" >&2
        rm -f "$_uv_log" "$_uv_installer"
        exit 1
    fi
}

# ── Python check ────────────────────────────────────────────────────

check_python() {
    if is_termux; then
        if command -v python >/dev/null 2>&1; then
            PYTHON_PATH="$(command -v python)"
            if "$PYTHON_PATH" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
                log_ok "$($PYTHON_PATH --version 2>/dev/null) found"
                return 0
            fi
        fi
        log_error "Termux Python must be 3.12+ — run: pkg install python"
        exit 1
    fi
    if $UV_CMD python find "$PYTHON_VERSION" &> /dev/null; then
        PYTHON_PATH=$($UV_CMD python find "$PYTHON_VERSION")
        log_ok "$($PYTHON_PATH --version 2>/dev/null) found"
    else
        log_info "Python $PYTHON_VERSION not found, installing via uv..."
        $UV_CMD python install "$PYTHON_VERSION"
        PYTHON_PATH=$($UV_CMD python find "$PYTHON_VERSION")
        log_ok "$($PYTHON_PATH --version 2>/dev/null) installed"
    fi
}

# ── Git check ───────────────────────────────────────────────────────

check_git() {
    if command -v git >/dev/null 2>&1; then
        log_ok "git $(git --version | cut -d' ' -f3)"
    else
        log_error "git required — install git first"
        exit 1
    fi
}

# ── Clone / update repository ───────────────────────────────────────

clone_repo() {
    mkdir -p "$(dirname "$INSTALL_DIR")"
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Updating existing checkout..."
        cd "$INSTALL_DIR" && git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull --ff-only
    else
        log_info "Cloning ClawHermes..."
        git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
    log_ok "Repository ready: $INSTALL_DIR"

    # Channel submodules
    for ch in "${CHANNELS[@]}"; do
        SUBMODULE_PATH="clawhermes-${ch}"
        if [ -d "$SUBMODULE_PATH/.git" ]; then
            log_info "Updating $SUBMODULE_PATH submodule..."
            git submodule update --init --depth 1 "$SUBMODULE_PATH" 2>/dev/null || true
        elif git submodule status "$SUBMODULE_PATH" &>/dev/null 2>&1; then
            log_info "Initializing $SUBMODULE_PATH submodule..."
            git submodule update --init --depth 1 "$SUBMODULE_PATH" 2>/dev/null || true
        else
            log_warn "$SUBMODULE_PATH is not a valid submodule, skipping"
        fi
    done
}

# ── Virtual environment ─────────────────────────────────────────────

setup_venv() {
    if [ "$USE_VENV" = false ]; then
        log_info "Skipping venv (--no-venv)"
        return 0
    fi
    if [ -d "$INSTALL_DIR/.venv" ]; then
        log_info "Removing old venv..."
        rm -rf "$INSTALL_DIR/.venv"
    fi
    cd "$INSTALL_DIR"
    if is_termux; then
        "$PYTHON_PATH" -m venv .venv
        log_ok "venv created (stdlib venv)"
    else
        $UV_CMD venv .venv --python "$PYTHON_VERSION"
        log_ok "venv created (Python $PYTHON_VERSION)"
    fi
    export VIRTUAL_ENV="$INSTALL_DIR/.venv"
    SETUP_PYTHON="$INSTALL_DIR/.venv/bin/python"
    SETUP_PIP="$INSTALL_DIR/.venv/bin/pip"
}

# ── Python dependencies ─────────────────────────────────────────────

install_python_deps() {
    cd "$INSTALL_DIR"
    if is_termux; then
        log_info "Termux: installing with pip..."
        "$SETUP_PYTHON" -m pip install --upgrade pip setuptools wheel
        "$SETUP_PIP" install -e ".[dev]"
    else
        log_info "Installing Python dependencies..."
        $UV_CMD pip install -e ".[dev]"
    fi
    log_ok "Core dependencies installed"
}

# ── Channel adapter install ─────────────────────────────────────────

install_channel_deps() {
    cd "$INSTALL_DIR"
    for ch in "${CHANNELS[@]}"; do
        CH_DIR="$INSTALL_DIR/clawhermes-${ch}"
        if [ -d "$CH_DIR" ] && [ -f "$CH_DIR/pyproject.toml" ]; then
            log_info "Installing clawhermes-${ch}..."
            if is_termux; then
                "$SETUP_PIP" install -e "$CH_DIR" > /tmp/clawhermes-pip-${ch}.log 2>&1 && \
                    log_ok "clawhermes-${ch}" || { log_warn "clawhermes-${ch} install failed"; tail -10 /tmp/clawhermes-pip-${ch}.log; }
            else
                $UV_CMD pip install -e "$CH_DIR" && log_ok "clawhermes-${ch}" || log_warn "clawhermes-${ch} install failed"
            fi
        else
            log_warn "clawhermes-${ch} not found, skipping"
        fi
    done
    if [ ${#CHANNELS[@]} -eq 0 ]; then
        log_info "No channel adapters selected (use --with-lark etc.)"
    fi
}

# ── PATH setup ──────────────────────────────────────────────────────

setup_path() {
    local link_dir
    link_dir="$(get_command_link_dir)"
    mkdir -p "$link_dir"
    local clw_bin="$INSTALL_DIR/.venv/bin/clawhermes"
    if [ -x "$clw_bin" ]; then
        ln -sf "$clw_bin" "$link_dir/clawhermes"
        log_ok "Symlinked clawhermes → $link_dir/clawhermes"
    fi

    if [ "$ROOT_FHS_LAYOUT" = false ] && ! is_termux; then
        local shell_config=""
        if [ -f "$HOME/.zshrc" ]; then shell_config="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then shell_config="$HOME/.bashrc"
        elif [ -f "$HOME/.bash_profile" ]; then shell_config="$HOME/.bash_profile"; fi
        if [ -n "$shell_config" ]; then
            if ! grep -q '\.local/bin' "$shell_config" 2>/dev/null; then
                echo "" >> "$shell_config"
                echo "# ClawHermes — ensure ~/.local/bin is on PATH" >> "$shell_config"
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_config"
                log_ok "Added ~/.local/bin to PATH in $shell_config"
            fi
        fi
    fi
}

# ── Config templates ────────────────────────────────────────────────

copy_config_templates() {
    log_info "Preparing config..."
    mkdir -p "$CLAWHERMES_HOME"

    # .env
    if [ ! -f "$CLAWHERMES_HOME/.env" ] && [ -f "$INSTALL_DIR/config/.env.example" ]; then
        cp "$INSTALL_DIR/config/.env.example" "$CLAWHERMES_HOME/.env"
        chmod 600 "$CLAWHERMES_HOME/.env" 2>/dev/null || true
        log_ok ".env created from template"
    elif [ -f "$CLAWHERMES_HOME/.env" ]; then
        chmod 600 "$CLAWHERMES_HOME/.env" 2>/dev/null || true
        log_ok ".env exists"
    fi

    # config.yaml
    if [ ! -f "$CLAWHERMES_HOME/config.yaml" ] && [ -f "$INSTALL_DIR/config/config.yaml.example" ]; then
        cp "$INSTALL_DIR/config/config.yaml.example" "$CLAWHERMES_HOME/config.yaml"
        log_ok "config.yaml created from template"
    fi

    # channels/
    mkdir -p "$CLAWHERMES_HOME/channels"
    for ch in "${CHANNELS[@]}"; do
        local ch_map="lark:feishu weixin:wechat qq:qq"
        local ch_name=""
        for pair in $ch_map; do
            [ "${pair%%:*}" = "$ch" ] && ch_name="${pair##*:}" && break
        done
        local src="$INSTALL_DIR/config/channels/${ch_name}.yaml.example"
        local dst="$CLAWHERMES_HOME/channels/${ch}.yaml"
        if [ -f "$src" ] && [ ! -f "$dst" ]; then
            cp "$src" "$dst"
            log_ok "channels/${ch}.yaml created"
        fi
    done
}

# ── Setup wizard ────────────────────────────────────────────────────

run_setup_wizard() {
    if [ "$RUN_SETUP" = false ]; then
        log_info "Skipping setup wizard (--skip-setup)"
        return 0
    fi
    local clw_cmd="$INSTALL_DIR/.venv/bin/clawhermes"
    if [ ! -x "$clw_cmd" ]; then
        clw_cmd="$(get_command_link_dir)/clawhermes"
    fi
    if [ -x "$clw_cmd" ]; then
        if [ -t 0 ]; then
            log_info "Starting setup wizard..."
            CH_DATA_DIR="$CLAWHERMES_HOME" "$clw_cmd" setup
        else
            log_info "Non-interactive terminal — skipping setup wizard"
            log_info "Run later: clawhermes setup"
        fi
    else
        log_warn "clawhermes CLI not found, skipping setup wizard"
    fi
}

# ── Gateway config ──────────────────────────────────────────────────

maybe_start_gateway() {
    log_info "Gateway service can be started with:"
    log_info "  clawhermes gateway start"
    log_info "  clawhermes gateway setup  # install as systemd/launchd service"
}

# ── Self-check ──────────────────────────────────────────────────────

run_self_check() {
    log_info "Running self-check..."
    local ok=true

    "$SETUP_PYTHON" -c "
import sys
print(f'  OK  Python {sys.version_info.major}.{sys.version_info.minor}')
" || { log_error "Python check failed"; ok=false; }

    for pkg in litellm fastapi rich yaml questionary; do
        "$SETUP_PYTHON" -c "import ${pkg//-/_}" 2>/dev/null && \
            log_ok "$pkg" || { log_error "$pkg missing"; ok=false; }
    done

    for ch in "${CHANNELS[@]}"; do
        "$SETUP_PYTHON" -c "import clawhermes_${ch}" 2>/dev/null && \
            log_ok "clawhermes-${ch}" || log_warn "clawhermes-${ch} import failed"
    done

    if [ "$ok" = true ]; then
        log_ok "Self-check passed"
    else
        log_warn "Some checks failed — run 'pip install -e \".[dev]\"' to fix"
    fi
}

# ── Print success ───────────────────────────────────────────────────

print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}🎉 ClawHermes installation complete!${NC}"
    echo ""
    echo "Data directory: $CLAWHERMES_HOME"
    echo "Install directory: $INSTALL_DIR"
    if [ "$USE_VENV" = true ]; then
        echo "Virtual env: $INSTALL_DIR/.venv"
    fi
    echo ""
    echo "Next steps:"
    echo "  clawhermes setup          # Configure API keys and channels"
    echo "  clawhermes gateway start  # Start the gateway"
    echo "  clawhermes doctor         # Diagnose issues"
    echo "  clawhermes --help         # Show all commands"
    echo ""
}

# ── Stage runner ────────────────────────────────────────────────────

require_install_dir() {
    if [ -z "$INSTALL_DIR" ] || [ ! -d "$INSTALL_DIR" ]; then
        log_error "Install directory not found: ${INSTALL_DIR:-<unset>}"
        log_info "The 'repository' stage must run before this one."
        return 1
    fi
    cd "$INSTALL_DIR"
}

run_stage_body() {
    local stage="$1"
    case "$stage" in
        prerequisites)
            print_banner
            detect_os
            resolve_install_layout
            install_uv
            check_python
            check_git
            ;;
        repository)
            detect_os
            resolve_install_layout
            check_git
            clone_repo
            ;;
        venv)
            detect_os
            resolve_install_layout
            require_install_dir
            install_uv
            check_python
            setup_venv
            ;;
        python-deps)
            detect_os
            resolve_install_layout
            require_install_dir
            install_python_deps
            ;;
        channel-deps)
            detect_os
            resolve_install_layout
            require_install_dir
            install_channel_deps
            ;;
        path)
            detect_os
            resolve_install_layout
            require_install_dir
            setup_path
            ;;
        config)
            detect_os
            resolve_install_layout
            require_install_dir
            copy_config_templates
            ;;
        setup)
            detect_os
            resolve_install_layout
            require_install_dir
            run_setup_wizard
            ;;
        gateway)
            detect_os
            resolve_install_layout
            require_install_dir
            maybe_start_gateway
            ;;
        complete)
            detect_os
            resolve_install_layout
            require_install_dir
            run_self_check
            print_success
            echo "git" > "$INSTALL_DIR/.install_method"
            ;;
        *)
            log_error "Unknown stage: $stage"
            return 2
            ;;
    esac
}

run_stage_protocol() {
    local stage="$1"
    if [ -z "$stage" ]; then
        log_error "--stage requires a stage name"
        [ "$JSON_OUTPUT" = true ] && emit_stage_json "" false false "missing stage name"
        return 2
    fi
    if [ "$NON_INTERACTIVE" = true ] && stage_needs_user_input "$stage"; then
        log_info "Skipping $stage (non-interactive)"
        [ "$JSON_OUTPUT" = true ] && emit_stage_json "$stage" true true
        return 0
    fi
    set +e
    ( run_stage_body "$stage" )
    local code=$?
    set -e
    if [ "$JSON_OUTPUT" = true ]; then
        [ "$code" -eq 0 ] && emit_stage_json "$stage" true false || emit_stage_json "$stage" false false "exit code $code"
    fi
    return "$code"
}

# ── Main ────────────────────────────────────────────────────────────

main() {
    print_banner
    detect_os
    resolve_install_layout
    install_uv
    check_python
    check_git
    clone_repo
    setup_venv
    install_python_deps
    install_channel_deps
    setup_path
    copy_config_templates
    run_setup_wizard
    maybe_start_gateway
    run_self_check
    print_success
    echo "git" > "$INSTALL_DIR/.install_method"
}

# ── Entry ───────────────────────────────────────────────────────────

if [ "$MANIFEST_MODE" = true ]; then
    emit_manifest
elif [ -n "$STAGE_NAME" ]; then
    run_stage_protocol "$STAGE_NAME"
else
    main
fi
