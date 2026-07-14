#!/usr/bin/env bash
# T7Patch Manager — One-shot installer with fallbacks (all major Linux distros)
#
# Supported package managers:
#   pacman  · apt  · dnf  · zypper  · xbps  · apk  · eopkg
# Unknown package manager? --skip-deps + manual install works too.
#
# Modes:
#   ./install.sh              # install (default)
#   ./install.sh --uninstall  # remove everything this installer put in place
#   ./install.sh --diagnose   # check env; don't install anything
#   ./install.sh --no-launch  # skip the "start now" prompt at the end
#   ./install.sh --skip-deps  # skip system-package step
#   ./install.sh --use-pip    # skip pipx; use ~/.venv (last-resort fallback)

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; BLUE=$'\e[34m'; DIM=$'\e[2m'; RESET=$'\e[0m'
else
    BOLD=""; GREEN=""; YELLOW=""; RED=""; BLUE=""; DIM=""; RESET=""
fi

info()  { printf "%s→%s %s\n" "$BLUE"   "$RESET" "$*"; }
ok()    { printf "%s✓%s %s\n" "$GREEN"  "$RESET" "$*"; }
warn()  { printf "%s!%s %s\n" "$YELLOW" "$RESET" "$*"; }
fail()  { printf "%s✗%s %s\n" "$RED"    "$RESET" "$*" >&2; exit 1; }
header(){ printf "\n%s%s%s\n" "$BOLD" "$*" "$RESET"; }

# ── Paths ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
DESKTOP_SRC="$SCRIPT_DIR/data/io.github.heyiamusingarchbtw.T7PatchManager.desktop"
ICON_SRC="$SCRIPT_DIR/data/io.github.heyiamusingarchbtw.T7PatchManager.svg"
DESKTOP_DST="$HOME/.local/share/applications/io.github.heyiamusingarchbtw.T7PatchManager.desktop"
ICON_DST="$HOME/.local/share/icons/hicolor/scalable/apps/io.github.heyiamusingarchbtw.T7PatchManager.svg"
VENV_DIR="$HOME/.local/share/t7patch-manager/venv"

MODE="install"
LAUNCH=1
SKIP_DEPS=0
USE_PIP=0
DIAGNOSE=0
for arg in "$@"; do
    case "$arg" in
        --uninstall) MODE="uninstall" ;;
        --no-launch) LAUNCH=0 ;;
        --skip-deps) SKIP_DEPS=1 ;;
        --use-pip)   USE_PIP=1 ;;
        --diagnose)  MODE="diagnose"; DIAGNOSE=1 ;;
        -h|--help)
            sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) fail "Unknown option: $arg (try --help)" ;;
    esac
done

# ── Sanity ──────────────────────────────────────────────────────────
if [[ $EUID -eq 0 && "$MODE" != "diagnose" ]]; then
    fail "Don't run this as root. sudo is only used when installing system packages."
fi
if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    fail "install.sh must be run from the t7patch-manager repo root."
fi

# ── Distro / PM detection ───────────────────────────────────────────
detect_pm() {
    if   command -v pacman &>/dev/null; then PM=pacman
    elif command -v apt-get &>/dev/null; then PM=apt
    elif command -v dnf   &>/dev/null;  then PM=dnf
    elif command -v zypper &>/dev/null; then PM=zypper
    elif command -v xbps-install &>/dev/null; then PM=xbps
    elif command -v apk   &>/dev/null;  then PM=apk
    elif command -v eopkg &>/dev/null;  then PM=eopkg
    else PM="unknown"
    fi
}
detect_pm

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    DISTRO_NAME=$( . /etc/os-release; echo "${PRETTY_NAME:-$NAME}" )
else
    DISTRO_NAME="unknown Linux"
fi

