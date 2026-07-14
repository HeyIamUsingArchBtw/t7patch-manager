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

### AUR (recommended on Arch/CachyOS/Manjaro)
```fish
paru -S t7patch-manager
# or
yay -S t7patch-manager
```

### From source
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

#### Über das AUR (empfohlen)
```fish
paru -S t7patch-manager
```

#### Aus dem Quellcode
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
