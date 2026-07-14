"""Best-effort wrappers to open paths / URLs in the user's file manager or browser."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Order: native file managers first (the user gets the app they know),
# then generic openers (xdg-open / gio) as a safety net.
_FILE_MANAGERS = (
    "dolphin",
    "thunar",
    "nautilus",
    "nemo",
    "pcmanfm",
    "pcmanfm-qt",
    "caja",
    "krusader",
    "spacefm",
)

_GENERIC_OPENERS = ("xdg-open", "gio")

# Terminals used only as a last-resort fallback: opens a shell in the folder.
_TERMINALS = (
    ("kitty",           ["--directory"]),
    ("alacritty",       ["--working-directory"]),
    ("foot",            ["--working-directory"]),
    ("wezterm",         ["start", "--cwd"]),
    ("konsole",         ["--workdir"]),
    ("gnome-terminal",  ["--working-directory"]),
    ("xfce4-terminal",  ["--working-directory"]),
    ("tilix",           ["--working-directory"]),
    ("ptyxis",          ["--working-directory"]),
    ("xterm",           None),  # xterm can't set cwd; we cd first via env
    ("urxvt",           None),
    ("st",              None),
)


def _spawn(argv: list[str], cwd: str | None = None) -> None:
    subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def open_folder(path: Path) -> None:
    """Open *path* in the user's file manager.

    Preference order:

    1. Native file managers (Dolphin, Thunar, Nautilus, Nemo, PCManFM, …).
    2. Generic openers (``xdg-open``, ``gio open``) — delegates to whatever
       the desktop has set as the default for directories.
    3. Terminal emulator opened *in* the folder (Kitty, Alacritty, Konsole,
       GNOME Terminal, xterm, …). Useful on minimal / headless setups where
       no file manager is installed.

    Raises :class:`RuntimeError` only if not a single one of the above is
    available on the system.
    """
    p = str(path)
    tried: list[str] = []

    # 1. Native file managers
    for tool in _FILE_MANAGERS:
        if shutil.which(tool):
            _spawn([tool, p])
            return
        tried.append(tool)

    # 2. Generic openers
    for tool in _GENERIC_OPENERS:
        if shutil.which(tool):
            cmd = [tool, "open", p] if tool == "gio" else [tool, p]
            _spawn(cmd)
            return
        tried.append(tool)

    # 3. Terminal fallback — open a shell inside the folder
    for term, cwd_flag in _TERMINALS:
        if shutil.which(term):
            if cwd_flag is None:
                # xterm-style: no cwd flag, use subprocess cwd instead
                _spawn([term], cwd=p)
            else:
                _spawn([term, *cwd_flag, p])
            return
        tried.append(term)

    raise RuntimeError(
        "No file manager or terminal found. Tried: " + ", ".join(tried)
    )


def open_url(url: str) -> None:
    for tool in ("xdg-open", "gio"):
        if shutil.which(tool):
            cmd = [tool, "open", url] if tool == "gio" else [tool, url]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise RuntimeError("No URL opener available.")