case "$PM" in
    pacman)
        PM_NAME="pacman"
        PM_INSTALL=(sudo pacman -S --needed --noconfirm)
        pm_query(){ pacman -Qi "$1" &>/dev/null; }
        DEPS=(python python-gobject gtk4 libadwaita python-pipx)
        ;;
    apt)
        PM_NAME="APT"
        PM_INSTALL=(sudo apt-get install -y)
        pm_query(){ dpkg -s "$1" &>/dev/null; }
        DEPS=(python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 pipx)
        ;;
    dnf)
        PM_NAME="dnf"
        PM_INSTALL=(sudo dnf install -y)
        pm_query(){ rpm -q "$1" &>/dev/null; }
        DEPS=(python3 python3-gobject gtk4 libadwaita pipx)
        ;;
    zypper)
        PM_NAME="zypper"
        PM_INSTALL=(sudo zypper --non-interactive install)
        pm_query(){ rpm -q "$1" &>/dev/null; }
        DEPS=(python3 python3-gobject gtk4 libadwaita python3-pipx)
        ;;
    xbps)
        PM_NAME="XBPS"
        PM_INSTALL=(sudo xbps-install -Sy)
        pm_query(){ xbps-query -e "$1" &>/dev/null; }
        DEPS=(python3 python3-gobject gtk4 libadwaita python3-pipx)
        ;;
    apk)
        PM_NAME="apk"
        PM_INSTALL=(sudo apk add --no-cache)
        pm_query(){ apk info -e "$1" &>/dev/null; }
        DEPS=(python3 py3-gobject3 gtk4.0 libadwaita py3-pipx)
        ;;
    eopkg)
        PM_NAME="eopkg"
        PM_INSTALL=(sudo eopkg install -y)
        pm_query(){ eopkg info "$1" 2>/dev/null | grep -q "Installed"; }
        DEPS=(python3 python-gobject libgtk-4 libadwaita python-pipx)
        ;;
    unknown)
        PM_NAME="unknown"
        PM_INSTALL=()
        pm_query(){ return 1; }
        DEPS=()
        ;;
esac

# ── Diagnose mode: just print a full status report ──────────────────
if [[ "$MODE" == "diagnose" ]]; then
    header "T7Patch Manager — Diagnostics"
    info "Distro:          $DISTRO_NAME"
    info "Package manager: $PM_NAME"
    info "Shell:           ${SHELL:-unknown}"
    info "PATH contains ~/.local/bin: $([[ ":$PATH:" == *":$HOME/.local/bin:"* ]] && echo yes || echo no)"

    header "Python"
    if command -v python3 &>/dev/null; then
        ok "python3 → $(python3 -c 'import sys; print(sys.version.split()[0])')"
        python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
            && ok "Python 3.11+ OK" || warn "Python < 3.11 detected"
    else
        warn "python3 not found"
    fi

    header "GTK 4 + libadwaita + PyGObject"
    if python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); from gi.repository import Gtk, Adw' 2>/dev/null; then
        ok "GTK4 + libadwaita importable via PyGObject"
    else
        warn "PyGObject / GTK4 / libadwaita cannot be imported"
        python3 -c 'import gi; print("  gi module:", gi.__file__)' 2>&1 | sed 's/^/   /' || true
    fi

    header "Package managers"
    for pm in pacman apt-get dnf zypper xbps-install apk eopkg pipx pip; do
        if command -v $pm &>/dev/null; then ok "$pm → $(command -v $pm)"; else printf "  %s%s%s not found\n" "$DIM" "$pm" "$RESET"; fi
    done

    header "T7Patch Manager"
    if command -v t7patch-manager &>/dev/null; then
        ok "installed → $(command -v t7patch-manager)"
    else
        printf "  not installed\n"
    fi
    if [[ -d "$VENV_DIR" ]]; then ok "fallback venv exists at $VENV_DIR"; fi
    for f in "$DESKTOP_DST" "$ICON_DST"; do
        [[ -f "$f" ]] && ok "present: $f" || printf "  missing: %s\n" "$f"
    done

    header "Steam"
    STEAM_ROOTS=(
        "$HOME/.steam/steam"
        "$HOME/.steam/root"
        "$HOME/.local/share/Steam"
        "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam"
        "$HOME/.var/app/com.valvesoftware.Steam/data/Steam"
        "$HOME/snap/steam/common/.local/share/Steam"
        "$HOME/snap/steam/common/.steam/steam"
    )
    FOUND_STEAM=0
    for r in "${STEAM_ROOTS[@]}"; do
        if [[ -d "$r/steamapps" ]]; then
            ok "$r"
            FOUND_STEAM=1
            [[ -d "$r/steamapps/common/Call of Duty Black Ops III" ]] && \
                ok "  → BO3 install found here"
        fi
    done
    (( FOUND_STEAM )) || warn "No Steam installation found in known locations."

    printf "\n%sDiagnostics complete.%s Nothing was changed on your system.\n\n" "$BOLD" "$RESET"
    exit 0
