#!/usr/bin/env bash
# T7Patch Manager — One-shot installer (works on all major Linux distros)
#
# Supported package managers:
#   - pacman  (Arch, CachyOS, Manjaro, EndeavourOS, Garuda, …)
#   - apt     (Debian, Ubuntu, Pop!_OS, Mint, Zorin, …)
#   - dnf     (Fedora, RHEL, Rocky, Alma, Nobara, …)
#   - zypper  (openSUSE Tumbleweed / Leap)
#   - xbps    (Void Linux)
#   - apk     (Alpine)
#   - eopkg   (Solus)
# Fallback: prints the package names to install manually, then continues.
#
# What this does:
#   1. Detects your distro + package manager
#   2. Installs system dependencies (python, PyGObject, GTK 4, libadwaita, pipx)
#   3. Installs t7patch-manager via pipx --system-site-packages
#   4. Ensures ~/.local/bin is on your PATH (fish + bash + zsh)
#   5. Registers the desktop entry & icon
#   6. Offers to launch the app right away
#
# Usage:
#   ./install.sh              # normal install
#   ./install.sh --uninstall  # remove everything this installer put in place
#   ./install.sh --no-launch  # skip the "start now" prompt at the end
#   ./install.sh --skip-deps  # skip the system-package step (for advanced users)

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; BLUE=$'\e[34m'; DIM=$'\e[2m'; RESET=$'\e[0m'
else
    BOLD=""; GREEN=""; YELLOW=""; RED=""; BLUE=""; DIM=""; RESET=""
fi

info()  { printf "%s→%s %s\n" "$BLUE"  "$RESET" "$*"; }
ok()    { printf "%s✓%s %s\n" "$GREEN" "$RESET" "$*"; }
warn()  { printf "%s!%s %s\n" "$YELLOW" "$RESET" "$*"; }
fail()  { printf "%s✗%s %s\n" "$RED"   "$RESET" "$*" >&2; exit 1; }
header(){ printf "\n%s%s%s\n" "$BOLD" "$*" "$RESET"; }

# ── Paths ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
DESKTOP_SRC="$SCRIPT_DIR/data/io.github.heyiamusingarchbtw.T7PatchManager.desktop"
ICON_SRC="$SCRIPT_DIR/data/io.github.heyiamusingarchbtw.T7PatchManager.svg"
DESKTOP_DST="$HOME/.local/share/applications/io.github.heyiamusingarchbtw.T7PatchManager.desktop"
ICON_DST="$HOME/.local/share/icons/hicolor/scalable/apps/io.github.heyiamusingarchbtw.T7PatchManager.svg"

MODE="install"
LAUNCH=1
SKIP_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --uninstall) MODE="uninstall" ;;
        --no-launch) LAUNCH=0 ;;
        --skip-deps) SKIP_DEPS=1 ;;
        -h|--help)
            sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) fail "Unknown option: $arg (try --help)" ;;
    esac
done

# ── Sanity checks ───────────────────────────────────────────────────
if [[ $EUID -eq 0 ]]; then
    fail "Don't run this as root. It installs into your \$HOME.
   The script will call sudo itself only when installing system packages."
fi

if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    fail "install.sh must be run from the t7patch-manager repo root."
fi

# ── Package-manager detection ───────────────────────────────────────
# For each PM we know:
#   PM_NAME        — human name
#   PM_INSTALL     — command to install a list of packages (needs sudo)
#   PM_QUERY       — command that succeeds iff a package is installed
#   PKG_*          — distro-specific package names
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

# Distro pretty-name for the log
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    DISTRO_NAME=$( . /etc/os-release; echo "${PRETTY_NAME:-$NAME}" )
else
    DISTRO_NAME="unknown Linux"
fi

