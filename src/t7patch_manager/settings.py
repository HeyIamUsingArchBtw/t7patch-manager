"""Persistent user settings — manual overrides that survive across runs.

Lives in ~/.config/t7patch-manager/settings.json.

Every field is optional. When set, it overrides the corresponding auto-detected
value. This is the escape hatch for users on unusual setups where auto-detection
fails (custom Steam libraries, offline installs, forks of T7Patch, …).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import config_dir

SETTINGS_FILE = config_dir() / "settings.json"


@dataclass
class Settings:
    # Manual BO3 install path (skip Steam auto-detection when set)
    bo3_dir_override: str | None = None

    # Manual T7Patch source override — either an HTTPS URL to a Linux zip, or a
    # local filesystem path to a zip the user downloaded themselves.
    patch_source_override: str | None = None

    # Manual GitHub repo for the "check for updates" call, in "owner/repo" form.
    # Useful if a new maintainer ever forks the project.
    github_repo_override: str | None = None

    # Manual override for the Steam launch-options string. When set, the UI's
    # "Set automatically" button writes this exact value instead of the default
    # ``WINEDLLOVERRIDES="dsound=n,b" %command%``. Left empty for 99% of users.
    launch_options_override: str | None = None

    # Manual override for the Steam AppID whose LaunchOptions we set. Default
    # is 311210 (retail BO3). Set this if you added BO3 to Steam as a
    # "Non-Steam game" — Steam then assigns a per-user shortcut AppID like
    # ``2879137456`` which the user has to find themselves (see README).
    launch_options_appid_override: str | None = None

    # Network timeouts (seconds)
    http_timeout: int = 30

    # Extra bookkeeping — remembered dirs the user picked in file choosers
    last_zip_dir: str | None = None

    # Free-form key/value store for future settings without a schema bump
    extra: dict = field(default_factory=dict)

    # ── I/O ─────────────────────────────────────────────
    @classmethod
    def load(cls) -> "Settings":
        if not SETTINGS_FILE.is_file():
            return cls()
        try:
            data = json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        # Ignore unknown keys, tolerate schema drift
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2))

    # ── helpers ────────────────────────────────────────
    def effective_bo3_dir(self) -> Path | None:
        """Manual override if set and valid, else None (caller falls back to auto-detect)."""
        if not self.bo3_dir_override:
            return None
        p = Path(self.bo3_dir_override).expanduser()
        return p if p.is_dir() else None

    def effective_repo(self) -> str:
        return self.github_repo_override or "Scroptss/T7Patch"
