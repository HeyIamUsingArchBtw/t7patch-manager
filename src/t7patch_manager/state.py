"""Detect current T7Patch state in a BO3 folder and toggle enable/disable."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PatchState(Enum):
    NOT_INSTALLED = "not_installed"
    ENABLED = "enabled"
    DISABLED = "disabled"


_DLLS = ("dsound.dll", "t7patch.dll", "t7patchloader.dll")


@dataclass
class PatchStatus:
    state: PatchState
    installed_version: str | None
    conf_exists: bool


def _installed_version(bo3_dir: Path) -> str | None:
    """Read the shipped ``version`` file if present."""
    v = bo3_dir / "t7patch.version"
    return v.read_text().strip() if v.is_file() else None


def detect(bo3_dir: Path) -> PatchStatus:
    """Return current patch state in the BO3 folder."""
    enabled = all((bo3_dir / f).is_file() for f in _DLLS)
    disabled = all((bo3_dir / f"{f}.disabled").is_file() for f in _DLLS)
    if enabled:
        state = PatchState.ENABLED
    elif disabled:
        state = PatchState.DISABLED
    else:
        state = PatchState.NOT_INSTALLED
    return PatchStatus(
        state=state,
        installed_version=_installed_version(bo3_dir),
        conf_exists=(bo3_dir / "t7patch.conf").is_file(),
    )


def set_enabled(bo3_dir: Path, enable: bool) -> None:
    """Rename dlls to enable or disable the patch without deleting anything."""
    for f in _DLLS:
        active = bo3_dir / f
        parked = bo3_dir / f"{f}.disabled"
        if enable:
            if parked.is_file() and not active.is_file():
                parked.rename(active)
        else:
            if active.is_file() and not parked.is_file():
                active.rename(parked)


def write_version_marker(bo3_dir: Path, tag: str) -> None:
    """Persist installed tag for update-checking."""
    (bo3_dir / "t7patch.version").write_text(tag.strip() + "\n")
