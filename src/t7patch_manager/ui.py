"""GTK4 UI for t7patch-manager."""
from __future__ import annotations

import threading
import traceback
from importlib import resources
from pathlib import Path
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import __version__, config, installer, launch_wrappers, launcher, opener, paths, state, steam_config
from .logger import configure as configure_logging
from .settings import Settings

APP_ID = "io.github.heyiamusingarchbtw.T7PatchManager"
ISSUE_URL = "https://github.com/HeyIamUsingArchBtw/t7patch-manager/issues/new"

log = configure_logging()


# ── asset loading ───────────────────────────────────────────────────
def _find_data_file(name: str) -> Path | None:
    """Locate a bundled data file (CSS, SVG background) across install layouts.

    Search order:

    1. Packaged inside the wheel under ``t7patch_manager/data/<name>``
       (⇒ ``importlib.resources``).
    2. Sibling ``data/`` directory next to the package (source checkout /
       pipx --editable).
    3. Repo-root ``data/`` when running from a source checkout.

    Returns ``None`` if the file can't be found — the caller is expected to
    fall back gracefully (theme is a nice-to-have, not a hard requirement).
    """
    try:
        with resources.as_file(resources.files("t7patch_manager") / "data" / name) as p:
            if p.is_file():
                return Path(p)
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    here = Path(__file__).resolve().parent
    for candidate in (
        here / "data" / name,               # inside the package
        here.parent.parent / "data" / name, # <repo>/data (editable / source)
        here.parent.parent.parent / "data" / name,  # src-layout: <repo>/src/../data
    ):
        if candidate.is_file():
            return candidate
    return None


def _pango_tracking(label: Gtk.Label, *, spacing_1024: int = 1800) -> None:
    """Give *label* BO3-style letter tracking.

    GTK CSS ignores ``letter-spacing``, so we set it via a Pango attribute
    instead. Value is in 1/1024 of a point (Pango's unit).
    """
    attrs = Pango.AttrList.new()
    attrs.insert(Pango.attr_letter_spacing_new(spacing_1024 * Pango.SCALE // 1024))
    label.set_attributes(attrs)


def _apply_bo3_theme(display: Gdk.Display) -> None:
    """Load our custom CSS globally so every window inherits BO3 styling."""
    css_path = _find_data_file("style.css")
    if css_path is None:
        log.warning("style.css not found — falling back to default Adwaita.")
        return
    provider = Gtk.CssProvider()
    provider.load_from_path(str(css_path))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    log.debug("Loaded CSS from %s", css_path)


# ── background helper ───────────────────────────────────────────────
def run_in_thread(fn: Callable[..., None], *args, on_done: Callable[..., None] | None = None):
    """Run *fn* on a worker thread; schedule *on_done(result, error)* on the main loop."""
    def target():
        error, result = None, None
        try:
            result = fn(*args)
        except Exception as exc:  # noqa: BLE001
            log.exception("Background task failed")
            error = exc
        if on_done:
            GLib.idle_add(on_done, result, error)
    threading.Thread(target=target, daemon=True).start()


# ── error dialog with copy + report ─────────────────────────────────
def show_error_dialog(parent: Gtk.Window, heading: str, error: Exception):
    """Rich error dialog: full traceback in an expander, copy-to-clipboard, open issue."""
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__)).strip()
    detail = f"{type(error).__name__}: {error}\n\n{tb}"

    dlg = Adw.AlertDialog(
        heading=heading,
        body=str(error),
    )
    dlg.add_response("close", "Close")
    dlg.add_response("copy", "Copy details")
    dlg.add_response("report", "Report issue")
    dlg.set_default_response("close")
    dlg.set_close_response("close")

    def _on_resp(_d, resp):
        if resp == "copy":
            _copy_to_clipboard(parent, detail)
        elif resp == "report":
            try:
                opener.open_url(ISSUE_URL)
            except Exception:  # noqa: BLE001
                pass
    dlg.connect("response", _on_resp)
    dlg.present(parent)


def _copy_to_clipboard(widget: Gtk.Widget, text: str) -> None:
    display = widget.get_display() if hasattr(widget, "get_display") else Gdk.Display.get_default()
    if display:
        display.get_clipboard().set(text)


# ── config editor dialog ────────────────────────────────────────────
class ConfigDialog(Adw.Dialog):
    """Explicit Cancel / Save buttons for t7patch.conf."""

    def __init__(self, parent: Gtk.Window, conf_path: Path,
                 on_saved: Callable[[], None] | None = None):
        super().__init__()
        self.set_title("T7Patch Config")
        self.set_content_width(460)
        self._path = conf_path
        self._cfg = config.read(conf_path)
        self._on_saved = on_saved

        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)
        self.set_default_widget(save_btn)

        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        toolbar.set_content(body)

        grp = Adw.PreferencesGroup(
            title="In-game identity",
            description="Shown to other players.",
        )
        body.append(grp)

        self._name = Adw.EntryRow(title="Player name")
        self._name.set_text(self._cfg.playername)
        grp.add(self._name)

        self._pw = Adw.PasswordEntryRow(title="Network password")
        self._pw.set_text(self._cfg.networkpassword)
        grp.add(self._pw)

        self._friends = Adw.SwitchRow(
            title="Friends only",
            subtitle="Reject connections from anyone not on your friends list",
        )
        self._friends.set_active(self._cfg.isfriendsonly)
        grp.add(self._friends)

        self._name.connect("entry-activated", self._on_save)
        self._pw.connect("entry-activated", self._on_save)

        self.present(parent)

    def _on_save(self, *_):
        self._cfg.playername = self._name.get_text().strip() or "Unknown Soldier"
        self._cfg.networkpassword = self._pw.get_text()
        self._cfg.isfriendsonly = self._friends.get_active()
        try:
            config.write(self._path, self._cfg)
            if self._on_saved:
                self._on_saved()
        except Exception as exc:  # noqa: BLE001
            log.exception("Config save failed")
            show_error_dialog(self.get_parent() or self, "Could not save config", exc)
            return
        self.close()


