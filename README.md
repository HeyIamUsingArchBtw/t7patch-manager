# T7Patch Manager

A tiny GTK4 desktop app that installs, launches, toggles and configures
[**T7Patch v3**](https://github.com/Scroptss/T7Patch) — the community patch that
makes multiplayer for **Call of Duty: Black Ops III** work again on Linux.

- One-click install of the latest T7Patch release
- Launch the game from the app
- Enable / disable the patch without uninstalling
- Edit `t7patch.conf` (player name, network password, friends-only) in a real UI
- Detects your BO3 install automatically (via Steam's `libraryfolders.vdf`)
- Auto-detects updates and offers to install them

<sub>Deutsch weiter unten · [🇩🇪 Deutsche Version](#deutsch)</sub>

---

## Requirements

- Linux with a working Steam install
- Black Ops III owned in Steam
- **Proton** (Proton-GE or Proton Experimental — either works with T7Patch v3)
- **GTK 4 + libadwaita** (shipped with GNOME, KDE Plasma 6, and most modern desktops)
- Python 3.11+ and PyGObject

**You don't need to install any of these by hand — `./install.sh` does it for you.**
It auto-detects your distro's package manager and installs whatever is
missing. See below.

## Install

### One-shot installer (recommended, any Linux distro)
```bash
git clone https://github.com/HeyIamUsingArchBtw/t7patch-manager
cd t7patch-manager
./install.sh
```
The installer auto-detects your package manager and works on all major distros:

| Distro family                                  | Package manager |
|------------------------------------------------|-----------------|
| Arch, CachyOS, Manjaro, EndeavourOS, Garuda    | `pacman`        |
| Debian, Ubuntu, Pop!_OS, Mint, Zorin           | `apt`           |
| Fedora, RHEL, Rocky, Alma, Nobara              | `dnf`           |
| openSUSE Tumbleweed / Leap                     | `zypper`        |
| Void Linux                                     | `xbps`          |
| Alpine                                         | `apk`           |
| Solus                                          | `eopkg`         |

The script:

1. detects your package manager and installs anything missing (Python 3.11+,
   PyGObject, GTK 4, libadwaita, pipx),
2. verifies that `import gi; Gtk; Adw` actually works from Python — if not, it
   auto-retries a second install pass,
3. puts `~/.local/bin` on your PATH (fish/bash/zsh detected),
4. installs the app via `pipx`, then enables `include-system-site-packages` on
   the pipx venv so it can see your distro's PyGObject,
5. registers a `.desktop` entry + icon, and
6. offers to launch the app.

Additional flags:

- `./install.sh --yes` — non-interactive; useful for scripts.
- `./install.sh --diagnose` — print environment status without touching anything.
- `./install.sh --use-pip` — skip pipx; use a plain `venv` at
  `~/.local/share/t7patch-manager/venv` (last-resort fallback).
- `./install.sh --skip-deps` — don't touch system packages.
- `./install.sh --uninstall` — reverse everything the installer put in place.

On unsupported package managers the script lists the packages you need and
continues with `--skip-deps`.

### AUR (once published)
```fish
paru -S t7patch-manager
# or
yay -S t7patch-manager
```

### Manual (from source)
If you'd rather do it by hand, install the system packages for your distro
first:

```bash
# Arch / CachyOS / Manjaro
sudo pacman -S --needed python python-gobject gtk4 libadwaita python-pipx
# Debian / Ubuntu / Mint
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 pipx
# Fedora
sudo dnf install python3 python3-gobject gtk4 libadwaita pipx
```

Then:

```bash
git clone https://github.com/HeyIamUsingArchBtw/t7patch-manager
cd t7patch-manager
pipx install .
# Let pipx see the system PyGObject:
echo 'include-system-site-packages = true' \
    >> ~/.local/share/pipx/venvs/t7patch-manager/pyvenv.cfg
```

## Usage

1. Open **T7Patch Manager** from your app menu.
2. Click **Install T7Patch v3.xx** — the app downloads the latest release and
   drops the patch files into your BO3 folder.
3. Set Steam launch options for BO3 to:
   ```
   WINEDLLOVERRIDES="dsound=n,b" %command%
   ```
   (right-click BO3 in Steam → *Properties* → *Launch options*)
4. Optional: click **Edit…** to set your in-game name and network password.
5. Hit **Play**. Steam launches BO3 through Proton with the patch active.

The toggle at the top disables the patch (renames the DLLs to `*.disabled`)
whenever you want vanilla BO3 for a session, without deleting anything.

## Troubleshooting

If the installer or the app misbehaves, start here.

### Run diagnostics

```bash
./install.sh --diagnose
```

This checks Python, GTK 4 / libadwaita bindings, `pipx`, your Steam paths
and BO3 install, without changing anything on your system.

### Common issues

- **`t7patch-manager` command not found after install.** Restart your shell
  (or open a new terminal). The installer adds `~/.local/bin` to your PATH,
  but the change only applies to new shells.
- **App won't start / GTK4 or libadwaita import error.** Make sure your
  distro's `python3-gi`, `gtk4`, and `libadwaita` packages are installed.
  Debian/Ubuntu users also need `gir1.2-adw-1`. Then re-run `./install.sh`.
- **`pipx` isn't available on your distro.** Re-run with `./install.sh --use-pip`
  to install into a standalone venv at `~/.local/share/t7patch-manager/venv`
  instead.
- **The app can't find your BO3 install.** Open **Preferences…** from the menu
  and set the BO3 path manually (the folder that contains `BlackOps3.exe`).
- **T7Patch download fails / GitHub is blocked.** Open **Preferences…** and
  either point the app at a mirror URL, or download
  `Linux.Steamdeck.and.Manual.Windows.Install.zip` yourself from
  [Scroptss/T7Patch releases](https://github.com/Scroptss/T7Patch/releases)
  and set that local zip as the source override.
- **Something else went wrong.** In the app, open the menu → **Debug log…**,
  copy the log, and open an issue on
  [GitHub](https://github.com/HeyIamUsingArchBtw/t7patch-manager/issues).

## FAQ

**Do I still need `dsound.dll.disabled` chattr tricks / hosts blocks / depot
reverts?**
No. T7Patch v3 fixed the February 2026 injection issue natively. The old
workarounds are obsolete.

**Does this touch anything outside my BO3 folder?**
No. It only writes to
`~/.local/share/Steam/steamapps/common/Call of Duty Black Ops III/`.

**Where's the config?**
Same folder — `t7patch.conf`. The GUI reads and writes that file.

## Credits

- **T7Patch v3** by [Scroptss](https://github.com/Scroptss)
- **Original T7Patch** by [shiversoftdev](https://github.com/shiversoftdev/t7patch)

## License

MIT — see [LICENSE](LICENSE).

---

<a name="deutsch"></a>
## Deutsch

Ein winziges GTK4-Programm, das
[**T7Patch v3**](https://github.com/Scroptss/T7Patch) installiert, startet,
ein-/ausschaltet und konfiguriert — den Community-Patch, der den Multiplayer
von **Call of Duty: Black Ops III** unter Linux wieder zum Laufen bringt.

### Was es kann

- T7Patch mit einem Klick installieren (neuestes Release, automatisch)
- BO3 direkt aus der App starten
- Patch ein- und ausschalten, ohne ihn zu deinstallieren
- `t7patch.conf` in einer richtigen UI editieren (Spielername, Netzwerk-Passwort,
  „nur Freunde")
- Findet deinen BO3-Ordner selbst (über Steams `libraryfolders.vdf`)
- Prüft automatisch auf Updates

### Voraussetzungen

- Linux mit funktionierender Steam-Installation
- BO3 in Steam gekauft
- **Proton** (Proton-GE oder Proton Experimental — beides läuft mit T7Patch v3)
- **GTK 4 + libadwaita** (bei GNOME, KDE Plasma 6 und den meisten modernen Desktops schon dabei)
- Python 3.11+ mit PyGObject

**Du musst nichts davon selbst installieren — `./install.sh` erledigt das für
dich.** Der Installer erkennt deinen Paketmanager und installiert automatisch
nach, was fehlt.

### Installation

#### Ein-Kommando-Installer (empfohlen, jede Linux-Distro)
```bash
git clone https://github.com/HeyIamUsingArchBtw/t7patch-manager
cd t7patch-manager
./install.sh
```
Das Script erkennt deinen Paketmanager automatisch und funktioniert auf allen
gängigen Distributionen: `pacman` (Arch/CachyOS/Manjaro), `apt` (Debian/Ubuntu
und Derivate), `dnf` (Fedora/RHEL/Nobara), `zypper` (openSUSE), `xbps` (Void),
`apk` (Alpine), `eopkg` (Solus).

Das Script:

1. erkennt deinen Paketmanager und installiert fehlende System-Pakete
   (Python 3.11+, PyGObject, GTK 4, libadwaita, pipx),
2. prüft danach mit `import gi; Gtk; Adw`, ob die Bindings wirklich importierbar
   sind — falls nicht, wird ein zweiter Install-Durchlauf gestartet,
3. trägt `~/.local/bin` in deinen PATH ein (fish/bash/zsh erkannt),
4. installiert die App via `pipx` und aktiviert `include-system-site-packages`
   im pipx-venv, damit dein System-PyGObject sichtbar bleibt,
5. registriert Desktop-Eintrag + Icon und
6. bietet an, die App direkt zu starten.

Weitere Flags:

- `./install.sh --yes` — nicht-interaktiv (alle Prompts automatisch „ja").
- `./install.sh --diagnose` — Umgebung prüfen ohne etwas zu ändern.
- `./install.sh --use-pip` — pipx überspringen; fester venv als Fallback.
- `./install.sh --skip-deps` — System-Pakete unangetastet lassen.
- `./install.sh --uninstall` — alles rückgängig machen, was der Installer
  eingerichtet hat.

#### Über das AUR (sobald verfügbar)
```fish
paru -S t7patch-manager
```

#### Manuell aus dem Quellcode
```fish
git clone https://github.com/HeyIamUsingArchBtw/t7patch-manager
cd t7patch-manager
pipx install --system-site-packages .
```

### Benutzung

1. **T7Patch Manager** aus dem App-Menü öffnen.
2. Auf **Install T7Patch v3.xx** klicken — die App lädt das neueste Release
   herunter und legt die Patch-Dateien in deinen BO3-Ordner.
3. Steam-Startoptionen für BO3 setzen auf:
   ```
   WINEDLLOVERRIDES="dsound=n,b" %command%
   ```
   (Rechtsklick auf BO3 in Steam → *Eigenschaften* → *Startoptionen*)
4. Optional: **Edit…** → Spielername und Passwort setzen.
5. Auf **Play** klicken. Steam startet BO3 mit aktivem Patch.

Der Schalter oben deaktiviert den Patch (benennt die DLLs zu `*.disabled` um)
wenn du mal Vanilla-BO3 haben willst — ohne etwas zu löschen.

### Fehlersuche

Wenn beim Installieren oder Starten etwas schief geht, hier ansetzen.

**System-Check ausführen**

```bash
./install.sh --diagnose
```

Prüft Python, GTK 4 / libadwaita, `pipx`, deine Steam-Pfade und die
BO3-Installation — ohne irgendetwas am System zu ändern.

**Häufige Probleme**

- **`t7patch-manager` ist nach der Installation nicht auffindbar.** Neue
  Shell öffnen (oder Terminal neu starten). Der Installer trägt
  `~/.local/bin` in den PATH ein — das gilt nur für neu geöffnete Shells.
- **App startet nicht / GTK4 oder libadwaita Import-Fehler.** Stell sicher,
  dass die Pakete `python3-gi`, `gtk4` und `libadwaita` deiner Distro
  installiert sind. Auf Debian/Ubuntu zusätzlich `gir1.2-adw-1`. Danach
  `./install.sh` erneut ausführen.
- **`pipx` gibt's auf deiner Distro nicht.** `./install.sh --use-pip`
  ausführen — installiert dann in ein eigenständiges venv unter
  `~/.local/share/t7patch-manager/venv`.
- **App findet BO3 nicht.** Im Menü **Preferences…** öffnen und den
  BO3-Pfad manuell setzen (der Ordner, in dem `BlackOps3.exe` liegt).
- **T7Patch-Download schlägt fehl / GitHub blockiert.** In **Preferences…**
  eine Mirror-URL setzen oder
  `Linux.Steamdeck.and.Manual.Windows.Install.zip` selbst von den
  [Scroptss/T7Patch Releases](https://github.com/Scroptss/T7Patch/releases)
  herunterladen und die lokale Zip-Datei als Quelle wählen.
- **Irgendwas anderes ist kaputt.** In der App Menü → **Debug log…** öffnen,
  Log kopieren und ein Issue bei
  [GitHub](https://github.com/HeyIamUsingArchBtw/t7patch-manager/issues) aufmachen.
