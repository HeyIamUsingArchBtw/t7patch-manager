"""Detect the host distro's package manager and build an install command.

We intentionally keep this dead-simple: we do NOT try to be a generic
package manager abstraction. All we need is *"install this one package
with a graphical polkit prompt, and stream the output live so the user
can watch progress"*.

Design notes
------------

- ``/etc/os-release`` is the single source of truth (systemd standard,
  present on every mainstream distro since ~2013).
- We pick a package manager based on ``ID`` and ``ID_LIKE`` — Arch,
  CachyOS, Manjaro all share ``ID_LIKE=arch``; Fedora / Nobara /
  Bazzite share ``fedora``; Ubuntu / Mint / Pop / Elementary share
  ``debian``; openSUSE variants share ``suse``.
- We escalate via ``pkexec`` — that's the standard GUI polkit prompt on
  GNOME/KDE/Hyprland, works headlessly (no terminal needed) and is
  present anywhere polkit is (which is anywhere you'd run this GUI).
- ``sudo`` is intentionally NOT a fallback. ``sudo`` needs a controlling
  TTY unless the user configured NOPASSWD, and we can't ship a
  pseudo-TTY through GTK4. If pkexec isn't available we bail early with
  a helpful message.
- No ``--assume-yes`` for pacman: it uses ``--noconfirm`` instead. This
  is the one place the flags actually differ.
- For openSUSE/Fedora we run ``refresh``/``makecache`` first because
  their default TTLs assume manual updates and installing a fresh
  package on a stale index frequently fails.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

log = logging.getLogger(__name__)


# ── Package-name mapping ──
# Same tool ships under different package names across distros. Keys are
# the wrapper binary (what shutil.which() looks for); values are the
# per-family package names.
_PACKAGE_NAMES: dict[str, dict[str, str]] = {
    "gamemoderun": {
        "arch":   "gamemode",
        "debian": "gamemode",
        "fedora": "gamemode",
        "suse":   "gamemode",
        "alpine": "gamemode",
        "void":   "gamemode",
        "gentoo": "games-util/gamemode",
        "solus":  "gamemode",
    },
    "mangohud": {
        "arch":   "mangohud",
        "debian": "mangohud",
        "fedora": "mangohud",
        "suse":   "mangohud",
        "alpine": "mangohud",
        "void":   "MangoHud",
        "gentoo": "games-util/mangohud",
        "solus":  "mangohud",
    },
}

# Distro families where the app cannot safely automate installs, but we
# can still give the user a clean copy-pasteable command. Mapped to a
# short human-readable name for the fallback dialog.
_MANUAL_ONLY_FAMILIES: dict[str, str] = {
    "nixos": "NixOS",
    "guix": "GNU Guix",
    "ostree": "immutable Fedora (Silverblue / Kinoite / Bazzite)",
}

# For manual-only distros, show a concrete recipe the user can copy.
_MANUAL_INSTALL_HINTS: dict[str, dict[str, str]] = {
    "gamemoderun": {
        "nixos": "Add to configuration.nix and rebuild:\n\n    programs.gamemode.enable = true;\n\nthen run: sudo nixos-rebuild switch",
        "guix":  "guix install gamemode",
        "ostree": "rpm-ostree install gamemode\nthen reboot: systemctl reboot",
    },
    "mangohud": {
        "nixos": "Add to configuration.nix (system) or home.nix (user):\n\n    environment.systemPackages = [ pkgs.mangohud ];\n\nthen run: sudo nixos-rebuild switch",
        "guix":  "guix install mangohud",
        "ostree": "Preferred: flatpak install org.freedesktop.Platform.VulkanLayer.MangoHud\n\nOr layered on host: rpm-ostree install mangohud && systemctl reboot",
    },
}


@dataclass
class InstallPlan:
    """A ready-to-execute install command for one wrapper on this host."""

    wrapper: str                     # gamemoderun / mangohud
    package: str                     # actual package name on this distro
    family: str                      # arch / debian / fedora / suse
    display_name: str                # "Arch / CachyOS", "Fedora", ...
    command: list[str]               # full argv, ready for subprocess
    needs_polkit: bool = True        # False if we're already root

    # Optional pre-command (refresh package index). Runs first, failure
    # is fatal — a stale index is the #1 cause of install failure on
    # Fedora and openSUSE.
    prefetch: list[str] | None = None

    # For the log header shown to the user.
    human_command: str = field(init=False)

    def __post_init__(self) -> None:
        self.human_command = " ".join(shlex.quote(a) for a in self.command)


# ── Distro detection ──
def _read_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dict. Returns {} if missing/unreadable."""
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, encoding="utf-8") as fh:
                data: dict[str, str] = {}
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    # os-release fields are shell-quoted; strip quotes.
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                        v = v[1:-1]
                    data[k] = v
                return data
        except OSError:
            continue
    return {}


