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
- **GTK 4 + libadwaita** (already present on GNOME, KDE Plasma 6, and most Arch-based distros)
- Python 3.11+ and PyGObject

On CachyOS / Arch:
```fish
sudo pacman -S --needed python python-gobject gtk4 libadwaita
```

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

It installs system dependencies (Python 3.11+, PyGObject, GTK 4, libadwaita,
pipx), sets up `~/.local/bin` in your PATH (fish/bash/zsh detected), installs
the app via `pipx --system-site-packages`, registers the desktop entry, and
offers to launch it. Run `./install.sh --uninstall` to reverse everything.

On unsupported package managers the script lists the packages you need and
continues with `--skip-deps`.

### AUR (once published)
```fish
paru -S t7patch-manager
# or
yay -S t7patch-manager
```

### Manual (from source)
```fish
git clone https://github.com/HeyIamUsingArchBtw/t7patch-manager
cd t7patch-manager
pipx install --system-site-packages .
```
The `--system-site-packages` flag lets pipx see your distro's PyGObject.

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
- **GTK 4 + libadwaita**
- Python 3.11+ mit PyGObject

Auf CachyOS / Arch:
```fish
sudo pacman -S --needed python python-gobject gtk4 libadwaita
```

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

Es installiert System-Pakete (Python 3.11+, PyGObject, GTK 4, libadwaita, pipx),
trägt `~/.local/bin` in den PATH ein (fish/bash/zsh erkannt), installiert die
App via `pipx --system-site-packages`, registriert den Desktop-Eintrag und
startet sie optional direkt. Zum sauberen Entfernen: `./install.sh --uninstall`.

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
