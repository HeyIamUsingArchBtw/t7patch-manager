"""GTK4 UI for t7patch-manager."""
from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import __version__, config, installer, launcher, paths, state


APP_ID = "io.github.heyiamusingarchbtw.T7PatchManager"


# ── helpers ─────────────────────────────────────────────────────────
def run_in_thread(fn: Callable[..., None], *args, on_done: Callable[..., None] | None = None):
    """Run *fn* on a background thread; schedule *on_done(result, error)* on the main loop."""
    def target():
        error, result = None, None
        try:
            result = fn(*args)
        except Exception as exc:  # noqa: BLE001
            error = exc
            traceback.print_exc()
        if on_done:
            GLib.idle_add(on_done, result, error)
    threading.Thread(target=target, daemon=True).start()


# ── config editor dialog ────────────────────────────────────────────
class ConfigDialog(Adw.Dialog):
    """Dialog with explicit Cancel / Save buttons for t7patch.conf."""

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
            description="These are shown to other players.",
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

        # Enter in any text field saves
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
        except Exception:  # noqa: BLE001
            pass
        self.close()


# ── main window ─────────────────────────────────────────────────────
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self.set_title("T7Patch Manager")
        self.set_default_size(560, 560)

        self._bo3_dir: Path | None = paths.find_bo3_dir()
        self._status: state.PatchStatus | None = None
        self._latest_tag: str | None = None
        self._downloading = False

        # Layout skeleton
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        # Menu
        menu = Gio.Menu()
        menu.append("Edit t7patch.conf…", "app.edit-config")
        menu.append("Check for updates", "app.check-updates")
        menu.append("Uninstall T7Patch…", "app.uninstall")
        menu.append("About", "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)

        self._toaster = Adw.ToastOverlay()
        toolbar.set_content(self._toaster)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                           margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self._toaster.set_child(content)

        # Update banner
        self._banner = Adw.Banner()
        self._banner.set_revealed(False)
        content.append(self._banner)

        # Status card
        status_group = Adw.PreferencesGroup()
        content.append(status_group)

        self._bo3_row = Adw.ActionRow(title="Black Ops III")
        self._bo3_row.set_subtitle("Detecting…")
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
                                        css_classes=["suggested-action", "pill"])
        self._install_btn.connect("clicked", self._on_install)
        self._install_row = Adw.ActionRow(title="T7Patch",
                                           subtitle="Loading release info…")
        self._install_row.add_suffix(self._install_btn)
        actions_group.add(self._install_row)

        self._play_btn = Gtk.Button(label="Play", css_classes=["pill"])
        self._play_btn.connect("clicked", self._on_play)
        play_row = Adw.ActionRow(title="Launch BO3",
                                  subtitle="Opens Steam and starts the game")
        play_row.add_suffix(self._play_btn)
        actions_group.add(play_row)

        self._config_btn = Gtk.Button(label="Edit…", css_classes=["pill"])
        self._config_btn.connect("clicked", lambda *_: self._open_config_dialog())
        cfg_row = Adw.ActionRow(title="In-game name & network password",
                                 subtitle="Edit t7patch.conf")
        cfg_row.add_suffix(self._config_btn)
        actions_group.add(cfg_row)

        # Footer with launch-options hint
        hint = Gtk.Label(
            label=(
                "<small>Steam launch options must be set to:\n"
                "<tt>WINEDLLOVERRIDES=\"dsound=n,b\" %command%</tt>\n"
                "(right-click BO3 in Steam → Properties → Launch options)</small>"
            ),
            use_markup=True,
            wrap=True,
            justify=Gtk.Justification.CENTER,
            css_classes=["dim-label"],
        )
        content.append(hint)

        # Initial refresh
        self._refresh_status()
        self._check_latest_async()

    # ── status handling ──
    def _refresh_status(self):
        """Repaint every status-dependent widget based on current disk state."""
        # No BO3 install at all
        if not self._bo3_dir:
            self._bo3_row.set_subtitle("Not found — install BO3 in Steam first.")
            self._patch_row.set_subtitle("BO3 not detected")
            self._install_row.set_subtitle("BO3 must be installed first")
            self._install_btn.set_sensitive(False)
            self._play_btn.set_sensitive(False)
            self._config_btn.set_sensitive(False)
            self._patch_switch.set_sensitive(False)
            return

        self._bo3_row.set_subtitle(str(self._bo3_dir))
        try:
            self._status = state.detect(self._bo3_dir)
        except Exception as exc:  # noqa: BLE001
            self._patch_row.set_subtitle(f"Error: {exc}")
            traceback.print_exc()
            return

        st = self._status
        # Show a friendly installed-version string (falls back to "unknown" if the
        # marker file was not written — e.g. the patch was placed manually).
        ver_txt = st.installed_version or "installed"

        # Guard the switch handler so programmatic changes don't fire the toggle
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

        # Install-action row + button label reflect current state
        self._update_install_row()

    def _update_install_row(self):
        """Update the install-action row's subtitle + button label based on state + latest tag."""
        st = self._status
        latest = self._latest_tag  # may be None if the API call hasn't returned yet

        if not st:
            return

        if st.state is state.PatchState.NOT_INSTALLED:
            self._install_row.set_subtitle(
                f"Not installed. Latest release: {latest}." if latest
                else "Not installed."
            )
            self._install_btn.set_label(f"Install {latest}" if latest else "Install T7Patch")
            self._install_btn.set_sensitive(True)
            self._install_btn.set_css_classes(["suggested-action", "pill"])
        else:
            # Installed — either same version or possibly outdated
            installed = st.installed_version
            if latest and installed and installed != latest:
                self._install_row.set_subtitle(
                    f"Installed: {installed}  ·  Update available: {latest}"
                )
                self._install_btn.set_label(f"Update to {latest}")
                self._install_btn.set_sensitive(True)
                self._install_btn.set_css_classes(["suggested-action", "pill"])
            elif latest and installed and installed == latest:
                self._install_row.set_subtitle(f"Up to date  ·  {installed}")
                self._install_btn.set_label("Reinstall")
                self._install_btn.set_sensitive(True)
                self._install_btn.set_css_classes(["pill"])
            else:
                # Installed but we couldn't determine the version (no marker file)
                if latest:
                    self._install_row.set_subtitle(
                        f"Installed (version unknown). Latest release: {latest}."
                    )
                    self._install_btn.set_label(f"Reinstall {latest}")
                else:
                    self._install_row.set_subtitle("Installed.")
                    self._install_btn.set_label("Reinstall")
                self._install_btn.set_sensitive(True)
                self._install_btn.set_css_classes(["pill"])

    # ── update check ──
    def _check_latest_async(self):
        def _done(result, error):
            if error or not result:
                if self._status and self._status.state is state.PatchState.NOT_INSTALLED:
                    self._install_row.set_subtitle("Not installed. (Update check failed)")
                elif self._status:
                    self._install_row.set_subtitle("Installed. (Update check failed)")
                return
            self._latest_tag = result.tag

            # If the patch is installed but has no version marker, adopt the
            # latest tag as the assumed version (best-effort — the user can
            # always click Reinstall to make it authoritative).
            if self._status and self._status.state is not state.PatchState.NOT_INSTALLED \
               and not self._status.installed_version and self._bo3_dir:
                try:
                    state.write_version_marker(self._bo3_dir, result.tag)
                    self._status = state.detect(self._bo3_dir)
                except Exception:  # noqa: BLE001
                    pass

            self._update_install_row()

            # Update banner if we have a mismatch
            installed = self._status.installed_version if self._status else None
            if installed and installed != result.tag:
                self._banner.set_title(
                    f"Update available: {result.tag} (installed: {installed})"
                )
                self._banner.set_button_label("Update now")
                self._banner.connect("button-clicked", lambda *_: self._on_install(None))
                self._banner.set_revealed(True)
            else:
                self._banner.set_revealed(False)

        run_in_thread(installer.fetch_latest_release, on_done=_done)

    # ── button handlers ──
    def _on_toggle(self, sw: Gtk.Switch, val: bool) -> bool:
        if not self._bo3_dir or self._downloading:
            return False
        try:
            state.set_enabled(self._bo3_dir, val)
            self._toast("T7Patch enabled" if val else "T7Patch disabled")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Toggle failed: {exc}")
        # Let GTK apply the new state, then refresh
        GLib.idle_add(self._refresh_status)
        return False

    def _on_play(self, _btn):
        try:
            launcher.launch_bo3()
            self._toast("Launching BO3 via Steam…")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Launch failed: {exc}")

    def _on_install(self, _btn):
        if not self._bo3_dir or self._downloading:
            return
        self._downloading = True
        self._install_btn.set_sensitive(False)

        progress = Adw.AlertDialog(
            heading="Downloading T7Patch",
            body="Fetching latest release…",
            close_response="cancel",
        )
        progress.present(self)

        def do_install():
            info = installer.fetch_latest_release()
            def _p(got, total):
                pct = (got / total * 100) if total else 0
                GLib.idle_add(progress.set_body, f"Downloading {info.tag} — {pct:0.0f}%")
            zip_bytes = installer.download_zip(info.linux_asset_url, on_progress=_p)
            GLib.idle_add(progress.set_body, "Extracting…")
            installer.extract_patch_into(self._bo3_dir, zip_bytes)
            state.write_version_marker(self._bo3_dir, info.tag)
            return info.tag

        def _done(tag, error):
            self._downloading = False
            self._install_btn.set_sensitive(True)
            progress.close()
            if error:
                self._toast(f"Install failed: {error}")
            else:
                self._toast(f"Installed T7Patch {tag}")
                self._banner.set_revealed(False)
                self._latest_tag = tag  # ensure UI reflects the new version immediately
            self._refresh_status()

        run_in_thread(do_install, on_done=_done)

    def _open_config_dialog(self):
        if not self._bo3_dir:
            return
        ConfigDialog(
            self,
            self._bo3_dir / "t7patch.conf",
            on_saved=lambda: self._toast("Config saved"),
        )

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
        if not self._window:
            self._window = MainWindow(self)
            self._install_actions()
        self._window.present()

    def _install_actions(self):
        for name, cb in (
            ("edit-config",   lambda *_: self._window._open_config_dialog()),
            ("check-updates", lambda *_: self._window._check_latest_async()),
            ("uninstall",     lambda *_: self._confirm_uninstall()),
            ("about",         lambda *_: self._show_about()),
        ):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)

    def _confirm_uninstall(self):
        if not self._window._bo3_dir:
            return
        dlg = Adw.AlertDialog(
            heading="Uninstall T7Patch?",
            body="This removes the patch DLLs from your BO3 folder. "
                 "Your t7patch.conf will be kept.",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("confirm", "Uninstall")
        dlg.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def _on_response(_dlg, resp):
            if resp != "confirm":
                return
            try:
                removed = installer.uninstall(self._window._bo3_dir)
                self._window._toast(f"Removed {len(removed)} file(s)")
            except Exception as exc:  # noqa: BLE001
                self._window._toast(f"Uninstall failed: {exc}")
            self._window._refresh_status()

        dlg.connect("response", _on_response)
        dlg.present(self._window)

    def _show_about(self):
        about = Adw.AboutDialog(
            application_name="T7Patch Manager",
            application_icon=APP_ID,
            developer_name="HeyIamUsingArchBtw",
            version=__version__,
            website="https://github.com/HeyIamUsingArchBtw/t7patch-manager",
            issue_url="https://github.com/HeyIamUsingArchBtw/t7patch-manager/issues",
            license_type=Gtk.License.MIT_X11,
            comments="Install, launch, toggle and configure T7Patch v3 for Call of Duty: Black Ops III on Linux.",
        )
        about.add_credit_section("T7Patch v3 by", ["Scroptss https://github.com/Scroptss/T7Patch"])
        about.add_credit_section("Original T7Patch by", ["shiversoftdev https://github.com/shiversoftdev/t7patch"])
        about.present(self._window)


def main() -> int:
    app = T7PatchApp()
    return app.run(None)