fi

# ── Uninstall path ──────────────────────────────────────────────────
if [[ "$MODE" == "uninstall" ]]; then
    header "Uninstalling T7Patch Manager"
    if command -v pipx &>/dev/null && pipx list --short 2>/dev/null | grep -q '^t7patch-manager '; then
        pipx uninstall t7patch-manager >/dev/null && ok "pipx package removed"
    fi
    if [[ -d "$VENV_DIR" ]]; then
        rm -rf "$VENV_DIR" && ok "Fallback venv removed"
        # symlink cleanup
        [[ -L "$HOME/.local/bin/t7patch-manager" ]] && rm -f "$HOME/.local/bin/t7patch-manager"
    fi
    for f in "$DESKTOP_DST" "$ICON_DST"; do
        [[ -f "$f" ]] && rm -f "$f" && ok "Removed $f"
    done
    command -v update-desktop-database &>/dev/null && \
        update-desktop-database "$HOME/.local/share/applications" &>/dev/null || true
    ok "Done."
    exit 0
fi

# ── Install path ────────────────────────────────────────────────────
header "T7Patch Manager — Installer"
info "Distro:          $DISTRO_NAME"
info "Package manager: $PM_NAME"

# 1. System deps
header "Step 1/4 — System dependencies"
if (( SKIP_DEPS )); then
    warn "Skipping dependency install (--skip-deps)."
elif [[ "$PM" == "unknown" ]]; then
    warn "No supported package manager detected."
    cat <<EOF

  Install manually, then re-run with --skip-deps:
    • Python 3.11+       (python3)
    • PyGObject          (python3-gi / python-gobject / py3-gobject3)
    • GTK 4              (gtk4)
    • libadwaita         (libadwaita, plus gir1.2-adw-1 on Debian/Ubuntu)
    • pipx               (pipx or python3-pipx)

EOF
    printf "Continue anyway? [y/N] "
    read -r reply
    [[ "$reply" =~ ^[Yy]$ ]] || exit 1
else
    MISSING=()
    for pkg in "${DEPS[@]}"; do
        if pm_query "$pkg"; then ok "$pkg"; else MISSING+=("$pkg"); fi
    done
    if (( ${#MISSING[@]} > 0 )); then
        info "Installing: ${MISSING[*]}"
        if [[ "$PM" == "apt" ]]; then
            sudo apt-get update -qq || warn "apt-get update failed — trying install anyway"
        fi
        if ! "${PM_INSTALL[@]}" "${MISSING[@]}"; then
            warn "$PM_NAME failed. Trying to continue in case core deps are present."
        else
            ok "All dependencies installed"
        fi
    else
        ok "All dependencies already present"
    fi
fi

# Runtime verification (independent of PM)
info "Verifying runtime prerequisites…"
command -v python3 &>/dev/null || fail "python3 not found. Install Python 3.11+ and re-run."
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "python3 → $PY_VER"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || fail "Python 3.11+ required; you have $PY_VER."
if ! python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); from gi.repository import Gtk, Adw' 2>/dev/null; then
    warn "GTK 4 + libadwaita Python bindings are not importable."
    cat <<EOF

  The app will not run without these. Install your distro's PyGObject +
  GTK 4 + libadwaita packages. Then re-run:  ./install.sh
  Or run:  ./install.sh --diagnose  for a detailed check.

EOF
    fail "Aborting install."
fi
ok "PyGObject + GTK 4 + libadwaita import OK"

# 2. Shell PATH
header "Step 2/4 — Shell PATH"
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    USER_SHELL=$(basename "${SHELL:-bash}")
    case "$USER_SHELL" in
        fish)
            CFG="$HOME/.config/fish/config.fish"; mkdir -p "$(dirname "$CFG")"; touch "$CFG"
            if ! grep -q "fish_add_path.*\\.local/bin" "$CFG" 2>/dev/null; then
                { echo ""; echo "# Added by t7patch-manager installer"; echo "fish_add_path -a \$HOME/.local/bin"; } >> "$CFG"
                ok "Added ~/.local/bin to fish PATH"
            fi
            ;;
        bash|zsh)
            CFG="$HOME/.${USER_SHELL}rc"; touch "$CFG"
            if ! grep -q "\\.local/bin" "$CFG" 2>/dev/null; then
                { echo ""; echo "# Added by t7patch-manager installer"; echo 'export PATH="$HOME/.local/bin:$PATH"'; } >> "$CFG"
                ok "Added ~/.local/bin to \$PATH"
            fi
            ;;
        *) warn "Add \$HOME/.local/bin to your PATH manually (unknown shell: $USER_SHELL)." ;;
    esac
    export PATH="$LOCAL_BIN:$PATH"