# ── preferences dialog ──────────────────────────────────────────────
class PreferencesDialog(Adw.PreferencesDialog):
    """User overrides — BO3 path, T7Patch source, network timeout."""

    def __init__(self, parent: Gtk.Window, settings: Settings,
                 on_applied: Callable[[], None]):
        super().__init__()
        self.set_title("Preferences")
        self._s = settings
        self._on_applied = on_applied

        page = Adw.PreferencesPage(icon_name="preferences-system-symbolic")
        self.add(page)

        # ── BO3 path override ──
        g1 = Adw.PreferencesGroup(
            title="BO3 install path",
            description="Only set this if auto-detection can't find your BO3 folder.",
        )
        page.add(g1)

        self._bo3_row = Adw.EntryRow(title="Path to Black Ops III folder")
        if settings.bo3_dir_override:
            self._bo3_row.set_text(settings.bo3_dir_override)
        # Suffix: browse + clear
        pick = Gtk.Button(icon_name="folder-symbolic", tooltip_text="Browse…",
                         valign=Gtk.Align.CENTER, css_classes=["flat"])
        pick.connect("clicked", self._pick_bo3_dir)
        clear1 = Gtk.Button(icon_name="edit-clear-symbolic", tooltip_text="Clear",
                            valign=Gtk.Align.CENTER, css_classes=["flat"])
        clear1.connect("clicked", lambda *_: self._bo3_row.set_text(""))
        self._bo3_row.add_suffix(pick)
        self._bo3_row.add_suffix(clear1)
        g1.add(self._bo3_row)

        # ── Patch source override ──
        g2 = Adw.PreferencesGroup(
            title="T7Patch source override",
            description="Use a specific URL or local zip instead of the latest GitHub release.",
        )
        page.add(g2)

        self._src_row = Adw.EntryRow(title="URL or local file path")
        if settings.patch_source_override:
            self._src_row.set_text(settings.patch_source_override)
        pick2 = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Choose a local zip…",
                          valign=Gtk.Align.CENTER, css_classes=["flat"])
        pick2.connect("clicked", self._pick_zip_file)
        clear2 = Gtk.Button(icon_name="edit-clear-symbolic", tooltip_text="Clear",
                           valign=Gtk.Align.CENTER, css_classes=["flat"])
        clear2.connect("clicked", lambda *_: self._src_row.set_text(""))
        self._src_row.add_suffix(pick2)
        self._src_row.add_suffix(clear2)
        g2.add(self._src_row)

        # ── Steam launch options override ──
        g_launch = Adw.PreferencesGroup(
            title="Steam launch options",
            description=(
                "For 99% of users the defaults are correct. Only touch these "
                "if you added BO3 as a Non-Steam game or want a custom "
                "launch string. Note: while a custom launch string is set, "
                "the Performance-mode and Performance-monitoring switches on "
                "the main window are disabled because we can no longer safely "
                "rewrite the string for you."
            ),
        )
        page.add(g_launch)

        self._launchopts_pref_row = Adw.EntryRow(
            title='Launch string (default: WINEDLLOVERRIDES="dsound=n,b" %command%)',
        )
        if settings.launch_options_override:
            self._launchopts_pref_row.set_text(settings.launch_options_override)
        clear_lo = Gtk.Button(
            icon_name="edit-clear-symbolic", tooltip_text="Reset to default",
            valign=Gtk.Align.CENTER, css_classes=["flat"],
        )
        clear_lo.connect("clicked", lambda *_: self._launchopts_pref_row.set_text(""))
        self._launchopts_pref_row.add_suffix(clear_lo)
        g_launch.add(self._launchopts_pref_row)

        self._appid_pref_row = Adw.EntryRow(
            title="Steam AppID (default: 311210 = retail BO3)",
        )
        if settings.launch_options_appid_override:
            self._appid_pref_row.set_text(settings.launch_options_appid_override)
        detect_appid = Gtk.Button(
            label="Detect",
            tooltip_text="Scan Steam shortcuts for a BO3-looking Non-Steam game",
            valign=Gtk.Align.CENTER, css_classes=["flat"],
        )
        detect_appid.connect("clicked", self._detect_non_steam_appid)
        clear_appid = Gtk.Button(
            icon_name="edit-clear-symbolic", tooltip_text="Reset to default",
            valign=Gtk.Align.CENTER, css_classes=["flat"],
        )
        clear_appid.connect("clicked", lambda *_: self._appid_pref_row.set_text(""))
        self._appid_pref_row.add_suffix(detect_appid)
        self._appid_pref_row.add_suffix(clear_appid)
        g_launch.add(self._appid_pref_row)

        # ── Advanced (network) ──
        g3 = Adw.PreferencesGroup(
            title="Advanced",
            description="You probably don't need to touch this.",
        )
        page.add(g3)

        self._timeout_row = Adw.SpinRow.new_with_range(5, 300, 5)
        self._timeout_row.set_title("Network timeout (seconds)")
        self._timeout_row.set_value(settings.http_timeout)
        g3.add(self._timeout_row)

        # ── Action buttons ──
        g4 = Adw.PreferencesGroup()
        page.add(g4)

        apply_row = Adw.ActionRow()
        apply_row.set_title("Apply changes")
        apply_row.set_subtitle("Save these overrides and refresh the main window.")
        apply_btn = Gtk.Button(label="Apply", css_classes=["suggested-action", "pill"])
        apply_btn.connect("clicked", self._apply)
        apply_row.add_suffix(apply_btn)
        g4.add(apply_row)

        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset all overrides")
        reset_row.set_subtitle("Restore auto-detection defaults.")
        reset_btn = Gtk.Button(label="Reset", css_classes=["destructive-action", "pill"])
        reset_btn.connect("clicked", self._reset)
        reset_row.add_suffix(reset_btn)
        g4.add(reset_row)

        self.present(parent)

    # ── file/folder pickers ──
    def _pick_bo3_dir(self, _btn):
        dlg = Gtk.FileDialog(title="Pick your BO3 folder")
        dlg.select_folder(self.get_parent(), None, self._on_bo3_picked)

    def _on_bo3_picked(self, dlg, result):
        try:
            folder = dlg.select_folder_finish(result)
            if folder:
                self._bo3_row.set_text(folder.get_path())
        except GLib.Error:
            pass

    def _pick_zip_file(self, _btn):
        dlg = Gtk.FileDialog(title="Pick a T7Patch Linux zip")
        f = Gtk.FileFilter()
        f.set_name("Zip archives")
        f.add_pattern("*.zip")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        dlg.set_filters(filters)
        dlg.open(self.get_parent(), None, self._on_zip_picked)

    def _on_zip_picked(self, dlg, result):
        try:
            f = dlg.open_finish(result)
            if f:
                self._src_row.set_text(f.get_path())
        except GLib.Error:
            pass

    # ── save/reset ──
    def _apply(self, _btn):
        self._s.bo3_dir_override = self._bo3_row.get_text().strip() or None
        self._s.patch_source_override = self._src_row.get_text().strip() or None
        self._s.launch_options_override = self._launchopts_pref_row.get_text().strip() or None
        appid_raw = self._appid_pref_row.get_text().strip()
        # Only accept digit-only AppIDs — anything else is user error and we
        # ignore it rather than silently writing garbage to Steam's config.
        self._s.launch_options_appid_override = appid_raw if appid_raw.isdigit() else None
        self._s.http_timeout = int(self._timeout_row.get_value())
        try:
            self._s.save()
            log.info("Preferences saved: %s", self._s)
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to save preferences")
            show_error_dialog(self, "Could not save preferences", exc)
            return
        self._on_applied()
        self.close()

    def _reset(self, _btn):
        self._bo3_row.set_text("")
        self._src_row.set_text("")
        self._launchopts_pref_row.set_text("")
        self._appid_pref_row.set_text("")
        self._timeout_row.set_value(30)

    # ── Non-Steam AppID auto-detect ──
    def _detect_non_steam_appid(self, _btn):
        """Look through Steam's shortcuts.vdf files for a BO3-ish entry."""
        try:
            hits = steam_config.find_non_steam_bo3_shortcuts()
        except Exception as exc:  # noqa: BLE001
            show_error_dialog(self, "Could not scan Steam shortcuts", exc)
            return

        if not hits:
            dlg = Adw.AlertDialog(
                heading="No Non-Steam BO3 shortcut found",
                body=(
                    "Steam has no 'Non-Steam game' shortcut whose name or exe "
                    "looks like BO3.\n\n"
                    "If you added BO3 to Steam manually, make sure the shortcut "
                    "name contains 'BO3' or 'Black Ops 3', then try again. "
                    "Otherwise leave this field empty — the app will use the "
                    "default retail AppID 311210."
                ),
            )
            dlg.add_response("ok", "OK")
            dlg.present(self)
            return

        if len(hits) == 1:
            hit = hits[0]
            self._appid_pref_row.set_text(hit.appid)
            dlg = Adw.AlertDialog(
                heading="Non-Steam BO3 shortcut found",
                body=(
                    f"Filled in AppID {hit.appid} for shortcut “{hit.name}”.\n\n"
                    f"Exe: {hit.exe or '(unknown)'}"
                ),
            )
            dlg.add_response("ok", "OK")
            dlg.present(self)
            return

        # Multiple candidates — let the user pick.
        dlg = Adw.AlertDialog(
            heading="Multiple BO3 shortcuts found",
            body="Which one should we set launch options for?",
        )
        for i, hit in enumerate(hits):
            dlg.add_response(str(i), f"{hit.name}  ·  {hit.appid}")
        dlg.add_response("cancel", "Cancel")
        dlg.set_close_response("cancel")

        def on_resp(_d, resp):
            if resp == "cancel" or not resp.isdigit():
                return
            self._appid_pref_row.set_text(hits[int(resp)].appid)

        dlg.connect("response", on_resp)
        dlg.present(self)


