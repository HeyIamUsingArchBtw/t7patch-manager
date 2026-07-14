"""Find the BO3 install path via Steam's libraryfolders.vdf."""
from __future__ import annotations
import re
from pathlib import Path

BO3_APPID = "311210"
BO3_INSTALLDIR = "Call of Duty Black Ops III"

_STEAM_ROOTS = [
    Path.home() / ".steam" / "steam",
    Path.home() / ".local" / "share" / "Steam",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
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
    text = vdf.read_text(errors="ignore")
    # libraryfolders.vdf: quoted key/value, we just want every "path" line
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


def config_dir() -> Path:
    """XDG config dir for this app."""
    base = Path.home() / ".config"
    d = base / "t7patch-manager"
    d.mkdir(parents=True, exist_ok=True)
    return d