def _is_immutable_ostree() -> bool:
    """Return True on Silverblue / Kinoite / Bazzite / other rpm-ostree systems.

    On these systems ``dnf install`` still exists but does nothing useful —
    layered packages must go through ``rpm-ostree install`` followed by a
    reboot. We refuse to automate that, but do give the user a clean hint.
    """
    # /run/ostree-booted is the authoritative marker created by ostree at boot.
    if os.path.exists("/run/ostree-booted"):
        return True
    # rpm-ostree binary alone isn't proof (Fedora ships it in Workstation too),
    # but combined with ID=silverblue|kinoite|bazzite it is.
    ident = _read_os_release().get("VARIANT_ID", "").lower()
    return ident in {"silverblue", "kinoite", "sericea", "onyx"}


def detect_family() -> tuple[str, str] | tuple[None, None]:
    """Return ``(family, display_name)`` or ``(None, None)`` if unknown.

    Family is one of: ``arch``, ``debian``, ``fedora``, ``suse``,
    ``alpine``, ``void``, ``gentoo``, ``solus`` (auto-installable), or
    ``nixos``, ``guix``, ``ostree`` (manual-only — detected but not
    auto-installed by us).
    """
    info = _read_os_release()
    ident = info.get("ID", "").lower()
    like = info.get("ID_LIKE", "").lower().split()
    pretty = info.get("PRETTY_NAME") or info.get("NAME", "your distro")

    # Direct match first, then ID_LIKE fallback.
    def _match(*names: str) -> bool:
        return ident in names or any(n in like for n in names)

    # Immutable rpm-ostree systems must be caught BEFORE fedora — the
    # ID_LIKE is "fedora" but the install path is completely different.
    if _is_immutable_ostree() or _match("silverblue", "kinoite", "bazzite", "bluefin", "aurora"):
        return "ostree", pretty

    if _match("arch", "cachyos", "manjaro", "endeavouros", "artix", "garuda"):
        return "arch", pretty
    if _match("debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin", "kali", "raspbian"):
        return "debian", pretty
    if _match("fedora", "rhel", "centos", "nobara", "rocky", "almalinux"):
        return "fedora", pretty
    if _match("opensuse", "opensuse-tumbleweed", "opensuse-leap", "suse", "sles"):
        return "suse", pretty
    if _match("alpine", "postmarketos"):
        return "alpine", pretty
    if _match("void"):
        return "void", pretty
    if _match("gentoo", "funtoo"):
        return "gentoo", pretty
    if _match("solus"):
        return "solus", pretty
    if _match("nixos"):
        return "nixos", pretty
    if _match("guix", "guixsystem"):
        return "guix", pretty

    log.warning("Unknown distro: ID=%r ID_LIKE=%r", ident, like)
    return None, None


