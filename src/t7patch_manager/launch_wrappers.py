"""Manage GameMode / MangoHud wrappers inside a Steam LaunchOptions string.

The LaunchOptions string Steam accepts looks like this::

    ENV1=foo ENV2="bar baz" wrapper1 wrapper2 %command% -extra -args

* env-vars stay at the front (Steam requires ``key=value`` tokens before the
  first non-``key=value`` token)
* wrappers follow env-vars, in the order the user wants them applied
* ``%command%`` is the anchor; everything to its right are extra game args
* whitespace is preserved sensibly on re-serialisation

We only touch the *wrappers* segment. Anything the user had before / after
``%command%`` \u2014 including exotic env-vars, gamescope, obs-vkcapture, custom
Proton launch scripts \u2014 stays exactly where it was.
"""
from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass, field
from typing import Iterable


# ── Known wrappers ──────────────────────────────────────────────────
# Order in this dict = default position in the LaunchOptions string
# (earlier = further left = wraps everything to its right). GameMode
# outside, MangoHud inside \u2014 that's the widely-used convention.
KNOWN_WRAPPERS: tuple[str, ...] = ("gamemoderun", "mangohud")


def is_installed(wrapper: str) -> bool:
    """Return True iff *wrapper* is available on the user's ``$PATH``."""
    return shutil.which(wrapper) is not None


# ── Parsing / composing ─────────────────────────────────────────────
@dataclass
class LaunchOptions:
    """Parsed Steam LaunchOptions.

    Round-trips: ``LaunchOptions.parse(s).format() == s`` for every string
    we've thrown at it in tests, modulo collapsing of runs of whitespace to
    single spaces (Steam does the same on write).
    """

    env: list[tuple[str, str]] = field(default_factory=list)   # preserves order
    wrappers: list[str] = field(default_factory=list)          # e.g. ["gamemoderun", "mangohud"]
    tail: str = ""                                             # everything from %command% onwards, verbatim
    had_command_token: bool = True                             # False = string didn't include %command%

    # ── parsing ──
    @classmethod
    def parse(cls, s: str) -> "LaunchOptions":
        s = (s or "").strip()
        if not s:
            return cls(had_command_token=False, tail="%command%")

        # Split off %command% and its right-hand args. We keep the exact
        # right-hand side verbatim; only the left-hand side is structured.
        if "%command%" in s:
            left, _, right = s.partition("%command%")
            tail = "%command%" + right
        else:
            left, tail = s, ""

        try:
            tokens = shlex.split(left, posix=True)
        except ValueError:
            # Unbalanced quotes \u2014 give up on structured parsing and dump
            # everything into the wrappers list so nothing is lost.
            return cls(env=[], wrappers=[left.strip()],
                       tail=tail or "%command%",
                       had_command_token="%command%" in s)

        env: list[tuple[str, str]] = []
        wrappers: list[str] = []
        i = 0
        # Leading tokens of the form KEY=VALUE are env-vars.
        while i < len(tokens):
            t = tokens[i]
            if _looks_like_env_assign(t):
                k, _, v = t.partition("=")
                env.append((k, v))
                i += 1
                continue
            break
        # Everything remaining on the left of %command% is wrapper tokens.
        wrappers = tokens[i:]

        return cls(env=env, wrappers=wrappers,
                   tail=tail or "%command%",
                   had_command_token="%command%" in s)

    # ── composing ──
    def format(self) -> str:
        parts: list[str] = []
        for k, v in self.env:
            parts.append(f"{k}={_shell_quote_value(v)}")
        parts.extend(self.wrappers)
        left = " ".join(parts)
        tail = self.tail if self.tail else "%command%"
        if left:
            return f"{left} {tail}".strip()
        return tail

    # ── wrapper toggles ──
    def has_wrapper(self, name: str) -> bool:
        return name in self.wrappers

    def add_wrapper(self, name: str) -> None:
        """Insert *name* at its canonical position (see KNOWN_WRAPPERS)."""
        if name in self.wrappers:
            return
        # Preserve existing order for unknown wrappers; slot known ones by
        # their KNOWN_WRAPPERS index so gamemoderun always ends up before
        # mangohud regardless of which the user toggled first.
        if name not in KNOWN_WRAPPERS:
            self.wrappers.append(name)
            return
        target_idx = KNOWN_WRAPPERS.index(name)
        insert_at = len(self.wrappers)
        for i, existing in enumerate(self.wrappers):
            if existing in KNOWN_WRAPPERS and KNOWN_WRAPPERS.index(existing) > target_idx:
                insert_at = i
                break
        self.wrappers.insert(insert_at, name)

    def remove_wrapper(self, name: str) -> None:
        self.wrappers = [w for w in self.wrappers if w != name]


