"""Best-effort wrappers to open paths / URLs in the user's file manager or browser."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def open_folder(path: Path) -> None:
    """Open *path* in the user's file manager (GNOME Files, Dolphin, Nautilus, …)."""
    p = str(path)
    for tool, args in (
        ("xdg-open", [p]),
        ("gio",      ["open", p]),
        ("nautilus", [p]),
        ("dolphin",  [p]),
        ("thunar",   [p]),
        ("nemo",     [p]),
        ("pcmanfm",  [p]),
    ):
        if shutil.which(tool):
            subprocess.Popen([tool, *args] if tool == "gio" else [tool, p],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise RuntimeError("No file manager available (xdg-open / gio / nautilus / …).")


def open_url(url: str) -> None:
    for tool in ("xdg-open", "gio"):
        if shutil.which(tool):
            cmd = [tool, "open", url] if tool == "gio" else [tool, url]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise RuntimeError("No URL opener available.")