else
    ok "~/.local/bin is on PATH"
fi

# 3. Install
header "Step 3/4 — Installing t7patch-manager"

install_via_pipx() {
    command -v pipx &>/dev/null || return 1
    pipx list --short 2>/dev/null | grep -q '^t7patch-manager ' && pipx uninstall t7patch-manager &>/dev/null || true
    pipx install --system-site-packages "$SCRIPT_DIR"
}

install_via_venv() {
    info "Falling back to a manually-managed venv at $VENV_DIR"
    mkdir -p "$(dirname "$VENV_DIR")"
    rm -rf "$VENV_DIR"
    if ! python3 -m venv --system-site-packages "$VENV_DIR"; then
        return 1
    fi
    "$VENV_DIR/bin/pip" install --upgrade pip &>/dev/null || true
    if ! "$VENV_DIR/bin/pip" install "$SCRIPT_DIR"; then
        return 1
    fi
    # Symlink the CLI onto PATH
    ln -sf "$VENV_DIR/bin/t7patch-manager" "$LOCAL_BIN/t7patch-manager"
    return 0
}

INSTALLED=0
if (( ! USE_PIP )); then
    if install_via_pipx; then
        ok "Installed via pipx"
        INSTALLED=1
    else
        warn "pipx install failed — falling back to python venv"
    fi
fi
if (( ! INSTALLED )); then
    if install_via_venv; then
        ok "Installed via venv → $VENV_DIR"
        INSTALLED=1
    else
        fail "Both pipx and venv install methods failed. Run ./install.sh --diagnose"
    fi
fi

command -v t7patch-manager &>/dev/null || fail "t7patch-manager not on PATH after install. Restart your shell."

# 4. Desktop integration
header "Step 4/4 — Desktop integration"
mkdir -p "$(dirname "$DESKTOP_DST")" "$(dirname "$ICON_DST")"
install -Dm644 "$DESKTOP_SRC" "$DESKTOP_DST"
install -Dm644 "$ICON_SRC" "$ICON_DST"
ok "Desktop entry + icon installed"
command -v update-desktop-database &>/dev/null && update-desktop-database "$HOME/.local/share/applications" &>/dev/null || true
command -v gtk-update-icon-cache &>/dev/null && gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

# ── Done ────────────────────────────────────────────────────────────
header "Done."
cat <<EOF

  ${GREEN}${BOLD}T7Patch Manager is installed.${RESET}

  Start it from your app menu, or run:  ${BOLD}t7patch-manager${RESET}

  ${DIM}Steam launch options for BO3 (only once):${RESET}
    ${BOLD}WINEDLLOVERRIDES="dsound=n,b" %command%${RESET}

  ${DIM}Troubleshooting:${RESET}  ./install.sh --diagnose

EOF

if (( LAUNCH )) && command -v t7patch-manager &>/dev/null; then
    printf "Start T7Patch Manager now? [Y/n] "
    read -r reply
    if [[ ! "$reply" =~ ^[Nn]$ ]]; then
        (nohup t7patch-manager >/dev/null 2>&1 &) || true
    fi
fi
