"""Read & write Steam per-user config (``localconfig.vdf``).

The interesting file is at::

    <steam_root>/userdata/<uid>/config/localconfig.vdf

with the nested key path::

    UserLocalConfigStore / Software / Valve / Steam / apps / <appid> / LaunchOptions

We locate every Steam root the user might have (native, Flatpak, Snap) and
every ``userdata/<uid>`` under each of them, then let the caller decide what
to do with the resulting candidate list.

Steam serialises this file from memory when it exits — any writes we make
while Steam is running will be clobbered. Call :func:`is_steam_running`
first and bail if it returns ``True``.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import steam_vdf
from .logger import configure as _configure_logging

log = _configure_logging()


# ── Steam roots ─────────────────────────────────────────────────────
_STEAM_ROOTS = (
    "~/.steam/steam",
    "~/.steam/root",
    "~/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/data/Steam",
    "~/snap/steam/common/.local/share/Steam",
    "~/snap/steam/common/.steam/steam",
)


def _existing_steam_roots() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for raw in _STEAM_ROOTS:
        p = Path(os.path.expanduser(raw))
        try:
            resolved = p.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


@dataclass(frozen=True)
class LocalConfig:
    """A single ``localconfig.vdf`` on disk, tied to one Steam userdata dir."""

    path: Path            # …/userdata/<uid>/config/localconfig.vdf
    steam_uid: str        # numeric SteamID3 (folder name under userdata/)
    steam_root: Path      # the Steam root this belongs to

    @property
    def label(self) -> str:
        """Short human-readable label, e.g. ``123456789 (~/.local/share/Steam)``."""
        root_disp = str(self.steam_root).replace(str(Path.home()), "~", 1)
        return f"{self.steam_uid} ({root_disp})"


def find_local_configs() -> list[LocalConfig]:
    """Return every existing ``localconfig.vdf`` across all Steam roots.

    Sorted by modification time, newest first — that way ``[0]`` is almost
    always the account the user is actually logged in with.
    """
    hits: list[LocalConfig] = []
    for root in _existing_steam_roots():
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for uid_dir in userdata.iterdir():
            if not uid_dir.is_dir() or not uid_dir.name.isdigit():
                continue
            cfg = uid_dir / "config" / "localconfig.vdf"
            if cfg.is_file():
                hits.append(LocalConfig(path=cfg, steam_uid=uid_dir.name, steam_root=root))
    hits.sort(key=lambda h: h.path.stat().st_mtime, reverse=True)
    return hits


# ── Steam running detection ─────────────────────────────────────────
def is_steam_running() -> bool:
    """Best-effort check whether the Steam client is currently running.

    We combine three signals so we don't rely on a single fragile one:

    * ``pgrep -x steam`` (works on native + most repackaged clients)
    * ``pidof steam``    (fallback for tiny distros without pgrep)
    * scanning ``/proc/*/comm`` for ``steam``  (no external deps at all)
    """
    for cmd in (("pgrep", "-x", "steam"),
                ("pgrep", "-x", "steamwebhelper"),
                ("pidof", "steam")):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and r.stdout.strip():
            return True

    # Pure /proc fallback — no external binaries required.
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            comm = entry / "comm"
            try:
                if comm.read_text(errors="ignore").strip() == "steam":
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def wait_for_steam_to_exit(timeout: float = 30.0, poll: float = 0.5) -> bool:
    """Block until Steam is no longer running or *timeout* elapses.

    Returns ``True`` if Steam is gone, ``False`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_steam_running():
            return True
        time.sleep(poll)
    return not is_steam_running()


def request_steam_shutdown() -> bool:
    """Ask Steam to exit cleanly.

    Uses ``steam -shutdown`` if the ``steam`` CLI is on ``PATH`` — that's the
    same method Steam's own installer uses. Returns ``True`` if the command
    ran (not whether Steam actually stopped — poll with
    :func:`wait_for_steam_to_exit`).
    """
    steam_bin = shutil.which("steam")
    if steam_bin is None:
        # Flatpak fallback
        flatpak = shutil.which("flatpak")
        if flatpak is not None:
            try:
                subprocess.run(
                    [flatpak, "run", "com.valvesoftware.Steam", "-shutdown"],
                    capture_output=True, timeout=5,
                )
                return True
            except (OSError, subprocess.TimeoutExpired):
                return False
        return False
    try:
        subprocess.run([steam_bin, "-shutdown"], capture_output=True, timeout=5)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


# ── Launch-option get/set ───────────────────────────────────────────
BO3_APPID = "311210"
BO3_LAUNCH_OPTIONS = 'WINEDLLOVERRIDES="dsound=n,b" %command%'

# Path under localconfig.vdf where per-app settings live.
_APPS_PATH = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")


def _walk(root: dict, path: Iterable[str], *, create: bool = False) -> dict | None:
    """Walk a nested dict along *path*. If *create* is set, missing sub-dicts
    are created in place. Returns ``None`` when *create* is false and any
    step is missing.

    Steam is case-insensitive about the top-level keys \u2014 different clients
    write ``Software`` vs ``software``. We match case-insensitively on read
    but keep whatever casing we already found so we don't rewrite the file
    with a different case.
    """
    node: dict = root
    for step in path:
        # Case-insensitive lookup
        match = next((k for k in node.keys() if k.lower() == step.lower()), None)
        if match is None:
            if not create:
                return None
            node[step] = {}
            match = step
        if not isinstance(node[match], dict):
            if not create:
                return None
            node[match] = {}
        node = node[match]
    return node


def get_launch_options(cfg: LocalConfig, appid: str = BO3_APPID) -> str | None:
    """Return the current LaunchOptions string for *appid*, or ``None`` if
    none is set / the file has no ``apps`` block yet.
    """
    text = cfg.path.read_text(encoding="utf-8", errors="replace")
    tree = steam_vdf.loads(text)
    apps = _walk(tree, _APPS_PATH)
    if apps is None:
        return None
    # AppID lookup — Steam sometimes writes the id as int-looking string,
    # sometimes with quotes; be lenient.
    app = next((v for k, v in apps.items() if str(k) == str(appid)), None)
    if not isinstance(app, dict):
        return None
    lo = next((v for k, v in app.items() if k.lower() == "launchoptions"), None)
    return lo if isinstance(lo, str) else None


def set_launch_options(
    cfg: LocalConfig,
    value: str = BO3_LAUNCH_OPTIONS,
    *,
    appid: str = BO3_APPID,
    backup: bool = True,
) -> Path:
    """Write *value* as the LaunchOptions for *appid* in *cfg*.

    * Refuses to run if Steam is currently up (would be clobbered on exit).
    * Writes a ``.bak-YYYYmmddHHMMSS`` backup unless *backup* is False.
    * Uses an atomic replace: write to ``<file>.tmp`` then ``os.replace``.

    Returns the path to the backup file (or the original path if no backup
    was taken).
    """
    if is_steam_running():
        raise RuntimeError(
            "Steam is currently running. Close Steam completely first \u2014 "
            "otherwise Steam will overwrite localconfig.vdf on exit and "
            "discard our change."
        )

    text = cfg.path.read_text(encoding="utf-8", errors="replace")
    tree = steam_vdf.loads(text)
    apps = _walk(tree, _APPS_PATH, create=True)
    assert apps is not None  # create=True guarantees a dict

    # Find or create the app entry, preserving existing casing.
    app_key = next((k for k in apps.keys() if str(k) == str(appid)), appid)
    if not isinstance(apps.get(app_key), dict):
        apps[app_key] = {}
    app = apps[app_key]

    lo_key = next((k for k in app.keys() if k.lower() == "launchoptions"), "LaunchOptions")
    app[lo_key] = value

    new_text = steam_vdf.dumps(tree)

    backup_path = cfg.path
    if backup:
        stamp = time.strftime("%Y%m%d%H%M%S")
        backup_path = cfg.path.with_suffix(cfg.path.suffix + f".bak-{stamp}")
        shutil.copy2(cfg.path, backup_path)
        log.info("Backed up %s \u2192 %s", cfg.path, backup_path)

    tmp = cfg.path.with_suffix(cfg.path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, cfg.path)
    log.info("Set LaunchOptions for app %s in %s", appid, cfg.path)
    return backup_path


# Convenience for the UI: "what's the state right now?"
# Not frozen — the UI re-evaluates ``matches_target`` against a
# wrapper-aware expected value (see ui._refresh_launch_options).
@dataclass
class LaunchOptionsStatus:
    config: LocalConfig | None
    current: str | None       # current value (or None)
    matches_target: bool      # current == BO3_LAUNCH_OPTIONS


def check_status(
    target: str = BO3_LAUNCH_OPTIONS,
    appid: str = BO3_APPID,
) -> LaunchOptionsStatus:
    """Return the status of the most-recently-used Steam profile."""
    configs = find_local_configs()
    if not configs:
        return LaunchOptionsStatus(config=None, current=None, matches_target=False)
    cfg = configs[0]
    try:
        current = get_launch_options(cfg, appid=appid)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read %s: %s", cfg.path, exc)
        current = None
    return LaunchOptionsStatus(
        config=cfg,
        current=current,
        matches_target=(current or "").strip() == target.strip(),
    )


# ── Non-Steam shortcut discovery ──
@dataclass(frozen=True)
class NonSteamShortcut:
    """A game the user added to Steam via 'Add a Non-Steam Game'."""
    appid: str          # decimal string of the Steam-generated shortcut AppID
    name: str           # display name Steam shows in the library
    exe: str            # exe / launcher path Steam records
    userdata: Path      # userdata/<uid> dir this shortcut lives under


_BO3_NAME_HINTS = ("black ops iii", "black ops 3", "bo3", "blackops3")


def _read_shortcuts_vdf(path: Path) -> list[dict]:
    """Parse Steam's binary shortcuts.vdf into a list of shortcut dicts.

    shortcuts.vdf is a *binary* KeyValues blob, not the text format used by
    localconfig.vdf. Its structure is a sequence of null-terminated typed
    fields wrapped in ``\\x00shortcuts\\x00`` → ``\\x00<idx>\\x00`` → field
    entries. We do a permissive text-oriented extraction — enough to pull
    out ``appid``, ``AppName`` and ``Exe`` for every entry, which is all we
    need. We deliberately don't ship a full binary VDF parser; if this
    fingerprinting misses an edge case, the user's manual AppID override
    still works.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return []

    out: list[dict] = []
    # Split on the record separator Steam uses between shortcuts (0x00<index>0x00).
    # We just scan every '\x02appid' + 4-byte little-endian uint block, then
    # look at the next AppName / Exe string fields that follow.
    i = 0
    while True:
        j = raw.find(b"\x02appid\x00", i)
        if j == -1:
            break
        # After the key, Steam writes the uint32 little-endian.
        val_off = j + len(b"\x02appid\x00")
        if val_off + 4 > len(raw):
            break
        appid_uint = int.from_bytes(raw[val_off:val_off + 4], "little", signed=True)
        # Steam stores it as *signed* i32; the 32-bit AppID we want in
        # localconfig.vdf is that value reinterpreted as unsigned.
        appid = str(appid_uint & 0xFFFFFFFF)

        # Look ahead a few hundred bytes for AppName + Exe strings.
        window = raw[val_off:val_off + 4096]

        def _read_string(key: bytes) -> str:
            k = window.find(b"\x01" + key + b"\x00")
            if k == -1:
                return ""
            start = k + len(key) + 2
            end = window.find(b"\x00", start)
            if end == -1:
                return ""
            try:
                return window[start:end].decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return ""

        out.append({
            "appid": appid,
            "AppName": _read_string(b"AppName") or _read_string(b"appname"),
            "Exe":     _read_string(b"Exe")     or _read_string(b"exe"),
        })
        i = val_off + 4
    return out


def find_non_steam_bo3_shortcuts() -> list[NonSteamShortcut]:
    """Scan every Steam userdata dir for shortcuts that look like BO3.

    Matches on AppName + Exe path against a small set of BO3 name hints, so
    a user who named their shortcut ``Black Ops 3 (T5)`` or ``BO3-crack`` or
    ``blackops3.exe`` all get picked up.
    """
    hits: list[NonSteamShortcut] = []
    for root in _existing_steam_roots():
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for uid_dir in userdata.iterdir():
            if not uid_dir.is_dir() or not uid_dir.name.isdigit():
                continue
            sc = uid_dir / "config" / "shortcuts.vdf"
            if not sc.is_file():
                continue
            for entry in _read_shortcuts_vdf(sc):
                needle = f"{entry.get('AppName', '')} {entry.get('Exe', '')}".lower()
                if any(h in needle for h in _BO3_NAME_HINTS):
                    hits.append(NonSteamShortcut(
                        appid=entry["appid"],
                        name=entry.get("AppName", "") or "(unnamed)",
                        exe=entry.get("Exe", ""),
                        userdata=uid_dir,
                    ))
    return hits
