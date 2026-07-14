"""Find the BO3 install path via Steam's libraryfolders.vdf.

Uses :mod:`steam_roots` for the Steam-install search, then walks every
library folder Steam knows about (Steam stores those in
``steamapps/libraryfolders.vdf``). Non-Steam installs (Lutris, Heroic,
Bottles, plain ``~/Games/…``) are picked up too so users who never bought
BO3 through Steam still get auto-detected.

Returns None if nothing works — in which case the UI shows a manual
override in Preferences.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .steam_roots import existing_roots

BO3_APPID = "311210"
BO3_INSTALLDIR = "Call of Duty Black Ops III"

# Alternate directory names we've seen users end up with. Steam always
# writes exactly ``Call of Duty Black Ops III`` — the alternates only
# matter for manual / Non-Steam installs where the user picked the name.
_BO3_DIR_ALTS: tuple[str, ...] = (
    BO3_INSTALLDIR,
    "Call of Duty - Black Ops III",
    "Call of Duty Black Ops 3",
    "Black Ops III",
    "Black Ops 3",
    "BlackOps3",
    "BO3",
)


def _steam_root() -> Path | None:
    """Return the first Steam root that exists, or ``None``."""
    roots = existing_roots()
    return roots[0] if roots else None


def _library_paths(steam_root: Path) -> list[Path]:
    """Read Steam's libraryfolders.vdf and return every library root.

    Silently drops libraries whose ``path`` no longer exists on disk —
    Steam keeps stale entries around after external drives are unplugged
    or reformatted, and we don't want ``steamapps/common/…`` lookups
    exploding when those turn up.
    """
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return [steam_root]
    try:
        text = vdf.read_text(errors="ignore")
    except OSError:
        return [steam_root]
    libs: list[Path] = []
    seen: set[Path] = set()
    # Include the Steam root itself first (Steam always treats its own
    # install dir as library index 0, but sometimes the VDF entry uses
    # a differently-cased path — this way we never miss it).
    libs.append(steam_root)
    seen.add(_resolve_or(steam_root))
    for p in re.findall(r'"path"\s+"([^"]+)"', text):
        # Steam escapes backslashes in the VDF text form.
        candidate = Path(p.replace("\\\\", "\\").replace("\\/", "/"))
        try:
            key = candidate.resolve()
        except OSError:
            key = candidate
        if key in seen:
            continue
        if not candidate.is_dir():
            continue
        seen.add(key)
        libs.append(candidate)
    return libs


def _resolve_or(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


def _find_case_insensitive(parent: Path, name: str) -> Path | None:
    """Return the child of *parent* whose name matches *name* ignoring case.

    Files on ext4/btrfs/xfs are case-sensitive but a BO3 folder that was
    once copied off an NTFS drive can end up with weird casing like
    ``Call of duty black ops III``. This lets our detection survive that.
    """
    if not parent.is_dir():
        return None
    lo = name.lower()
    try:
        for child in parent.iterdir():
            if child.name.lower() == lo:
                return child
    except OSError:
        return None
    return None


def _bo3_in_library(lib: Path) -> Path | None:
    """Look for a BO3 install anywhere in ``<lib>/steamapps/common/``.

    Tries the canonical name first, then case-insensitive variants, then
    the small set of alternate names we know real installs use.
    """
    common = lib / "steamapps" / "common"
    if not common.is_dir():
        return None
    # Fast path — the canonical name matches exactly.
    canonical = common / BO3_INSTALLDIR
    if canonical.is_dir() and looks_like_bo3(canonical):
        return canonical
    # Slow path — try alternate casings / names.
    for alt in _BO3_DIR_ALTS:
        hit = _find_case_insensitive(common, alt)
        if hit is not None and looks_like_bo3(hit):
            return hit
    return None


# Common places a Non-Steam BO3 install ends up on Linux. All checked in
# order and the first one that ``looks_like_bo3()`` wins.
def _non_steam_hints() -> list[Path]:
    home = Path.home()
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", "") or (home / ".local" / "share")).expanduser()
    hints: list[Path] = []
    for base_name in _BO3_DIR_ALTS:
        hints += [
            home / "Games" / base_name,
            home / base_name,
            # Lutris (both default install dirs)
            home / "Games" / "lutris" / base_name.lower().replace(" ", "-") / "drive_c" / "Program Files" / BO3_INSTALLDIR,
            xdg_data / "lutris" / "runners" / "wine" / "prefixes" / "bo3" / "drive_c" / "Program Files" / BO3_INSTALLDIR,
            # Heroic
            home / "Games" / "Heroic" / base_name,
            # Bottles
            xdg_data / "bottles" / "bottles" / "bo3" / "drive_c" / "Program Files" / BO3_INSTALLDIR,
        ]
    return hints


def find_bo3_dir() -> Path | None:
    """Return the absolute path of the BO3 install folder, or None.

    Prefers Steam's library listing (across every Steam root — native,
    Flatpak, Snap), then falls back to well-known Non-Steam install
    locations. Every hit is sanity-checked against :func:`looks_like_bo3`.
    """
    # 1) Any Steam library on any Steam root — first hit wins.
    for root in existing_roots():
        for lib in _library_paths(root):
            hit = _bo3_in_library(lib)
            if hit is not None:
                return hit

    # 2) Non-Steam install hints.
    for candidate in _non_steam_hints():
        if candidate.is_dir() and looks_like_bo3(candidate):
            return candidate

    return None


def scan_all_steam_roots() -> list[Path]:
    """List every Steam root we could find on this system (for diagnostics)."""
    return existing_roots()


def looks_like_bo3(path: Path) -> bool:
    """Sanity-check a user-supplied path — does it look like a BO3 install?"""
    if not path.is_dir():
        return False
    # Canonical filenames (as shipped). We also accept case-insensitive
    # matches because copies via NTFS/exFAT sometimes mangle casing.
    markers = ("BlackOps3.exe", "steam_appid.txt", "main")
    for m in markers:
        if (path / m).exists():
            return True
        if _find_case_insensitive(path, m) is not None:
            return True
    return False


def config_dir() -> Path:
    """XDG-compliant config dir for this app.

    Honours ``XDG_CONFIG_HOME`` if set; otherwise falls back to
    ``~/.config`` per the freedesktop spec.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    d = base / "t7patch-manager"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    """Where we write the running log for the debug viewer."""
    return config_dir() / "t7patch-manager.log"