# ── helpers ─────────────────────────────────────────────────────────
def _looks_like_env_assign(tok: str) -> bool:
    """Steam only recognises leading KEY=VALUE tokens where KEY matches
    ``[A-Za-z_][A-Za-z0-9_]*``. Anything else is a wrapper.
    """
    if "=" not in tok:
        return False
    key, _, _ = tok.partition("=")
    if not key:
        return False
    if not (key[0].isalpha() or key[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in key)


# Characters that force us to wrap the value in double quotes when we
# re-emit it. Whitespace and shell metacharacters are obvious; comma is
# added because Steam-style env values like ``dsound=n,b`` are, by
# convention on ProtonDB / community guides, always shown quoted — we
# want to give the user back exactly what they'd have typed themselves.
_QUOTE_TRIGGERS = set(' \t"\'\\$`,;&|<>()#!*?[]{}~')


def _shell_quote_value(v: str) -> str:
    """Quote *v* only if necessary \u2014 keeps trivial values unquoted so the
    string looks like what the user would type themselves."""
    if v == "":
        return '""'
    if any(c in _QUOTE_TRIGGERS for c in v):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


# ── high-level convenience for the UI ───────────────────────────────
@dataclass(frozen=True)
class WrapperStatus:
    name: str
    installed: bool
    enabled: bool           # currently present in the LaunchOptions string


def status_for(options: str, wrapper: str) -> WrapperStatus:
    parsed = LaunchOptions.parse(options)
    return WrapperStatus(
        name=wrapper,
        installed=is_installed(wrapper),
        enabled=parsed.has_wrapper(wrapper),
    )


def toggle_wrapper(options: str, wrapper: str, *, enable: bool) -> str:
    """Return a new LaunchOptions string with *wrapper* enabled / disabled."""
    parsed = LaunchOptions.parse(options)
    if enable:
        parsed.add_wrapper(wrapper)
    else:
        parsed.remove_wrapper(wrapper)
    return parsed.format()


# Package-manager hints for the "install this" toast \u2014 covered distros mirror
# install.sh's set. Format: ``{distro_name: install_command}``.
INSTALL_HINTS: dict[str, dict[str, str]] = {
    "gamemoderun": {
        "arch":     "sudo pacman -S gamemode lib32-gamemode",
        "fedora":   "sudo dnf install gamemode",
        "debian":   "sudo apt install gamemode",
        "opensuse": "sudo zypper install gamemode",
        "alpine":   "sudo apk add gamemode",
        "void":     "sudo xbps-install -S gamemode",
        "gentoo":   "sudo emerge games-util/gamemode",
        "solus":    "sudo eopkg install gamemode",
        "nixos":    "programs.gamemode.enable = true;   # in configuration.nix",
        "ostree":   "rpm-ostree install gamemode && systemctl reboot",
        "flatpak":  "flatpak install --user com.valvesoftware.Steam.CompatibilityTool.gamemode",
    },
    "mangohud": {
        "arch":     "sudo pacman -S mangohud lib32-mangohud",
        "fedora":   "sudo dnf install mangohud",
        "debian":   "sudo apt install mangohud",
        "opensuse": "sudo zypper install mangohud",
        "alpine":   "sudo apk add mangohud",
        "void":     "sudo xbps-install -S MangoHud",
        "gentoo":   "sudo emerge games-util/mangohud",
        "solus":    "sudo eopkg install mangohud",
        "nixos":    "environment.systemPackages = [ pkgs.mangohud ];   # in configuration.nix",
        "ostree":   "flatpak install org.freedesktop.Platform.VulkanLayer.MangoHud",
        "flatpak":  "flatpak install --user com.valvesoftware.Steam.Utility.MangoHud",
    },
}