# Map generic dep-names → distro-specific package names
case "$PM" in
    pacman)
        PM_NAME="pacman"
        PM_INSTALL=(sudo pacman -S --needed --noconfirm)
        PM_QUERY(){ pacman -Qi "$1" &>/dev/null; }
        DEPS=(python python-gobject gtk4 libadwaita python-pipx)
        ;;
    apt)
        PM_NAME="APT"
        PM_INSTALL=(sudo apt-get install -y)
        PM_QUERY(){ dpkg -s "$1" &>/dev/null; }
        # python3-gi already pulls in libgirepository; gir1.2-adw-1 gives libadwaita bindings
        DEPS=(python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 pipx)
        ;;
    dnf)
        PM_NAME="dnf"
        PM_INSTALL=(sudo dnf install -y)
        PM_QUERY(){ rpm -q "$1" &>/dev/null; }
        DEPS=(python3 python3-gobject gtk4 libadwaita pipx)
        ;;
    zypper)
        PM_NAME="zypper"
        PM_INSTALL=(sudo zypper --non-interactive install)
        PM_QUERY(){ rpm -q "$1" &>/dev/null; }
        DEPS=(python3 python3-gobject gtk4 libadwaita python3-pipx)
        ;;
    xbps)
        PM_NAME="XBPS"
        PM_INSTALL=(sudo xbps-install -Sy)
        PM_QUERY(){ xbps-query -e "$1" &>/dev/null; }
        DEPS=(python3 python3-gobject gtk4 libadwaita python3-pipx)
        ;;
    apk)
        PM_NAME="apk"
        PM_INSTALL=(sudo apk add --no-cache)
        PM_QUERY(){ apk info -e "$1" &>/dev/null; }
        DEPS=(python3 py3-gobject3 gtk4.0 libadwaita py3-pipx)
        ;;
    eopkg)
        PM_NAME="eopkg"
        PM_INSTALL=(sudo eopkg install -y)
        PM_QUERY(){ eopkg info "$1" 2>/dev/null | grep -q "Installed"; }
        DEPS=(python3 python-gobject libgtk-4 libadwaita python-pipx)
        ;;
    unknown)
        PM_NAME="unknown"
        DEPS=()
        ;;
esac

# ── Uninstall path ──────────────────────────────────────────────────
if [[ "$MODE" == "uninstall" ]]; then
    header "Uninstalling T7Patch Manager"
    if command -v pipx &>/dev/null && pipx list --short 2>/dev/null | grep -q '^t7patch-manager '; then
        info "Removing pipx package…"
        pipx uninstall t7patch-manager >/dev/null && ok "pipx package removed"
    else
        warn "pipx package not installed — skipping"
    fi
    for f in "$DESKTOP_DST" "$ICON_DST"; do
        if [[ -f "$f" ]]; then rm -f "$f" && ok "Removed $f"; fi
    done
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$HOME/.local/share/applications" &>/dev/null || true
    fi
    ok "Done."
    exit 0
fi

# ── Install path ────────────────────────────────────────────────────
header "T7Patch Manager — Installer"
info "Distro:          $DISTRO_NAME"
info "Package manager: $PM_NAME"

# 1. System dependencies
header "Step 1/4 — System dependencies"

if (( SKIP_DEPS )); then
    warn "Skipping dependency install (--skip-deps). Make sure these are present:"
    printf "   • GTK 4\n   • libadwaita\n   • Python 3.11+\n   • PyGObject (python3-gi / python-gobject)\n   • pipx\n"
elif [[ "$PM" == "unknown" ]]; then
    warn "No supported package manager detected."
    cat <<EOF

  Please install these dependencies manually with your distro's package manager,
  then re-run this installer with --skip-deps:

    • Python 3.11+          (typically: python3)
    • PyGObject bindings    (typically: python3-gi, python-gobject, or py3-gobject3)
    • GTK 4                 (typically: gtk4)
    • libadwaita            (typically: libadwaita)
    • pipx                  (typically: pipx or python3-pipx)

EOF
    printf "Continue anyway (assumes deps are already installed)? [y/N] "
    read -r reply
    [[ "$reply" =~ ^[Yy]$ ]] || exit 1