# ── Command builders ──
def _build_command(family: str, package: str) -> tuple[list[str], list[str] | None]:
    """Return ``(install_argv, prefetch_argv_or_None)`` for *family*.

    All commands run non-interactively — they must NOT prompt on the
    controlling terminal (there is no controlling terminal), and they
    must NOT ask questions like 'do you accept this signature key?'.
    """
    if family == "arch":
        # --needed keeps the command idempotent (silently no-op if
        # already installed by someone else in the meantime).
        return (
            ["pacman", "-S", "--noconfirm", "--needed", package],
            None,
        )

    if family == "debian":
        # DEBIAN_FRONTEND is injected via env in run_install().
        # apt-get is preferred over apt for scripts (stable output).
        # --no-install-recommends keeps the payload small.
        return (
            ["apt-get", "install", "-y", "--no-install-recommends", package],
            ["apt-get", "update"],
        )

    if family == "fedora":
        # dnf5 (Fedora ≥41) and dnf4 both accept these flags identically.
        return (
            ["dnf", "install", "-y", package],
            ["dnf", "makecache", "--refresh"],
        )

    if family == "suse":
        # --non-interactive on the top-level *and* --no-confirm on the
        # subcommand — zypper needs both.
        return (
            ["zypper", "--non-interactive", "install", "--no-confirm", package],
            ["zypper", "--non-interactive", "refresh"],
        )

    if family == "alpine":
        # apk-tools on Alpine and postmarketOS.
        return (
            ["apk", "add", "--no-interactive", package],
            ["apk", "update"],
        )

    if family == "void":
        # xbps-install. -S = sync repos, -y = assume yes.
        return (
            ["xbps-install", "-Sy", package],
            None,
        )

    if family == "gentoo":
        # emerge builds from source — can be slow, but that's normal on
        # Gentoo and users expect it. --quiet-build reduces log spam.
        return (
            ["emerge", "--noreplace", "--quiet-build=y", package],
            ["emerge", "--sync", "--quiet"],
        )

    if family == "solus":
        return (
            ["eopkg", "install", "--yes-all", package],
            ["eopkg", "update-repo"],
        )

    raise ValueError(f"Unknown distro family: {family!r}")


def has_polkit() -> bool:
    """Is pkexec available on this system? Required unless we're root."""
    return shutil.which("pkexec") is not None


def plan_install(wrapper: str) -> InstallPlan:
    """Build an :class:`InstallPlan` for *wrapper* on this host.

    Raises
    ------
    ValueError
        Unknown wrapper.
    RuntimeError
        Unknown distro, or polkit missing while running as non-root.
    """
    if wrapper not in _PACKAGE_NAMES:
        raise ValueError(f"Unknown wrapper: {wrapper!r}")

    family, display = detect_family()
    if family is None:
        raise RuntimeError(
            "Could not detect your distribution's package manager. "
            "Please install the package manually and try again."
        )

    # Manual-only families — we don't automate NixOS / Guix / rpm-ostree
    # because the correct install path involves editing config and
    # rebooting, which the app can't safely do on the user's behalf.
    if family in _MANUAL_ONLY_FAMILIES:
        hint = _MANUAL_INSTALL_HINTS.get(wrapper, {}).get(family, "")
        raise RuntimeError(
            f"Automatic install isn't supported on {_MANUAL_ONLY_FAMILIES[family]} "
            f"because the correct install path involves editing system config "
            f"and/or rebooting. Please run one of:\n\n{hint}"
        )

    package = _PACKAGE_NAMES[wrapper].get(family)
    if package is None:
        raise RuntimeError(
            f"No known package name for {wrapper} on {display}. "
            "Please install it manually."
        )

    install_argv, prefetch_argv = _build_command(family, package)

    is_root = os.geteuid() == 0
    if not is_root and not has_polkit():
        raise RuntimeError(
            "pkexec is not available — cannot request admin privileges "
            "from a GUI. Install polkit, or run the install command "
            f"manually in a terminal:\n\n    sudo {' '.join(install_argv)}"
        )

    # Wrap in pkexec unless we're already root.
    if not is_root:
        install_argv = ["pkexec", *install_argv]
        if prefetch_argv is not None:
            prefetch_argv = ["pkexec", *prefetch_argv]

    return InstallPlan(
        wrapper=wrapper,
        package=package,
        family=family,
        display_name=display,
        command=install_argv,
        prefetch=prefetch_argv,
        needs_polkit=not is_root,
    )


@dataclass
class InstallResult:
    ok: bool
    exit_code: int
    cancelled: bool = False
    error_message: str = ""


