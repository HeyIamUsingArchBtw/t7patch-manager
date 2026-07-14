"""Launch BO3 through Steam (which handles Proton, launch options, everything)."""
from __future__ import annotations
import subprocess
import shutil

BO3_APPID = "311210"
STEAM_URL = f"steam://rungameid/{BO3_APPID}"

# Steam-side launch option the user must set in the game's properties:
LAUNCH_OPTIONS = 'WINEDLLOVERRIDES="dsound=n,b" %command%'


def launch_bo3() -> None:
    """Fire off BO3 via steam:// URL. Non-blocking."""
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if opener == shutil.which("gio"):
        subprocess.Popen(["gio", "open", STEAM_URL],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif opener:
        subprocess.Popen([opener, STEAM_URL],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Steam is almost certainly on PATH — fall back to it directly
        subprocess.Popen(["steam", STEAM_URL],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
