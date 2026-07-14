"""Single source of truth for locating every Steam installation on this system.

Historically :mod:`paths` and :mod:`steam_config` each carried their own copy
of the Steam-root candidate list. The two lists slowly drifted, which meant a
user with a non-standard install (Flatpak, Snap, XDG_DATA_HOME set to a
custom path, symlinked ``~/.local/share``) got detected by one part of the
app but not the other. This module now owns the list.

We look in **every** known location — native, Flatpak, Snap — plus anything
implied by the freedesktop XDG environment variables, resolve symlinks so
duplicates fold away, and return the roots that actually have a
``steamapps`` directory. That last check is the only reliable way to tell
"Steam ran here once" from "Steam is installed here".
"""
from __future__ import annotations

import os
from pathlib import Path

# Every location Steam is known to live in, expressed as ``$HOME``-relative
# strings so we can substitute the current user cleanly. ``XDG_DATA_HOME``
# overrides ``~/.local/share`` and is handled dynamically below.
_STEAM_ROOT_HINTS: tuple[str, ...] = (
    # Native — the two symlinks Steam itself maintains + the real dir
    "~/.steam/steam",
    "~/.steam/root",
    "~/.local/share/Steam",
    # Flatpak (com.valvesoftware.Steam)
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/data/Steam",
    # Snap (canonical steam snap)
    "~/snap/steam/common/.local/share/Steam",
    "~/snap/steam/common/.steam/steam",
)


def _xdg_data_home() -> Path:
    """Return the effective ``XDG_DATA_HOME`` — respects the env var."""
    v = os.environ.get("XDG_DATA_HOME", "").strip()
    if v:
        return Path(v).expanduser()
    return Path.home() / ".local" / "share"


def candidate_roots() -> list[Path]:
    """Every path we should check for a Steam install, in preference order.

    Deduplicates by resolved (symlink-followed) path, so a user whose
    ``~/.steam/steam`` symlinks into ``~/.local/share/Steam`` only sees the
    Steam root once. Non-existent candidates stay in the list — callers use
    :func:`existing_roots` when they want only the live ones.
    """
    raw: list[Path] = []
    xdg = _xdg_data_home()
    # XDG-derived candidates first — a user who set XDG_DATA_HOME expects
    # us to honour it before the hard-coded ~/.local/share fallback.
    if xdg != Path.home() / ".local" / "share":
        raw.append(xdg / "Steam")
    for raw_hint in _STEAM_ROOT_HINTS:
        raw.append(Path(os.path.expanduser(raw_hint)))

    seen: set[Path] = set()
    out: list[Path] = []
    for p in raw:
        # Resolving may fail if a parent dir is inaccessible; keep the raw
        # path so we still check it in that case.
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def existing_roots() -> list[Path]:
    """Roots that actually exist and contain a ``steamapps`` directory."""
    out: list[Path] = []
    seen: set[Path] = set()
    for p in candidate_roots():
        if not (p / "steamapps").is_dir():
            continue
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


# ── Flavour detection ────────────────────────────────────────────────
def steam_flavour(root: Path) -> str:
    """Return a short label describing which Steam install this root is.

    One of ``native``, ``flatpak``, ``snap``, ``other``. Used to steer
    Steam-shutdown / Steam-launch commands when the user has multiple
    installs.
    """
    s = str(root)
    if "/.var/app/com.valvesoftware.Steam/" in s:
        return "flatpak"
    if "/snap/steam/" in s:
        return "snap"
    if s.endswith("/.local/share/Steam") or s.endswith("/.steam/steam") or s.endswith("/.steam/root"):
        return "native"
    return "other"
