"""Download and install T7Patch v3.x into the BO3 folder."""
from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GITHUB_API_LATEST = "https://api.github.com/repos/Scroptss/T7Patch/releases/latest"

# Files inside the Linux zip we care about
_PATCH_FILES = ("dsound.dll", "t7patch.dll", "t7patchloader.dll", "t7patch.conf")


@dataclass
class ReleaseInfo:
    tag: str
    published_at: str
    body: str
    linux_asset_url: str
    linux_asset_size: int


class InstallerError(RuntimeError):
    pass


def fetch_latest_release() -> ReleaseInfo:
    """Query GitHub API for the newest T7Patch release."""
    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "t7patch-manager"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    assets = data.get("assets") or []
    linux_asset = next(
        (a for a in assets if "linux" in a["name"].lower() and a["name"].lower().endswith(".zip")),
        None,
    )
    if not linux_asset:
        raise InstallerError("No Linux asset found in the latest T7Patch release.")
    return ReleaseInfo(
        tag=data["tag_name"],
        published_at=data["published_at"],
        body=data.get("body", "") or "",
        linux_asset_url=linux_asset["browser_download_url"],
        linux_asset_size=linux_asset.get("size", 0),
    )


def download_zip(url: str, on_progress: Callable[[int, int], None] | None = None) -> bytes:
    """Download a URL fully into memory, reporting (downloaded, total) bytes."""
    with urllib.request.urlopen(url, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        got = 0
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            got += len(chunk)
            if on_progress:
                on_progress(got, total)
    return buf.getvalue()


def extract_patch_into(bo3_dir: Path, zip_bytes: bytes, preserve_conf: bool = True) -> list[Path]:
    """Extract the 4 patch files into ``bo3_dir``.

    * A pre-existing ``t7patch.conf`` is preserved by default.
    * Existing DLLs are backed up to ``*.bak`` on the first install.

    Returns the list of files written.
    """
    if not bo3_dir.is_dir():
        raise InstallerError(f"BO3 directory does not exist: {bo3_dir}")

    written: list[Path] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.infolist():
            name = Path(member.filename).name
            if name not in _PATCH_FILES:
                continue
            target = bo3_dir / name
            if name == "t7patch.conf" and preserve_conf and target.exists():
                continue  # never clobber user config
            # Back up any pre-existing DLL exactly once
            if target.exists() and name.endswith(".dll") and not (bo3_dir / f"{name}.bak").exists():
                target.rename(bo3_dir / f"{name}.bak")
            target.write_bytes(zf.read(member))
            written.append(target)
    if not written:
        raise InstallerError("Zip contained no expected T7Patch files.")
    return written


def uninstall(bo3_dir: Path, delete_conf: bool = False) -> list[Path]:
    """Remove the 3 patch DLLs (and optionally the conf). Restore *.bak backups."""
    removed: list[Path] = []
    for name in ("dsound.dll", "t7patch.dll", "t7patchloader.dll"):
        p = bo3_dir / name
        pd = bo3_dir / f"{name}.disabled"
        for candidate in (p, pd):
            if candidate.exists():
                candidate.unlink()
                removed.append(candidate)
        bak = bo3_dir / f"{name}.bak"
        if bak.exists():
            bak.rename(bo3_dir / name)
    if delete_conf:
        conf = bo3_dir / "t7patch.conf"
        if conf.exists():
            conf.unlink()
            removed.append(conf)
    return removed