else
    MISSING=()
    for pkg in "${DEPS[@]}"; do
        if PM_QUERY "$pkg"; then
            ok "$pkg (already installed)"
        else
            MISSING+=("$pkg")
        fi
    done

    if (( ${#MISSING[@]} > 0 )); then
        info "Installing missing packages via $PM_NAME: ${MISSING[*]}"
        # For apt, refresh the index first
        if [[ "$PM" == "apt" ]]; then
            sudo apt-get update -qq || warn "apt-get update failed — trying install anyway"
        fi
        if ! "${PM_INSTALL[@]}" "${MISSING[@]}"; then
            fail "$PM_NAME failed. Please install manually: ${MISSING[*]}"
        fi
        ok "All dependencies installed"
    else
        ok "All dependencies already present"
    fi
fi

# Verify what we actually need at runtime, regardless of PM
info "Verifying runtime prerequisites…"
if ! command -v python3 &>/dev/null; then
    fail "python3 not found. Install Python 3.11+ and re-run."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "  python3 → $PY_VER"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "Python 3.11+ required; you have $PY_VER."
fi
if ! python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); from gi.repository import Gtk, Adw' 2>/dev/null; then
    fail "GTK 4 + libadwaita Python bindings not importable.
   Install your distro's PyGObject + GTK 4 + libadwaita packages and re-run."
fi
ok "PyGObject + GTK 4 + libadwaita import OK"

if ! command -v pipx &>/dev/null; then
    fail "pipx not found. Install your distro's pipx package (or run: python3 -m pip install --user pipx)."
fi
ok "pipx found: $(pipx --version)"

# 2. PATH check for ~/.local/bin (pipx installs binaries there)
header "Step 2/4 — Shell PATH"
LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    warn "$LOCAL_BIN is not on your PATH yet."
    USER_SHELL=$(basename "${SHELL:-bash}")
    case "$USER_SHELL" in
        fish)
            CONFIG="$HOME/.config/fish/config.fish"
            mkdir -p "$(dirname "$CONFIG")"
            touch "$CONFIG"
            if ! grep -q "fish_add_path.*\\.local/bin" "$CONFIG" 2>/dev/null; then
                {
                    echo ""
                    echo "# Added by t7patch-manager installer"
                    echo "fish_add_path -a \$HOME/.local/bin"
                } >> "$CONFIG"
                ok "Added ~/.local/bin to fish PATH ($CONFIG)"
            fi
            ;;
        bash|zsh)
            CONFIG="$HOME/.${USER_SHELL}rc"
            touch "$CONFIG"
            if ! grep -q "\\.local/bin" "$CONFIG" 2>/dev/null; then
                {
                    echo ""
                    echo "# Added by t7patch-manager installer"
                    echo 'export PATH="$HOME/.local/bin:$PATH"'
                } >> "$CONFIG"
                ok "Added ~/.local/bin to \$PATH ($CONFIG)"
            fi
            ;;
        *)
            warn "Unknown shell '$USER_SHELL'. Add \$HOME/.local/bin to your PATH manually."
            ;;
    esac
    export PATH="$LOCAL_BIN:$PATH"
else
    ok "~/.local/bin is on PATH"
fi

# Try to ensure pipx's own paths too (idempotent, quiet)
pipx ensurepath >/dev/null 2>&1 || true

# 3. Install via pipx
header "Step 3/4 — Installing t7patch-manager"
if pipx list --short 2>/dev/null | grep -q '^t7patch-manager '; then
    info "Already installed — upgrading in place…"
    pipx uninstall t7patch-manager >/dev/null 2>&1 || true
fi
if ! pipx install --system-site-packages "$SCRIPT_DIR"; then
    fail "pipx install failed. Check the output above for details."
fi
ok "t7patch-manager installed"

# 4. Desktop entry + icon
header "Step 4/4 — Desktop integration"
mkdir -p "$(dirname "$DESKTOP_DST")" "$(dirname "$ICON_DST")"
install -Dm644 "$DESKTOP_SRC" "$DESKTOP_DST"
install -Dm644 "$ICON_SRC" "$ICON_DST"
ok "Desktop entry installed → $DESKTOP_DST"
ok "Icon installed → $ICON_DST"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$HOME/.local/share/applications" &>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# ── Done ────────────────────────────────────────────────────────────
header "Done."
cat <<EOF

  ${GREEN}${BOLD}T7Patch Manager is installed.${RESET}

  Start it from your app menu, or run:  ${BOLD}t7patch-manager${RESET}

  ${DIM}One last step you'll need to do in Steam (only once):${RESET}
  Right-click BO3 in Steam → Properties → Launch options →

    ${BOLD}WINEDLLOVERRIDES="dsound=n,b" %command%${RESET}

  ${DIM}The app will remind you of this on its main screen too.${RESET}

EOF

if (( LAUNCH )); then
    if command -v t7patch-manager &>/dev/null; then
        printf "Start T7Patch Manager now? [Y/n] "
        read -r reply
        if [[ ! "$reply" =~ ^[Nn]$ ]]; then
            info "Launching…"
            (nohup t7patch-manager >/dev/null 2>&1 &) || true
        fi
    fi
fi
