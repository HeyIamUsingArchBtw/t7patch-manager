"""Launch BO3 through Steam (which handles Proton, launch options, everything).

Handles native, Flatpak and Snap Steam \u2014 whichever is on the host is fine.
"""
from __future__ import annotations
import shutil
import subprocess

BO3_APPID = "311210"
STEAM_URL = f"steam://rungameid/{BO3_APPID}"

# Steam-side launch option the user must set in the game's properties:
LAUNCH_OPTIONS = 'WINEDLLOVERRIDES="dsound=n,b" %command%'


def _spawn(argv: list[str]) -> None:
    subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def launch_bo3() -> None:
    """Fire off BO3 via steam:// URL. Non-blocking.

    Preference order:

    1. ``xdg-open`` \u2014 respects the user's default handler for ``steam://``,
       so Flatpak-Steam users get Flatpak-Steam automatically.
    2. ``gio open`` \u2014 same idea, GNOME's native equivalent.
    3. Native ``steam`` binary directly on ``$PATH``.
    4. ``flatpak run com.valvesoftware.Steam`` \u2014 Flatpak-Steam without a
       registered URL handler.
    5. ``snap run steam`` \u2014 Snap-Steam.
    """
    if shutil.which("xdg-open"):
        _spawn(["xdg-open", STEAM_URL])
        return
    if shutil.which("gio"):
        _spawn(["gio", "open", STEAM_URL])
        return
    if shutil.which("steam"):
        _spawn(["steam", STEAM_URL])
        return
    if shutil.which("flatpak"):
        _spawn(["flatpak", "run", "com.valvesoftware.Steam", STEAM_URL])
        return
    if shutil.which("snap"):
        _spawn(["snap", "run", "steam", STEAM_URL])
        return
    raise RuntimeError(
        "Could not find a way to launch Steam. Install one of: "
        "xdg-utils, glib2 (for gio), native steam, flatpak, or snap."
    )
