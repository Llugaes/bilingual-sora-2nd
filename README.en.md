# Bilingual Sora 2nd — Trails in the Sky the 2nd Bilingual Subtitles Mod

[简体中文](README.md) · **English** · [日本語](README.ja.md)

**空之轨迹 the 2nd 双语字幕 Mod · 空の軌跡 the 2nd 二言語字幕 Mod**

Compare English/Japanese, Chinese/Japanese, or other language pairs in dialogue subtitles and menus. Hold or toggle a shortcut to switch languages, or use bilingual ruby-style annotations for language learning.

A native bilingual text mod for the PC version of **Trails in the Sky the 2nd**. Choose your primary and secondary languages independently from English, Japanese, Simplified Chinese, Traditional Chinese, Korean, French, German, and Spanish. For an English-language game, first-time setup keeps English as the main text and adds Japanese annotations for comparison and language learning.

Currently supports Steam build **25386012**, executable **1.03.2**. The tool checks the game build before installing hooks; it does not force hooks into unsupported versions or rewrite the original PAC/EXE files. This is an early project with offline regression tests and partial in-game validation. Full-game coverage, layout across all languages, and controller compatibility still need in-game feedback.

## Installation

**Recommended installer:** Download `bilingual-sora-2nd-VERSION-windows-x64-setup.exe` from [Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest). The English/Japanese/Chinese wizard installs for the current user without administrator rights, adds a Start menu entry and an optional desktop shortcut, and bundles all dependencies for offline installation. Uninstall through Windows Installed apps; settings are retained. Exit the tool from its tray menu and end its game connection before reinstalling or uninstalling. Setup never force-closes the game.

**Portable alternative:** Follow the ZIP steps below if you prefer managing the folder yourself.

From **0.3.4**, automatic updates download the small application component when dependencies are unchanged, and fetch the runtime only when needed. Versions 0.3.0–0.3.3 download one complete upgrade first. Intermediate versions can be skipped. The `app` and `runtime` ZIPs are updater components; choose the installer or complete ZIP for manual installation.

**0.2.2 reports “更新包文件过多” (too many files)?** Its old updater cannot install the bundled-runtime release. Use the installer and migrate your settings using the 0.2.x instructions below. The new updater provides a download action on failure, keeping technical diagnostics in logs.

1. Download **bilingual-sora-2nd-VERSION-windows-x64.zip** from [Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) and extract the entire ZIP into a writable folder.
2. Double-click **BilingualSora2nd.exe**. Python and all runtime dependencies are included: no Python installation, CMD scripts, or first-run dependency downloads. Supports Windows 10/11 x64.
3. Select the game's current text language on first launch. Settings open immediately; the tool automatically connects to the game or waits for it to start. It never launches the game itself.

The Updates page includes desktop shortcut creation, the logs/settings folder, and a user guide. Launching the EXE again opens the existing interface without starting a second backend. The interface supports English, Japanese, and Simplified Chinese.

Download the ZIP only. **bilingual-sora-2nd-update.json** is updater metadata; GitHub's Source code archives are for developers. Keep the extracted folder intact; do not move only the EXE.