class InstallProcess:
    """A cancellable, line-streaming subprocess runner.

    Not tied to any GUI framework — the caller passes an ``on_line``
    callback which will be invoked (on the *worker thread*) for each
    line of combined stdout/stderr. The caller is responsible for
    marshalling that back to the UI thread (``GLib.idle_add`` in our
    case).

    Use ``run()`` from a background thread. It blocks until the child
    exits or ``cancel()`` is called from any thread.
    """

    def __init__(
        self,
        plan: InstallPlan,
        on_line: Callable[[str], None],
        on_stage: Callable[[str], None] | None = None,
    ) -> None:
        self._plan = plan
        self._on_line = on_line
        self._on_stage = on_stage or (lambda _s: None)
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._cancelled = False

    # ── public API ──
    def cancel(self) -> None:
        """Ask the running child to terminate. Idempotent, thread-safe."""
        with self._lock:
            self._cancelled = True
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            # pkexec forwards SIGTERM to the wrapped process cleanly.
            proc.terminate()
        except ProcessLookupError:
            pass

    def run(self) -> InstallResult:
        """Run prefetch (if any), then install. Returns on completion."""
        env = env_for_install(self._plan.family)

        if self._plan.prefetch is not None:
            self._on_stage(f"Refreshing package index ({self._plan.family})…")
            self._on_line(f"$ {shlex.join(self._plan.prefetch)}")
            res = self._run_one(self._plan.prefetch, env)
            if res is not None:
                return res  # cancelled or failed

        self._on_stage(f"Installing {self._plan.package}…")
        self._on_line(f"$ {shlex.join(self._plan.command)}")
        res = self._run_one(self._plan.command, env)
        if res is not None:
            return res

        self._on_stage("Done.")
        return InstallResult(ok=True, exit_code=0)

    # ── internals ──
    def _run_one(self, argv: list[str], env: dict[str, str]) -> InstallResult | None:
        """Run one subprocess. Returns None on success, InstallResult otherwise."""
        with self._lock:
            if self._cancelled:
                return InstallResult(
                    ok=False, exit_code=-1, cancelled=True,
                    error_message="Cancelled before start.",
                )
            try:
                # Merge stderr into stdout so pacman's progress bars and
                # apt's warnings land in the same log the user reads.
                # start_new_session=True detaches from any controlling
                # terminal (belt & braces — we're already headless).
                self._proc = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,          # line-buffered
                    env=env,
                    start_new_session=True,
                )
            except FileNotFoundError as exc:
                msg = f"Command not found: {argv[0]}"
                self._on_line(f"error: {msg}")
                return InstallResult(ok=False, exit_code=-1, error_message=msg)
            except OSError as exc:
                msg = f"Could not start {argv[0]}: {exc}"
                self._on_line(f"error: {msg}")
                return InstallResult(ok=False, exit_code=-1, error_message=msg)
            proc = self._proc

        assert proc.stdout is not None
        # Iterating the file object is line-buffered thanks to bufsize=1;
        # this blocks the worker thread until the child closes stdout.
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                # pacman/apt sometimes emit \r-repainted progress bars.
                # Split on \r so the UI shows the latest state cleanly.
                for segment in line.split("\r"):
                    if segment:
                        self._on_line(segment)
        except Exception as exc:  # noqa: BLE001
            log.warning("Error while reading subprocess output: %s", exc)

        code = proc.wait()

        with self._lock:
            cancelled = self._cancelled
            self._proc = None

        if cancelled:
            return InstallResult(
                ok=False, exit_code=code, cancelled=True,
                error_message="Cancelled by user.",
            )

        if code == 0:
            return None  # success

        # pkexec exit codes:
        #   126 = user dismissed the auth dialog
        #   127 = authentication failed / not authorized
        if code == 126:
            msg = "Authentication dialog was dismissed."
        elif code == 127:
            msg = "Authentication failed."
        else:
            msg = f"Command failed with exit code {code}."
        self._on_line(f"error: {msg}")
        return InstallResult(ok=False, exit_code=code, error_message=msg)


def env_for_install(family: str) -> dict[str, str]:
    """Extra env vars for the subprocess — noninteractive frontends etc."""
    env = os.environ.copy()
    # Make apt-get shut up.
    if family == "debian":
        env["DEBIAN_FRONTEND"] = "noninteractive"
    # Make sure translated output doesn't confuse our log rendering.
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"
    return env