# ── debug log dialog ────────────────────────────────────────────────
class LogDialog(Adw.Dialog):
    def __init__(self, parent: Gtk.Window):
        super().__init__()
        self.set_title("Debug log")
        self.set_content_width(720)
        self.set_content_height(520)

        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        header = Adw.HeaderBar()
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda *_: self.close())
        header.pack_start(close_btn)

        copy_btn = Gtk.Button(label="Copy", css_classes=["flat"])
        copy_btn.connect("clicked", self._on_copy)
        header.pack_end(copy_btn)

        open_btn = Gtk.Button(label="Open file", css_classes=["flat"])
        open_btn.connect("clicked", self._on_open)
        header.pack_end(open_btn)

        toolbar.add_top_bar(header)

        # Text view
        self._buf = Gtk.TextBuffer()
        tv = Gtk.TextView(buffer=self._buf, editable=False, monospace=True,
                          wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroller = Gtk.ScrolledWindow(child=tv, vexpand=True, hexpand=True)
        scroller.set_margin_top(6); scroller.set_margin_bottom(12)
        scroller.set_margin_start(12); scroller.set_margin_end(12)
        toolbar.set_content(scroller)

        # Load file contents
        try:
            self._buf.set_text(paths.log_file().read_text(encoding="utf-8", errors="ignore"))
            end = self._buf.get_end_iter()
            tv.scroll_to_iter(end, 0, False, 0, 0)
        except OSError as e:
            self._buf.set_text(f"(could not read log: {e})")

        self.present(parent)

    def _on_copy(self, _btn):
        s, e = self._buf.get_bounds()
        _copy_to_clipboard(self, self._buf.get_text(s, e, False))

    def _on_open(self, _btn):
        try:
            opener.open_folder(paths.log_file().parent)
        except Exception as exc:  # noqa: BLE001
            show_error_dialog(self, "Could not open log folder", exc)


# ── main window ─────────────────────────────────────────────────────
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self.set_title("T7Patch Manager")
        self.set_default_size(620, 660)
        self.add_css_class("bo3")

        self._settings = Settings.load()
        self._bo3_dir: Path | None = self._resolve_bo3_dir()
        self._status: state.PatchStatus | None = None
        self._latest_tag: str | None = None
        self._downloading = False

        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        header.set_title_widget(self._build_header_title())
        toolbar.add_top_bar(header)

        menu = Gio.Menu()
        menu.append("Edit t7patch.conf…", "app.edit-config")
        menu.append("Check for updates", "app.check-updates")
        menu.append("Open BO3 folder", "app.open-bo3")
        menu.append("Preferences…", "app.prefs")
        menu.append("Debug log…", "app.log")
        menu.append("Uninstall T7Patch…", "app.uninstall")
        menu.append("About", "app.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))

        # Overlay: painted BO3 background at the bottom, semi-transparent content on top.
        stage = Gtk.Overlay()
        stage.add_css_class("bo3-root")
        toolbar.set_content(stage)

        bg = self._build_background()
        if bg is not None:
            stage.set_child(bg)

        self._toaster = Adw.ToastOverlay()
        stage.add_overlay(self._toaster)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20,
                          margin_top=24, margin_bottom=24, margin_start=28, margin_end=28)
        self._toaster.set_child(content)

        # Update banner
        self._banner = Adw.Banner()
        self._banner.set_revealed(False)
        content.append(self._banner)

        # Hero block: big "T7 PATCH" title + tagline
        content.append(self._build_hero())

        # Status
        status_group = Adw.PreferencesGroup(title="System")
        content.append(status_group)

        self._bo3_row = Adw.ActionRow(title="Black Ops III")
        self._bo3_row.set_subtitle("Detecting…")
        self._bo3_row_fix = Gtk.Button(label="Set path…")
        self._bo3_row_fix.connect("clicked", lambda *_: self._open_prefs())
        self._bo3_row_fix.set_visible(False)
        self._bo3_row.add_suffix(self._bo3_row_fix)
        status_group.add(self._bo3_row)

        self._patch_row = Adw.ActionRow(title="T7Patch")
        self._patch_row.set_subtitle("Detecting…")
        self._patch_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._patch_switch_handler = self._patch_switch.connect("state-set", self._on_toggle)
        self._patch_row.add_suffix(self._patch_switch)
        status_group.add(self._patch_row)

        # Actions
        actions_group = Adw.PreferencesGroup(title="Actions")
        content.append(actions_group)

        self._install_btn = Gtk.Button(label="Install T7Patch",
                                       css_classes=["suggested-action"])
        self._install_btn.connect("clicked", self._on_install)
        self._install_row = Adw.ActionRow(title="T7Patch",
                                          subtitle="Loading release info…")
        self._install_row.add_suffix(self._install_btn)
        actions_group.add(self._install_row)

        self._config_btn = Gtk.Button(label="Edit…")
        self._config_btn.connect("clicked", lambda *_: self._open_config_dialog())
        cfg_row = Adw.ActionRow(title="In-game name & network password",
                                subtitle="Edit t7patch.conf")
        cfg_row.add_suffix(self._config_btn)
        actions_group.add(cfg_row)

        # Steam launch-options row — auto-set the WINEDLLOVERRIDES line.
        self._launchopts_btn = Gtk.Button(label="Set automatically")
        self._launchopts_btn.connect("clicked", self._on_set_launch_options)
        self._launchopts_row = Adw.ActionRow(
            title="Steam launch options",
            subtitle="Checking…",
        )
        self._launchopts_row.add_suffix(self._launchopts_btn)
        actions_group.add(self._launchopts_row)

        # GameMode toggle — wraps BO3 in gamemoderun via LaunchOptions.
        self._gamemode_row = Adw.SwitchRow(
            title="Performance mode (GameMode)",
            subtitle="Checking…",
        )
        # Guard so programmatic ``set_active`` during refresh doesn't fire
        # the user-toggle handler.
        self._gamemode_row_signal_blocked = False
        self._gamemode_handler_id = self._gamemode_row.connect(
            "notify::active", self._on_wrapper_toggled, "gamemoderun"
        )
        actions_group.add(self._gamemode_row)

        # MangoHud toggle — wraps BO3 in mangohud via LaunchOptions.
        self._mangohud_row = Adw.SwitchRow(
            title="Performance monitoring (MangoHud)",
            subtitle="Checking…",
        )
        self._mangohud_row_signal_blocked = False
        self._mangohud_handler_id = self._mangohud_row.connect(
            "notify::active", self._on_wrapper_toggled, "mangohud"
        )
        actions_group.add(self._mangohud_row)

        # Big Play button, centred
        self._play_btn = Gtk.Button(label="▶  Launch BO3",
                                    css_classes=["bo3-play"])
        self._play_btn.connect("clicked", self._on_play)
        play_row = Gtk.CenterBox(margin_top=6, margin_bottom=6)
        play_row.set_center_widget(self._play_btn)
        content.append(play_row)

        # No standalone footer hint anymore — the new launch-options row in
        # the Actions section handles that job interactively.

        self._refresh_status()
        self._refresh_launch_options()
        self._check_latest_async()

    # ── header / hero builders ──
    def _build_header_title(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER)
        title = Gtk.Label(label="T7 PATCH", css_classes=["bo3-accent"])
        _pango_tracking(title, spacing_1024=2600)
        subtitle = Gtk.Label(label="MANAGER", css_classes=["bo3-mono"])
        _pango_tracking(subtitle, spacing_1024=3200)
        box.append(title)
        box.append(subtitle)
        return box

    def _build_background(self) -> Gtk.Widget | None:
        svg_path = _find_data_file("bo3-bg.svg")
        if svg_path is None:
            log.debug("bo3-bg.svg not bundled — skipping decorative background.")
            return None
        pic = Gtk.Picture.new_for_filename(str(svg_path))
        pic.set_content_fit(Gtk.ContentFit.COVER)
        pic.set_can_focus(False)
        pic.set_can_target(False)
        pic.set_hexpand(True)
        pic.set_vexpand(True)
        # A hair of extra dimming on top of the SVG's own vignette — keeps
        # foreground text comfortably readable at all window sizes.
        pic.set_opacity(0.9)
        return pic

    def _build_hero(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                      margin_bottom=6, halign=Gtk.Align.CENTER)
        title = Gtk.Label(label="BLACK OPS III", css_classes=["bo3-title"])
        title.set_xalign(0.5)
        _pango_tracking(title, spacing_1024=4800)
        sub = Gtk.Label(label="T7 Patch · Multiplayer connectivity fix",
                        css_classes=["bo3-subtitle"])
        sub.set_xalign(0.5)
        _pango_tracking(sub, spacing_1024=1200)
        box.append(title)
        box.append(sub)
        return box

    # ── resolvers ──
    def _resolve_bo3_dir(self) -> Path | None:
        """Manual override wins; otherwise auto-detect."""
        override = self._settings.effective_bo3_dir()
        if override:
            log.info("Using BO3 override path: %s", override)
            return override
        detected = paths.find_bo3_dir()
        if detected:
            log.info("Auto-detected BO3: %s", detected)
        else:
            log.warning("BO3 not found in any known Steam library.")
        return detected

    # ── status ──
    def _refresh_status(self):
        if not self._bo3_dir:
            self._bo3_row.set_subtitle(
                "Not found — set the path manually below, or install BO3 in Steam."
            )
            self._bo3_row_fix.set_visible(True)
            self._patch_row.set_subtitle("BO3 not detected")
            self._install_row.set_subtitle("BO3 must be located first")
            self._install_btn.set_sensitive(False)
            self._play_btn.set_sensitive(False)
            self._config_btn.set_sensitive(False)
            self._patch_switch.set_sensitive(False)
            return

        self._bo3_row_fix.set_visible(False)
        self._bo3_row.set_subtitle(str(self._bo3_dir))
        try:
            self._status = state.detect(self._bo3_dir)
        except Exception as exc:  # noqa: BLE001
            log.exception("state.detect failed")
            self._patch_row.set_subtitle(f"Error: {exc}")
            return

        st = self._status
        ver_txt = st.installed_version or "installed"

        self._patch_switch.handler_block(self._patch_switch_handler)
        try:
            if st.state is state.PatchState.NOT_INSTALLED:
                self._patch_row.set_subtitle("Not installed")
                self._patch_switch.set_sensitive(False)
                self._patch_switch.set_active(False)
                self._config_btn.set_sensitive(False)
                self._play_btn.set_sensitive(True)
            elif st.state is state.PatchState.ENABLED:
                self._patch_row.set_subtitle(f"Enabled  ·  {ver_txt}")
                self._patch_switch.set_sensitive(True)
                self._patch_switch.set_active(True)
                self._config_btn.set_sensitive(st.conf_exists)
                self._play_btn.set_sensitive(True)
            elif st.state is state.PatchState.DISABLED:
                self._patch_row.set_subtitle(f"Disabled  ·  {ver_txt}")
                self._patch_switch.set_sensitive(True)
                self._patch_switch.set_active(False)
                self._config_btn.set_sensitive(st.conf_exists)
                self._play_btn.set_sensitive(True)
        finally:
            self._patch_switch.handler_unblock(self._patch_switch_handler)

        self._update_install_row()

    def _update_install_row(self):
        st = self._status
        latest = self._latest_tag
        if not st:
            return

        if st.state is state.PatchState.NOT_INSTALLED:
            self._install_row.set_subtitle(
                f"Not installed. Latest release: {latest}." if latest else "Not installed."
            )
            self._install_btn.set_label(f"Install {latest}" if latest else "Install T7Patch")
            self._install_btn.set_sensitive(True)
            self._install_btn.set_css_classes(["suggested-action", "pill"])
        else:
            installed = st.installed_version
            if latest and installed and installed != latest:
                self._install_row.set_subtitle(
                    f"Installed: {installed}  ·  Update available: {latest}"
                )
                self._install_btn.set_label(f"Update to {latest}")
                self._install_btn.set_css_classes(["suggested-action", "pill"])
            elif latest and installed and installed == latest:
                self._install_row.set_subtitle(f"Up to date  ·  {installed}")
                self._install_btn.set_label("Reinstall")
                self._install_btn.set_css_classes(["pill"])
            elif latest:
                self._install_row.set_subtitle(
                    f"Installed (version unknown). Latest: {latest}."
                )
                self._install_btn.set_label(f"Reinstall {latest}")
                self._install_btn.set_css_classes(["pill"])
            else:
                self._install_row.set_subtitle("Installed.")
                self._install_btn.set_label("Reinstall")
                self._install_btn.set_css_classes(["pill"])
            self._install_btn.set_sensitive(True)

    # ── async update check ──
    def _check_latest_async(self, *, user_initiated: bool = False):
        repo = self._settings.effective_repo()
        timeout = self._settings.http_timeout
        override = self._settings.patch_source_override

        # Visible feedback while the network call runs.
        self._install_row.set_subtitle("Checking for updates…")
        if user_initiated:
            self._toast("Checking for updates…", timeout=2)

        def _done(result, error):
            if error or not result:
                if self._status and self._status.state is state.PatchState.NOT_INSTALLED:
                    self._install_row.set_subtitle("Not installed. (Update check failed)")
                elif self._status:
                    self._install_row.set_subtitle("Installed. (Update check failed)")
                if error:
                    log.warning("Update check failed: %s", error)
                    if user_initiated:
                        self._toast(f"Update check failed: {error}")
                return
            self._latest_tag = result.tag
            log.info("Latest T7Patch: %s (from %s)", result.tag, result.source)

            if self._status and self._status.state is not state.PatchState.NOT_INSTALLED \
               and not self._status.installed_version and self._bo3_dir \
               and result.source == "github":
                try:
                    state.write_version_marker(self._bo3_dir, result.tag)
                    self._status = state.detect(self._bo3_dir)
                except Exception:  # noqa: BLE001
                    pass

            self._update_install_row()

            installed = self._status.installed_version if self._status else None
            if installed and installed != result.tag and result.source == "github":
                self._banner.set_title(f"Update available: {result.tag} (installed: {installed})")
                self._banner.set_button_label("Update now")
                self._banner.connect("button-clicked", lambda *_: self._on_install(None))
                self._banner.set_revealed(True)
            else:
                self._banner.set_revealed(False)

            if user_initiated:
                if installed and installed == result.tag:
                    self._toast(f"You're on the latest: {result.tag}")
                elif installed and result.source == "github":
                    self._toast(f"Update available: {result.tag}")
                elif not installed:
                    self._toast(f"Latest T7Patch: {result.tag}")
                else:
                    self._toast(f"Latest: {result.tag}")

        run_in_thread(installer.fetch_latest_release, repo, timeout, override, on_done=_done)

    # ── handlers ──
    def _on_toggle(self, sw: Gtk.Switch, val: bool) -> bool:
        if not self._bo3_dir or self._downloading:
            return False
        try:
            state.set_enabled(self._bo3_dir, val)
            self._toast("T7Patch enabled" if val else "T7Patch disabled")
            log.info("Patch toggled: %s", "on" if val else "off")
        except Exception as exc:  # noqa: BLE001
            log.exception("Toggle failed")
            show_error_dialog(self, "Could not toggle T7Patch", exc)
        GLib.idle_add(self._refresh_status)
        return False

    # ── Steam launch options ──
    def _target_launch_options(self, *, preserve_wrappers_from: str = "") -> str:
        """Return the string the user wants written.

        If a custom override is set in Preferences it wins verbatim.
        Otherwise we start from the safe default and — if
        *preserve_wrappers_from* is a real Steam value — carry over any
        known wrappers (``gamemoderun`` / ``mangohud``) the user already
        had enabled, so the “Set automatically” button never silently
        strips them.
        """
        if self._settings.launch_options_override:
            return self._settings.launch_options_override

        result = steam_config.BO3_LAUNCH_OPTIONS
        if preserve_wrappers_from:
            for wrapper in launch_wrappers.KNOWN_WRAPPERS:
                st = launch_wrappers.status_for(preserve_wrappers_from, wrapper)
                if st.enabled and st.installed:
                    result = launch_wrappers.toggle_wrapper(result, wrapper, enable=True)
        return result

    def _target_appid(self) -> str:
        """AppID whose LaunchOptions we set — override for Non-Steam BO3."""
        return (self._settings.launch_options_appid_override
                or steam_config.BO3_APPID)

    def _refresh_launch_options(self):
        """Poll ``localconfig.vdf`` in a worker thread and update the row."""
        appid = self._target_appid()

        # Reflect the active AppID in the row title so an override is obvious.
        if appid == steam_config.BO3_APPID:
            self._launchopts_row.set_title("Steam launch options")
        else:
            self._launchopts_row.set_title(
                f"Steam launch options (Non-Steam AppID {appid})"
            )

        def worker():
            # Fetch the raw status first, then decide what "OK" means
            # based on whichever wrappers are currently enabled.
            status = steam_config.check_status(appid=appid)
            expected = self._target_launch_options(
                preserve_wrappers_from=status.current or ""
            )
            # Re-tag matches_target against our wrapper-aware expected value.
            status.matches_target = (status.current == expected)
            return status

        def done(status, error):
            if error is not None:
                log.warning("launch-options check failed: %s", error)
                self._launchopts_row.set_subtitle(
                    "Could not read Steam config — set it manually in Steam."
                )
                self._launchopts_btn.set_sensitive(False)
                return

            if status.config is None:
                self._launchopts_row.set_subtitle(
                    "No Steam profile found — launch Steam once, then re-check."
                )
                self._launchopts_btn.set_label("Retry")
                self._launchopts_btn.set_sensitive(True)
                self._launchopts_btn.remove_css_class("suggested-action")
                return

            profile = status.config.steam_uid
            if status.matches_target:
                self._launchopts_row.set_subtitle(f"OK · already set for profile {profile}")
                self._launchopts_btn.set_label("Re-apply")
                self._launchopts_btn.remove_css_class("suggested-action")
                self._launchopts_btn.set_sensitive(True)
            elif status.current:
                short = status.current if len(status.current) < 60 else status.current[:57] + "…"
                self._launchopts_row.set_subtitle(
                    f"Different value set for {profile}: {short}"
                )
                self._launchopts_btn.set_label("Overwrite")
                self._launchopts_btn.add_css_class("suggested-action")
                self._launchopts_btn.set_sensitive(True)
            else:
                self._launchopts_row.set_subtitle(f"Not set for profile {profile}")
                self._launchopts_btn.set_label("Set automatically")
                self._launchopts_btn.add_css_class("suggested-action")
                self._launchopts_btn.set_sensitive(True)

            # Sync the wrapper switches to what's actually in the config.
            self._sync_wrapper_rows(status.current or "")

        run_in_thread(worker, on_done=done)

    # ── Wrapper switches (GameMode / MangoHud) ──
    def _sync_wrapper_rows(self, current_launch_options: str) -> None:
        """Reflect the on-disk LaunchOptions state in the two switch rows.

        Never triggers the user-toggle handler — we set the switch value
        under a signal-block guard, then update the subtitle text.
        """
        overridden = bool(self._settings.launch_options_override)
        for wrapper, row, handler_id, human in (
            ("gamemoderun", self._gamemode_row, self._gamemode_handler_id, "GameMode"),
            ("mangohud", self._mangohud_row, self._mangohud_handler_id, "MangoHud"),
        ):
            st = launch_wrappers.status_for(current_launch_options, wrapper)

            # Compose subtitle.
            if not st.installed:
                subtitle = f"{wrapper} not installed — install it first"
                row.set_sensitive(False)
            elif overridden:
                subtitle = (
                    "Disabled while a custom launch string is set in Preferences."
                )
                row.set_sensitive(False)
            else:
                subtitle = f"On — wraps BO3 in {wrapper}" if st.enabled \
                    else f"Off — add {wrapper} wrapper on next Set"
                row.set_sensitive(True)

            row.set_subtitle(subtitle)

            # Update the switch without firing our own toggle handler.
            row.handler_block(handler_id)
            try:
                row.set_active(st.enabled)
            finally:
                row.handler_unblock(handler_id)

    def _on_wrapper_toggled(self, row: Adw.SwitchRow, _pspec, wrapper: str) -> None:
        """User flipped a wrapper switch — rewrite LaunchOptions accordingly.

        Reuses the same close-Steam-first UX as ``_on_set_launch_options``.
        On any failure we roll the visual switch back to whatever's actually
        on disk.
        """
        enable = row.get_active()

        # Refuse when the user has a custom launch string in Preferences —
        # touching it via a toggle would be confusing.
        if self._settings.launch_options_override:
            self._toast(
                "Custom launch string is active in Preferences — toggles disabled."
            )
            self._refresh_launch_options()
            return

        # Not installed? Show a helpful hint and roll back the switch.
        if not launch_wrappers.is_installed(wrapper):
            self._show_install_hint(wrapper)
            self._refresh_launch_options()
            return

        # Pick the correct config + rewrite the string.
        status = steam_config.check_status(appid=self._target_appid())
        if status.config is None:
            self._toast("No Steam profile found. Launch Steam once first.")
            self._refresh_launch_options()
            return

        base = status.current or self._target_launch_options()
        new_value = launch_wrappers.toggle_wrapper(base, wrapper, enable=enable)

        # If nothing actually changed, do nothing (avoids re-writing the file).
        if new_value == (status.current or ""):
            return

        if steam_config.is_steam_running():
            self._prompt_close_steam_then_write(status.config, new_value, wrapper, enable)
            return

        self._write_launch_options(status.config, new_value, wrapper, enable)

    def _write_launch_options(
        self,
        cfg: "steam_config.LocalConfig",
        new_value: str,
        wrapper: str,
        enabled: bool,
    ) -> None:
        """Write *new_value* to localconfig.vdf; refresh UI on completion."""
        appid = self._target_appid()

        def worker():
            steam_config.set_launch_options(cfg, new_value, appid=appid)
            return True

        def done(_res, error):
            if error is not None:
                show_error_dialog(self, f"Could not toggle {wrapper}", error)
                self._refresh_launch_options()
                return
            verb = "enabled" if enabled else "disabled"
            self._toast(f"{wrapper} {verb} — active on next Steam start.")
            self._refresh_launch_options()

        run_in_thread(worker, on_done=done)

    def _prompt_close_steam_then_write(
        self,
        cfg: "steam_config.LocalConfig",
        new_value: str,
        wrapper: str,
        enabled: bool,
    ) -> None:
        dlg = Adw.AlertDialog(
            heading="Steam is running",
            body=(
                f"Toggling {wrapper} needs to write to Steam's config, and "
                "Steam overwrites that file when it exits. Close Steam now "
                "and apply the change?"
            ),
            close_response="cancel",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("close-steam", "Close Steam & apply")
        dlg.set_response_appearance("close-steam", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("close-steam")

        appid = self._target_appid()

        def on_response(_dlg, resp):
            if resp != "close-steam":
                # User cancelled — put the switch back where it was.
                self._refresh_launch_options()
                return

            def worker():
                if not steam_config.request_steam_shutdown():
                    raise RuntimeError(
                        "Could not send 'steam -shutdown'. Please close Steam manually."
                    )
                if not steam_config.wait_for_steam_to_exit(timeout=25.0):
                    raise TimeoutError(
                        "Steam did not exit within 25 s. Please close it manually and retry."
                    )
                steam_config.set_launch_options(cfg, new_value, appid=appid)
                return True

            def done(_res, error):
                if error is not None:
                    show_error_dialog(self, f"Could not toggle {wrapper}", error)
                    self._refresh_launch_options()
                    return
                verb = "enabled" if enabled else "disabled"
                self._toast(f"{wrapper} {verb} — you can start Steam again.")
                self._refresh_launch_options()

            run_in_thread(worker, on_done=done)

        dlg.connect("response", on_response)
        dlg.present(self)

    def _show_install_hint(self, wrapper: str) -> None:
        hints = launch_wrappers.INSTALL_HINTS.get(wrapper, {})
        body_lines = [f"{wrapper} isn't installed on your system.", "", "Install it with your distro's package manager:"]
        for label, cmd in (
            ("Arch / CachyOS / Manjaro", hints.get("arch")),
            ("Fedora", hints.get("fedora")),
            ("Debian / Ubuntu / Mint", hints.get("debian")),
            ("openSUSE", hints.get("opensuse")),
            ("Flatpak Steam", hints.get("flatpak")),
        ):
            if cmd:
                body_lines.append(f"• {label}:  {cmd}")

        dlg = Adw.AlertDialog(
            heading=f"{wrapper} not installed",
            body="\n".join(body_lines),
        )
        dlg.add_response("ok", "OK")
        dlg.present(self)

    def _on_set_launch_options(self, _btn):
        """Write ``WINEDLLOVERRIDES="dsound=n,b" %command%`` into localconfig.vdf.

        If Steam is running, ask the user (via a dialog) whether we may
        shut it down; otherwise refuse.
        """
        status = steam_config.check_status(appid=self._target_appid())
        if status.config is None:
            self._toast("No Steam profile found. Launch Steam once first.")
            self._refresh_launch_options()
            return

        if steam_config.is_steam_running():
            self._prompt_close_steam_then_apply(status.config, status.current or "")
            return

        self._do_apply_launch_options(status.config, status.current or "")

    def _prompt_close_steam_then_apply(self, cfg: steam_config.LocalConfig, current: str = "") -> None:
        dlg = Adw.AlertDialog(
            heading="Steam is running",
            body=(
                "Steam overwrites its config file when it exits, so any changes we "
                "make right now would be lost.\n\n"
                "Close Steam now and apply the launch options?"
            ),
            close_response="cancel",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("close-steam", "Close Steam & apply")
        dlg.set_response_appearance("close-steam", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("close-steam")

        def on_response(_dlg, resp):
            if resp != "close-steam":
                return
            self._launchopts_btn.set_sensitive(False)
            self._launchopts_row.set_subtitle("Closing Steam…")

            target = self._target_launch_options(preserve_wrappers_from=current)
            appid = self._target_appid()

            def worker():
                if not steam_config.request_steam_shutdown():
                    raise RuntimeError(
                        "Could not send 'steam -shutdown'. Please close Steam manually."
                    )
                if not steam_config.wait_for_steam_to_exit(timeout=25.0):
                    raise TimeoutError(
                        "Steam did not exit within 25 s. Please close it manually and retry."
                    )
                steam_config.set_launch_options(cfg, target, appid=appid)
                return True

            def done(_res, error):
                if error is not None:
                    show_error_dialog(self, "Could not set launch options", error)
                    self._refresh_launch_options()
                    return
                self._toast("Launch options applied — you can start Steam again.")
                self._refresh_launch_options()

            run_in_thread(worker, on_done=done)

        dlg.connect("response", on_response)
        dlg.present(self)

    def _do_apply_launch_options(self, cfg: steam_config.LocalConfig, current: str = "") -> None:
        """Apply the launch-options write (Steam already confirmed not running)."""
        self._launchopts_btn.set_sensitive(False)
        self._launchopts_row.set_subtitle("Writing localconfig.vdf…")
        target = self._target_launch_options(preserve_wrappers_from=current)
        appid = self._target_appid()

        def worker():
            steam_config.set_launch_options(cfg, target, appid=appid)
            return True

        def done(_res, error):
            if error is not None:
                show_error_dialog(self, "Could not set launch options", error)
                self._refresh_launch_options()
                return
            self._toast("Launch options applied.")
            self._refresh_launch_options()

        run_in_thread(worker, on_done=done)

    def _on_play(self, _btn):
        try:
            launcher.launch_bo3()
            self._toast("Launching BO3 via Steam…")
            log.info("Launch requested")
        except Exception as exc:  # noqa: BLE001
            log.exception("Launch failed")
            show_error_dialog(self, "Could not launch BO3", exc)

    def _on_install(self, _btn):
        if not self._bo3_dir or self._downloading:
            return
        self._downloading = True
        self._install_btn.set_sensitive(False)

        repo = self._settings.effective_repo()
        timeout = self._settings.http_timeout
        override = self._settings.patch_source_override

        progress = Adw.AlertDialog(
            heading="Installing T7Patch",
            body="Fetching release info…",
            close_response="cancel",
        )
        progress.present(self)

        def do_install():
            info = installer.fetch_latest_release(repo=repo, timeout=timeout,
                                                  override_source=override)
            def _p(got, total):
                pct = (got / total * 100) if total else 0
                GLib.idle_add(progress.set_body, f"Downloading {info.tag} — {pct:0.0f}%")
            zip_bytes = installer.download_zip(info.linux_asset_url,
                                               on_progress=_p, timeout=timeout)
            GLib.idle_add(progress.set_body, "Extracting…")
            installer.extract_patch_into(self._bo3_dir, zip_bytes)
            if info.source == "github":
                state.write_version_marker(self._bo3_dir, info.tag)
            return info.tag

        def _done(tag, error):
            self._downloading = False
            self._install_btn.set_sensitive(True)
            progress.close()
            if error:
                show_error_dialog(self, "Install failed", error)
            else:
                self._toast(f"Installed T7Patch {tag}")
                log.info("Installed T7Patch %s", tag)
                self._banner.set_revealed(False)
                self._latest_tag = tag
            self._refresh_status()

        run_in_thread(do_install, on_done=_done)

    def _open_config_dialog(self):
        if not self._bo3_dir:
            return
        ConfigDialog(self, self._bo3_dir / "t7patch.conf",
                     on_saved=lambda: self._toast("Config saved"))

    def _open_prefs(self):
        PreferencesDialog(self, self._settings, on_applied=self._on_prefs_applied)

    def _on_prefs_applied(self):
        # Re-resolve everything with the new settings
        self._bo3_dir = self._resolve_bo3_dir()
        self._latest_tag = None
        self._refresh_status()
        self._refresh_launch_options()
        self._check_latest_async()
        self._toast("Preferences applied")

    def _toast(self, msg: str, timeout: int = 4):
        t = Adw.Toast.new(msg)
        t.set_timeout(timeout)
        self._toaster.add_toast(t)


# ── application ─────────────────────────────────────────────────────
class T7PatchApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._window: MainWindow | None = None

    def do_activate(self):  # noqa: N802
        # Force the dark libadwaita variant so our CSS lands on the intended
        # base palette regardless of the desktop's global preference.
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        display = Gdk.Display.get_default()
        if display is not None:
            _apply_bo3_theme(display)

        if not self._window:
            self._window = MainWindow(self)
            self._install_actions()
        self._window.present()

    def _install_actions(self):
        w = self._window
        actions = (
            ("edit-config",   lambda *_: w._open_config_dialog()),
            ("check-updates", lambda *_: w._check_latest_async(user_initiated=True)),
            ("open-bo3",      lambda *_: self._open_bo3_folder()),
            ("prefs",         lambda *_: w._open_prefs()),
            ("log",           lambda *_: LogDialog(w)),
            ("uninstall",     lambda *_: self._confirm_uninstall()),
            ("about",         lambda *_: self._show_about()),
        )
        for name, cb in actions:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)

    def _open_bo3_folder(self):
        w = self._window
        if not w._bo3_dir:
            w._toast("BO3 folder unknown. Set the path in Preferences.")
            return
        try:
            opener.open_folder(w._bo3_dir)
        except Exception as exc:  # noqa: BLE001
            show_error_dialog(w, "Could not open folder", exc)

    def _confirm_uninstall(self):
        w = self._window
        if not w._bo3_dir:
            return
        dlg = Adw.AlertDialog(
            heading="Uninstall T7Patch?",
            body="This removes the patch DLLs from your BO3 folder. "
                 "Your t7patch.conf is kept.",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("confirm", "Uninstall")
        dlg.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def _on(_d, resp):
            if resp != "confirm":
                return
            try:
                removed = installer.uninstall(w._bo3_dir)
                w._toast(f"Removed {len(removed)} file(s)")
                log.info("Uninstalled %d file(s)", len(removed))
                # Force the UI back to a clean 'not installed' state:
                # detection now sees no DLLs and no version marker.
                w._banner.set_revealed(False)
                w._refresh_status()
                # Kick off a fresh update-check so the Actions row shows
                # the latest tag as installable again.
                w._check_latest_async()
            except Exception as exc:  # noqa: BLE001
                log.exception("Uninstall failed")
                show_error_dialog(w, "Uninstall failed", exc)
                w._refresh_status()

        dlg.connect("response", _on)
        dlg.present(w)

    def _show_about(self):
        """Custom About dialog with fully English labels.

        Adw.AboutDialog picks up the system locale for its built-in labels
        (Details, Website, License …), which we don't want here — the
        project's language is English. We render our own instead.
        """
        dlg = Adw.Dialog()
        dlg.set_title("About")
        dlg.set_content_width(420)

        toolbar = Adw.ToolbarView()
        dlg.set_child(toolbar)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda *_: dlg.close())
        header.pack_end(close_btn)
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=24, margin_bottom=20, margin_start=24, margin_end=24)
        toolbar.set_content(body)

        icon = Gtk.Image.new_from_icon_name(APP_ID)
        icon.set_pixel_size(96)
        icon.set_margin_bottom(4)
        body.append(icon)

        name_lbl = Gtk.Label(label="T7Patch Manager")
        name_lbl.add_css_class("title-1")
        body.append(name_lbl)

        version_lbl = Gtk.Label(label=f"Version {__version__}")
        version_lbl.add_css_class("dim-label")
        body.append(version_lbl)

        summary = Gtk.Label(
            label="Install, launch, toggle and configure T7Patch v3\n"
                  "for Call of Duty: Black Ops III on Linux.",
            justify=Gtk.Justification.CENTER,
            wrap=True,
        )
        summary.set_margin_top(8)
        body.append(summary)

        links_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                            halign=Gtk.Align.CENTER)
        links_box.set_margin_top(12)
        for label, url in (
            ("Website",       "https://github.com/HeyIamUsingArchBtw/t7patch-manager"),
            ("Report an issue", ISSUE_URL),
        ):
            b = Gtk.Button(label=label, css_classes=["pill"])
            b.connect("clicked", lambda _b, u=url: self._open_link(u))
            links_box.append(b)
        body.append(links_box)

        # Credits
        credits_group = Adw.PreferencesGroup()
        credits_group.set_margin_top(16)
        body.append(credits_group)

        for title, name, url in (
            ("App", "HeyIamUsingArchBtw",
             "https://github.com/HeyIamUsingArchBtw/t7patch-manager"),
            ("T7Patch v3", "Scroptss", "https://github.com/Scroptss/T7Patch"),
            ("Original T7Patch", "shiversoftdev",
             "https://github.com/shiversoftdev/t7patch"),
        ):
            row = Adw.ActionRow(title=title, subtitle=name)
            open_btn = Gtk.Button(icon_name="adw-external-link-symbolic",
                                  valign=Gtk.Align.CENTER, css_classes=["flat"])
            open_btn.set_tooltip_text(url)
            open_btn.connect("clicked", lambda _b, u=url: self._open_link(u))
            row.add_suffix(open_btn)
            row.set_activatable_widget(open_btn)
            credits_group.add(row)

        license_lbl = Gtk.Label(label="Released under the MIT License.")
        license_lbl.add_css_class("dim-label")
        license_lbl.set_margin_top(16)
        body.append(license_lbl)

        dlg.present(self._window)

    def _open_link(self, url: str):
        try:
            opener.open_url(url)
        except Exception as exc:  # noqa: BLE001
            show_error_dialog(self._window, "Could not open link", exc)


def main() -> int:
    app = T7PatchApp()
    return app.run(None)
