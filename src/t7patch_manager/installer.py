"""Download and install T7Patch v3.x into the BO3 folder.

Automatic sources (in order):
  1. Manual override in settings.patch_source_override
     - Local file path → read directly
     - https:// URL    → download
  2. GitHub releases of settings.effective_repo() (default: Scroptss/T7Patch)

Every network call has a timeout, retries and clear error messages so failures
surface early instead of hanging.
"""
from __future__ import annotations

import io
import json
import socket
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Files inside the Linux zip we care about
_PATCH_FILES = ("dsound.dll", "t7patch.dll", "t7patchloader.dll", "t7patch.conf")

# Retries for transient network errors
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # seconds; multiplied by attempt number


@dataclass
class ReleaseInfo:
    tag: str
    published_at: str
    body: str
    linux_asset_url: str
    linux_asset_size: int
    source: str = "github"  # "github" | "override-url" | "override-file"


class InstallerError(RuntimeError):
    """Any expected failure during install; message is user-facing."""


# ── HTTP helpers ────────────────────────────────────────────────────
def _urlopen(url: str, timeout: int = 30, accept: str = "application/octet-stream"):
    """Wrap urlopen with a User-Agent and consistent timeout."""
    req = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": "t7patch-manager"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _retryable(url: str, timeout: int, on_attempt: Callable[[int, str], None] | None = None):
    """Yield ``urlopen`` responses with retry on transient errors.

    Raises InstallerError with a user-friendly message on final failure.
    """
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return _urlopen(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            # 4xx errors are not retryable (except 429)
            if e.code == 429:
                last_err = e
                if on_attempt:
                    on_attempt(attempt, f"Rate-limited (HTTP 429); retrying…")
            elif 400 <= e.code < 500:
                raise InstallerError(
                    f"Server returned HTTP {e.code} for {url}\n{e.reason}"
                ) from e
            else:
                last_err = e
                if on_attempt:
                    on_attempt(attempt, f"HTTP {e.code}; retrying…")
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_err = e
            if on_attempt:
                on_attempt(attempt, f"Network error: {e}; retrying…")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    raise InstallerError(
        f"Could not reach {url} after {_MAX_RETRIES} attempts.\n"
        f"Last error: {last_err}\n\n"
        f"Check your internet connection, or set a manual T7Patch source in\n"
        f"Preferences → Advanced."
    ) from last_err


# ── Release discovery ───────────────────────────────────────────────
def fetch_latest_release(repo: str = "Scroptss/T7Patch",
                        timeout: int = 30,
                        override_source: str | None = None) -> ReleaseInfo:
    """Get the newest T7Patch release, or resolve a manual override."""

    if override_source:
        # Manual override — either a URL or a local file path
        if override_source.startswith(("http://", "https://")):
            return ReleaseInfo(
                tag="custom",
                published_at="",
                body="Manual URL override",
                linux_asset_url=override_source,
                linux_asset_size=0,
                source="override-url",
            )
        p = Path(override_source).expanduser()
        if not p.is_file():
            raise InstallerError(
                f"Manual T7Patch source is set but the file does not exist:\n{p}\n\n"
                f"Fix the path in Preferences → Advanced, or clear the override."
            )
        return ReleaseInfo(
            tag="custom",
            published_at="",
            body=f"Manual local file: {p}",
            linux_asset_url=str(p),
            linux_asset_size=p.stat().st_size,
            source="override-file",
        )

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        with _retryable(api_url, timeout=timeout) as r:
            data = json.load(r)
    except InstallerError:
        raise
    except Exception as e:  # noqa: BLE001
        raise InstallerError(f"GitHub API failed: {e}") from e

    assets = data.get("assets") or []
    linux_asset = next(
        (a for a in assets if "linux" in a["name"].lower() and a["name"].lower().endswith(".zip")),
        None,
    )
    if not linux_asset:
        raise InstallerError(
            f"No Linux zip found in the latest {repo} release ({data.get('tag_name')}).\n"
            f"The upstream release format may have changed. As a workaround, download\n"
            f"the Linux zip manually and point Preferences → Advanced at that file."
        )
    return ReleaseInfo(
        tag=data["tag_name"],
        published_at=data.get("published_at", ""),
        body=data.get("body", "") or "",
        linux_asset_url=linux_asset["browser_download_url"],
        linux_asset_size=linux_asset.get("size", 0),
        source="github",
    )


# ── Zip acquisition ─────────────────────────────────────────────────
def download_zip(url_or_path: str,
                 on_progress: Callable[[int, int], None] | None = None,
                 timeout: int = 30) -> bytes:
    """Return zip bytes from either an HTTP URL or a local file path."""

    if not url_or_path.startswith(("http://", "https://")):
        p = Path(url_or_path).expanduser()
        if not p.is_file():
            raise InstallerError(f"Local T7Patch zip not found: {p}")
        return p.read_bytes()

    try:
        with _retryable(url_or_path, timeout=timeout) as r:
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
    except InstallerError:
        raise
    except Exception as e:  # noqa: BLE001
        raise InstallerError(f"Download failed: {e}") from e


# ── Zip extraction ──────────────────────────────────────────────────
def extract_patch_into(bo3_dir: Path, zip_bytes: bytes,
                       preserve_conf: bool = True) -> list[Path]:
    """Extract the 4 patch files into *bo3_dir*.

    * A pre-existing ``t7patch.conf`` is preserved by default.
    * Existing DLLs are backed up to ``*.bak`` on the first install.
    """
    if not bo3_dir.is_dir():
        raise InstallerError(f"BO3 directory does not exist: {bo3_dir}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise InstallerError(
            f"Downloaded file is not a valid zip archive ({e}).\n"
            f"The source may be corrupted or wrong. Try again, or point\n"
            f"Preferences → Advanced at a locally downloaded copy."
        ) from e

    # Find the patch files anywhere in the zip (handles both flat and nested layouts)
    members_by_name: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        base = Path(info.filename).name
        if base in _PATCH_FILES and base not in members_by_name:
            members_by_name[base] = info

    if not members_by_name:
        raise InstallerError(
            "Zip does not contain any expected T7Patch files "
            f"({', '.join(_PATCH_FILES)}).\n"
            "The archive layout may have changed upstream."
        )

    written: list[Path] = []
    try:
        for name, info in members_by_name.items():
            target = bo3_dir / name
            if name == "t7patch.conf" and preserve_conf and target.exists():
                continue
            # Backup any pre-existing DLL exactly once
            if target.exists() and name.endswith(".dll") and not (bo3_dir / f"{name}.bak").exists():
                target.rename(bo3_dir / f"{name}.bak")
            target.write_bytes(zf.read(info))
            written.append(target)
    except PermissionError as e:
        raise InstallerError(
            f"Permission denied writing to {bo3_dir}\n\n"
            f"Make sure the folder is writable by your user. If BO3 lives on\n"
            f"a separate drive, check its mount options."
        ) from e
    except OSError as e:
        raise InstallerError(f"Could not write patch files: {e}") from e

    if not written:
        raise InstallerError("Nothing was written — install aborted.")
    return written


def uninstall(bo3_dir: Path, delete_conf: bool = False) -> list[Path]:
    """Remove patch DLLs and the version marker.

    * Removes ``dsound.dll``, ``t7patch.dll``, ``t7patchloader.dll`` in both
      their active and ``*.disabled`` variants.
    * Restores ``*.bak`` files if any were saved on first install.
    * Removes the ``t7patch.version`` marker so status detection reports
      the patch as gone.
    * Optionally removes ``t7patch.conf`` (off by default — the user's
      in-game name / password is worth keeping across reinstalls).
    """
    removed: list[Path] = []
    for name in ("dsound.dll", "t7patch.dll", "t7patchloader.dll"):
        for candidate in (bo3_dir / name, bo3_dir / f"{name}.disabled"):
            if candidate.exists():
                candidate.unlink()
                removed.append(candidate)
        bak = bo3_dir / f"{name}.bak"
        if bak.exists():
            bak.rename(bo3_dir / name)
    version_marker = bo3_dir / "t7patch.version"
    if version_marker.exists():
        version_marker.unlink()
        removed.append(version_marker)
    if delete_conf:
        conf = bo3_dir / "t7patch.conf"
        if conf.exists():
            conf.unlink()
            removed.append(conf)
    return removed
