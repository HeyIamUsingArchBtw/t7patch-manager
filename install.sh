#!/usr/bin/env bash
# T7Patch Manager — One-shot installer for Arch-based Linux distros
# (CachyOS, Arch, Manjaro, EndeavourOS, Garuda, …)
#
# What this does:
#   1. Checks you're on a supported (pacman-based) distro
#   2. Installs system dependencies via pacman  (python-gobject, gtk4, libadwaita, pipx)
#   3. Installs t7patch-manager itself via pipx --system-site-packages
#   4. Ensures ~/.local/bin is on your PATH (fish + bash + zsh)
#   5. Registers the desktop entry & icon so it shows up in your app menu
#   6. Offers to launch the app right away
#
# Usage:
#   ./install.sh              # normal install
#   ./install.sh --uninstall  # remove everything this installer put in place
#   ./install.sh --no-launch  # skip the "start now" prompt at the end

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
for arg in "$@"; do
    case "$arg" in
        --uninstall) MODE="uninstall" ;;
        --no-launch) LAUNCH=0 ;;
        -h|--help)
            sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) fail "Unknown option: $arg (try --help)" ;;
    esac
done

# ── Sanity checks ───────────────────────────────────────────────────
if [[ $EUID -eq 0 ]]; then
    fail "Don't run this as root. It installs into your \$HOME."
fi

if ! command -v pacman &>/dev/null; then
    fail "This installer only supports Arch-based distros (CachyOS, Arch, Manjaro, …).
   On other distros, please follow the manual instructions in README.md."
fi

if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    fail "install.sh must be run from the t7patch-manager repo root."
fi

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
info "Detected distro: $(source /etc/os-release && echo "$PRETTY_NAME")"

# 1. System dependencies via pacman
header "Step 1/4 — System dependencies"
PACMAN_DEPS=(python python-gobject gtk4 libadwaita python-pipx)
MISSING=()
for pkg in "${PACMAN_DEPS[@]}"; do
    if pacman -Qi "$pkg" &>/dev/null; then
        ok "$pkg (already installed)"
    else
        MISSING+=("$pkg")
    fi
done

if (( ${#MISSING[@]} > 0 )); then
    info "Installing missing packages: ${MISSING[*]}"
    if ! sudo pacman -S --needed --noconfirm "${MISSING[@]}"; then
        fail "pacman failed. Please install manually: ${MISSING[*]}"
    fi
    ok "All pacman dependencies installed"
else
    ok "All pacman dependencies already present"
fi

# 2. PATH check for ~/.local/bin (pipx installs binaries there)
header "Step 2/4 — Shell PATH"
LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    warn "$LOCAL_BIN is not on your PATH yet."
    # Detect user shell and offer to fix it
    USER_SHELL=$(basename "${SHELL:-bash}")
    case "$USER_SHELL" in
        fish)
            CONFIG="$HOME/.config/fish/config.fish"
            mkdir -p "$(dirname "$CONFIG")"
            if ! grep -q "fish_add_path.*\\.local/bin" "$CONFIG" 2>/dev/null; then
                echo "" >> "$CONFIG"
                echo "# Added by t7patch-manager installer" >> "$CONFIG"
                echo "fish_add_path -a \$HOME/.local/bin" >> "$CONFIG"
                ok "Added ~/.local/bin to fish PATH ($CONFIG)"
            fi
            ;;
        bash|zsh)
            CONFIG="$HOME/.${USER_SHELL}rc"
            if ! grep -q "\\.local/bin" "$CONFIG" 2>/dev/null; then
                echo "" >> "$CONFIG"
                echo "# Added by t7patch-manager installer" >> "$CONFIG"
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CONFIG"
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
            # detach so the installer exits cleanly
            (nohup t7patch-manager >/dev/null 2>&1 &) || true
        fi
    fi
fi