Upgrading from **0.2.x** requires a one-time manual migration because the old updater cannot install a bundled runtime. Exit the old tool, extract the new release into a new folder, copy **generated/native-control.json** and **generated/overlay-window.ini** (not **.venv/**, **generated/updates/**, or the old hot-reload manifest), then run the new EXE. Future portable releases automatically update both code and dependencies. Keep source checkouts separate.

Choose any primary/secondary pair under Languages and mode. If you change the language in the game itself, also change Advanced: source matching. Source language identifies incoming text; primary language controls the mod's displayed text.

### First-run defaults

| Game text language | Primary | Secondary |
|---|---|---|
| English | English | Japanese |
| Japanese | Japanese | English |
| Simplified / Traditional Chinese | Same as the game | Japanese |
| Korean / French / German / Spanish | Same as the game | Japanese |

These are initial preferences, not restrictions on language pairs. Existing settings survive restarts and updates unchanged. The interface supports English, Simplified Chinese, and Japanese, defaults to the system language, and switches live via **Interface language**. UI language, source matching, and display languages are independent.

The first load parses your local game resources and builds a cache, which can take time. Text is then rendered by native game controls; the Qt interface provides configuration and status. Use windowed or borderless mode; the settings overlay is not guaranteed to appear over exclusive fullscreen.

### Fonts for additional languages

Some language pairs need an expanded game font to avoid missing characters appearing as question marks. Generate fonts from your own game installation; game fonts are not distributed here. Exit the game before running:

```powershell
$runtime = Get-Content runtime/current.txt
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.universal_fonts --game "PATH_TO_GAME"
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.install_font_patch --game "PATH_TO_GAME" --loader "PATH_TO_xinput1_4.dll" --install
```

The optional loader comes from [sora2looseload](https://github.com/lmaple0/sora2looseload). The installer accepts only the verified DLL with SHA-256 **e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7**. Do not bypass a mismatch; keep the existing files and report it. Other mods' files are not overwritten. Use **--update** only for an installation already recorded by this tool. Automatic software updates do not modify the game directory, loader, or generated fonts.

## Controls and configuration

Click **设置** (Settings) on the status bar to open the full panel. **× / Esc inside the panel** collapses it. **× on the status bar** hides the interface while the background service keeps running. Reopen it from the system tray or desktop shortcut.

| Action | Default shortcut |
|---|---|
| Show / hide the interface | Ctrl + Shift + F9 |
| Language switch for the selected mode | Ctrl + Shift + F10 |

Record one keyboard or SDL controller combination under **Bindings**. The same binding follows the selected mode. Existing custom bindings migrate; F11/F12 are no longer separate simultaneously active actions. By default, bindings respond while the game is in the foreground.

- **Hold**: primary text normally, secondary-only text while held; release or focus loss restores primary text.
- **Toggle**: one press switches to secondary-only text, the next switches back. Holding does not repeatedly toggle.
- **Trails annotations**: uses this game's native ruby layout for simultaneous bilingual text; the shortcut turns annotations on/off. This mode depends on the game's special rendering support.

Text scale, offsets, and spacing remain adjustable live. Initial resource parsing still takes time; valid caches load directly. UI translations and initial language preferences no longer invalidate the game-resource index. Connection logs report model preparation and total connection time separately.

Menus, items, skills, NPC conversations, and story dialogue use small annotations. Only native cutscene subtitles use a complete primary block above a complete secondary block. Original ruby and emphasis marks retain their positions; the secondary language uses a separate annotation layer. Text baked into images or videos is outside the supported scope. Uncertain matches keep the original text rather than guessing a translation.

## Automatic updates

The **版本更新** (Updates) tab defaults to **automatically checking and installing stable releases** from this repository on startup and every six hours. You can also check immediately, choose notification-only updates, or disable checks.

Downloads are verified against the repository, version, file list, and SHA-256 hashes. Installation waits until the game connection ends. The interface then reloads automatically, restoring its position and expanded/hidden state. Settings and caches stay in **generated/**; bundled dependencies stay in **runtime/**. If installation is interrupted, the next shortcut launch completes it or restores the old files. Backups live under **generated/updates/backup-***.

Automatic installation requires a release installation containing **installed-manifest.json**. Git development directories and manually modified software files are not overwritten. Runtime updates install into a new versioned directory and switch on UI reload. Loaded DLLs are not overwritten; old runtimes remain available for recovery and consume additional disk space. Drafts, prereleases, and older versions are not installed automatically.

## Development and contributing

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m tools.dev check
```

**tests/check_overlay_update.py** exercises real Qt reloads using isolated settings and does not connect to the game. **tests/check_native_transport.py** requires local resources and attaches only to its own test process. These integration checks are separate from CI's game-free unit tests.

Publish local changes with **python -m tools.dev publish-local**. It validates syntax and atomically publishes the hot-reload manifest. The UI and text logic can reload; resident hook changes wait for the next game launch. Do not forcibly kill or unload an injected script while the game is running.

See the [architecture](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/ARCHITECTURE.md) and [contribution guide](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/CONTRIBUTING.md), currently in Chinese. Issues and pull requests are welcome. Include the tool version, game version, language pair, reproduction steps, and a short relevant error excerpt. Do not upload complete game resources.

For a release, maintainers update both **distribution.json** and **pyproject.toml**, then push a matching **vX.Y.Z** tag. GitHub Actions validates on Windows, builds from an explicit file allowlist, uploads all assets to a draft, then publishes them together. Manual build:

```powershell
.venv\Scripts\python.exe -m tools.build_portable --version 0.3.4 --repository Llugaes/bilingual-sora-2nd
```

Neither the repository nor releases contain game resources, generated fonts, complete text indexes, logs, screenshots, or user settings.

## License

Project code is available under [MIT](LICENSE). See [THIRD_PARTY.md](THIRD_PARTY.md) for third-party notices and references. This is an unofficial tool; the game, trademarks, and game assets belong to their respective owners.

## Acknowledgments

Thanks to the projects and maintainers whose work makes this tool possible:

- [0xDC00/scripts](https://github.com/0xDC00/scripts) and Tom (tomrock645): game text-hook call-site signatures and adapted code.
- [FPACker](https://github.com/coinkillerl/FPACker) and [Ingert](https://github.com/Aureole-Suite/Ingert): resource-container and script-format references.
- [sora2looseload](https://github.com/lmaple0/sora2looseload): the optional game-font loader; its DLL is not bundled.
- [Frida](https://github.com/frida/frida): native runtime text handling; [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/): settings and status UI.
- [pygame-ce / SDL](https://github.com/pygame-community/pygame-ce): controller input; [pefile](https://github.com/erocarrera/pefile): PE inspection; [python-lz4 / LZ4](https://github.com/python-lz4/python-lz4): font-texture compression.
- [Inno Setup](https://jrsoftware.org/) and its [Chinese translation](https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation): Windows installer.

Dependencies retain their own licenses. Notices for adapted code are preserved in [THIRD_PARTY.md](THIRD_PARTY.md).
