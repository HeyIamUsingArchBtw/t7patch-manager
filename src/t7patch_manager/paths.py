"""Find the BO3 install path via Steam's libraryfolders.vdf.

Falls back through a growing list of possible Steam roots (native, Snap,
Flatpak) and returns None if nothing works — in which case the UI shows a
manual-override option in Preferences.
"""
from __future__ import annotations
import re
from pathlib import Path

BO3_APPID = "311210"
BO3_INSTALLDIR = "Call of Duty Black Ops III"

# Every known place Steam might live, in the order most-likely first.
_STEAM_ROOTS = [
    Path.home() / ".steam" / "steam",
    Path.home() / ".steam" / "root",
    Path.home() / ".local" / "share" / "Steam",
    # Flatpak
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
    # Snap
    Path.home() / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
    Path.home() / "snap" / "steam" / "common" / ".steam" / "steam",
]


def _steam_root() -> Path | None:
    for r in _STEAM_ROOTS:
        if (r / "steamapps").is_dir():
            return r
    return None


def _library_paths(steam_root: Path) -> list[Path]:
    """Read Steam's libraryfolders.vdf and return every library root."""
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return [steam_root]
    try:
        text = vdf.read_text(errors="ignore")
    except OSError:
        return [steam_root]
    paths = re.findall(r'"path"\s+"([^"]+)"', text)
    libs = [Path(p) for p in paths]
    if steam_root not in libs:
        libs.insert(0, steam_root)
    return libs


def find_bo3_dir() -> Path | None:
    """Return the absolute path of the BO3 install folder, or None."""
    root = _steam_root()
    if not root:
        return None
    for lib in _library_paths(root):
        candidate = lib / "steamapps" / "common" / BO3_INSTALLDIR
        if candidate.is_dir():
            return candidate
    return None


def scan_all_steam_roots() -> list[Path]:
    """List every Steam root we could find on this system (for diagnostics)."""
    return [r for r in _STEAM_ROOTS if (r / "steamapps").is_dir()]


def looks_like_bo3(path: Path) -> bool:
    """Sanity-check a user-supplied path — does it look like a BO3 install?"""
    if not path.is_dir():
        return False
    markers = ("BlackOps3.exe", "steam_appid.txt", "main")
    return any((path / m).exists() for m in markers)


def config_dir() -> Path:
    """XDG config dir for this app."""
    base = Path.home() / ".config"
    d = base / "t7patch-manager"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    """Where we write the running log for the debug viewer."""
    return config_dir() / "t7patch-manager.log"
