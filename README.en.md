# Bilingual Sora 2nd — Trails in the Sky the 2nd Bilingual Subtitles Mod

[简体中文](README.md) · **English** · [日本語](README.ja.md)

**空之轨迹 the 2nd 双语字幕 Mod · 空の軌跡 the 2nd 二言語字幕 Mod**

A bilingual text mod for **Trails in the Sky the 2nd** on PC. Compare dialogue and menus on screen, or hold a shortcut to switch temporarily. Choose both languages independently: English, Japanese, Simplified or Traditional Chinese, Korean, French, German, and Spanish.

Currently supports Steam build **25386012**, executable **1.03.2**. The tool checks the game build before installing hooks; it does not force hooks into unsupported versions or rewrite the original PAC/EXE files. This is an early project with offline regression tests and partial in-game validation. Full-game coverage, layout across all languages, and controller compatibility still need in-game feedback.

**Recommended for everyday play: single-language display with hold-to-show secondary.** Read the primary language normally, hold your shortcut to compare, then release to return. Simultaneous bilingual text remains available, but opening the dialogue log can hitch and its frame rate can be lower; see the limitations below. This recommendation does not reset existing settings.

## Screenshots

In-game dialogue with English primary text and Japanese secondary text. Open an image to view it at full size.

![English and Japanese dialogue](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-en-ja.jpg)

![English and Japanese Arts menu](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/arts-en-ja.jpg)

<details>
<summary>Items, equipment, and field interface</summary>

The following captures use Chinese primary text and Japanese secondary text.

Item names and descriptions:

![Items](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/items.jpg)

Equipment names and descriptions:

![Equipment](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/equipment.jpg)

Field interactions and notifications:

![Field interface](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/field.jpg)

</details>

## Installation

**Recommended installer:** Download `bilingual-sora-2nd-VERSION-windows-x64-setup.exe` from [Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest). The English/Japanese/Chinese wizard installs for the current user without administrator rights, adds a Start menu entry and an optional desktop shortcut, and bundles all dependencies for offline installation. Uninstall through Windows Installed apps; settings are retained. Exit the tool from its tray menu and end its game connection before reinstalling or uninstalling. Setup never force-closes the game.

**Portable alternative:** Follow the ZIP steps below if you prefer managing the folder yourself.

From **0.3.4**, automatic updates download the small application component when dependencies are unchanged, and fetch the runtime only when needed. Versions 0.3.0–0.3.3 download one complete upgrade first. Intermediate versions can be skipped. The `app` and `runtime` ZIPs are updater components; choose the installer or complete ZIP for manual installation.

**0.2.2 reports “更新包文件过多” (too many files)?** Its old updater cannot install the bundled-runtime release. Use the installer and migrate your settings using the 0.2.x instructions below. The new updater provides a download action on failure, keeping technical diagnostics in logs.

1. Download **bilingual-sora-2nd-VERSION-windows-x64.zip** from [Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) and extract the entire ZIP into a writable folder.
2. Double-click **BilingualSora2nd.exe**. Python and all runtime dependencies are included: no Python installation, CMD scripts, or first-run dependency downloads. Supports Windows 10/11 x64.
3. On first launch, choose the tool's interface language. The game's source language is detected after connection. The tool automatically connects to the game or waits for it to start. It never launches the game itself.

The Updates page links to the user guide and release notes. Download and log actions appear if an update fails. Launching the EXE again opens the existing interface without starting a second backend. The interface supports English, Japanese, and Simplified Chinese.

Download the ZIP only. **bilingual-sora-2nd-update.json** is updater metadata; GitHub's Source code archives are for developers. Keep the extracted folder intact; do not move only the EXE.

Upgrading from **0.2.x** requires a one-time manual migration because the old updater cannot install a bundled runtime. Exit the old tool, extract the new release into a new folder, copy **generated/native-control.json** and **generated/overlay-window.ini** (not **.venv/**, **generated/updates/**, or the old hot-reload manifest), then run the new EXE. Future portable releases automatically update both code and dependencies. Keep source checkouts separate.

Settings are grouped into Language, Text layout, Shortcuts, and Updates. Choose any primary/secondary pair under Language. In-game text language is a read-only detection status, not an editable setting. Failed connections retry automatically; the Language page also offers a manual connection button. The Mod's primary language controls displayed text without changing the game's setting.

### First-run defaults

The primary language defaults to the game's text language. The secondary defaults to Japanese, or English when the game is in Japanese.

These are initial preferences, not restrictions on language pairs. Existing settings survive restarts and updates unchanged. Choose English, Simplified Chinese, or Japanese for the interface on first launch; **Interface language** changes it live or follows the system. UI language, source matching, and display languages are independent.

The first load parses your local game resources and builds a cache, which can take time. Text is then rendered by native game controls; the Qt interface provides configuration and status. Use windowed or borderless mode; the settings overlay is not guaranteed to appear over exclusive fullscreen.

### Fonts for additional languages

Some language pairs need an expanded game font to avoid missing characters appearing as question marks. Once the tool finds the game directory, it automatically prepares fonts from your local game resources. While the game is running, files are only staged; they are safely installed after it exits and take effect after the next launch. Game fonts are not distributed here; two supplementary glyphs are bundled under the OFL.

No manual action is normally needed. Use this command only to diagnose or retry a failed automatic preparation:

```powershell
$runtime = Get-Content runtime/current.txt
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.install_font_patch --game "PATH_TO_GAME" --install
```

The installer includes the audited [sora2looseload](https://github.com/lmaple0/sora2looseload) loader (SHA-256 **e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7**). A mismatch is never bypassed, and files owned by another mod are not overwritten.

## Controls and configuration

Choose a display mode and adjust the text layout as needed. These are offline captures of the real settings interface, without a game connection. The left image selects the recommended single-language hold mode.

| Language and mode | Text layout |
|---|---|
| ![Language settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/settings-en.png) | ![Layout settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/layout-en.png) |

Click **Settings** on the status bar to open or close the panel. Drag the bar's text, empty space, handle, or the panel header to move both together; buttons retain their click actions. **× / Esc inside the panel** collapses it. **× on the status bar** hides the interface while the background service keeps running. Reopen it from the system tray or desktop shortcut.

| Action | Default shortcut |
|---|---|
| Show / hide the interface | Ctrl + Shift + F9 |
| Language switch for the selected mode | Ctrl + Shift + F10 |

Record one keyboard or SDL controller combination under **Shortcuts**. The same binding follows the selected mode. Existing custom bindings migrate; F11/F12 are no longer separate simultaneously active actions. By default, bindings respond while the game is in the foreground.

- **Bilingual mode**: shows both languages using the game's native annotation layout. The shortcut turns the secondary language on/off.
- **Single-language mode**: choose **press to switch** or **hold to show secondary**. Holding does not repeatedly toggle; releasing a hold or losing focus restores primary text.

Text size and spacing update live and persist across menus. Secondary color multiplies the original RGB values; defaults are RGB 230 / 230 / 230 and 90% opacity. Adjust opacity with the slider below the color button. The vertical offset applies only in bilingual mode; positive values move text down.

First use or changed game resources require language-cache preparation. Open the tool before starting the game and let preparation finish; valid caches are reused.

## Recommended usage and known limitations

For smoother play, select **Single-language mode → Hold for secondary language** (**Hold** in older versions), then bind a convenient keyboard or controller combination. Read the primary language normally, hold to switch to the secondary, and release to return. This avoids continuously laying out both languages together and is the recommended everyday setup. Switching can still trigger a brief layout update; zero latency is not guaranteed.

- **Bilingual dialogue-log performance remains an unresolved limitation.** Opening the log can cause a noticeable hitch, and its frame rate can be lower than in single-language mode. In-game feedback has reported opening pauses of around **700 ms**, including on repeated opens. Results vary with history size, language pair, and hardware. Caching and native optimizations reduce some costs but do not guarantee a hitch-free log; the issue should not be considered fixed. Use the single-language hold setup above if it affects your play.
- **The cost includes layout and parsing, not just font drawing.** Bilingual text uses the game's native annotation layout. The log processes historical text in bulk and repeatedly parses some controls while displayed. Changing secondary color or opacity does not remove that work.
- **Preparing a language pair can take time.** First connection, an uncached pair, or changed game resources require local resource processing. Start the tool early and allow preparation to finish. This is separate from the dialogue-log opening hitch.
- **Coverage and available space have limits.** Uncertain matches keep the original text; text embedded in images or videos is not processed. Bilingual text does not enlarge the game's fixed text boxes, so long text or large fonts may be crowded. Reduce text size or use single-language mode. The full game and every language pair have not been exhaustively verified.

## Automatic updates

The **Updates** tab has one **Automatic updates** switch, enabled by default. It checks this repository's stable releases on startup and every six hours. Turning it off stops automatic checks and installation; manual version checks remain available. Legacy notification-only preferences become off, without enabling installation.

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
.venv\Scripts\python.exe -m tools.build_portable --version 0.3.9 --repository Llugaes/bilingual-sora-2nd
```

The repository includes selected demonstration screenshots in its documentation; release packages omit these images. Neither includes game resource archives, generated game fonts, complete text indexes, logs, or user settings.

## License

Project code is available under [MIT](LICENSE). See [THIRD_PARTY.md](THIRD_PARTY.md) for third-party notices and references. This is an unofficial tool; the game, trademarks, and game assets belong to their respective owners.

## Acknowledgments

Thanks to the projects and maintainers whose work makes this tool possible:

- [0xDC00/scripts](https://github.com/0xDC00/scripts) and Tom (tomrock645): game text-hook call-site signatures and adapted code.
- [FPACker](https://github.com/coinkillerl/FPACker) and [Ingert](https://github.com/Aureole-Suite/Ingert): resource-container and script-format references.
- [sora2looseload](https://github.com/lmaple0/sora2looseload): the bundled game-font loader.
- [Frida](https://github.com/frida/frida): native runtime text handling; [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/): settings and status UI.
- [pygame-ce / SDL](https://github.com/pygame-community/pygame-ce): controller input; [pefile](https://github.com/erocarrera/pefile): PE inspection; [python-lz4 / LZ4](https://github.com/python-lz4/python-lz4): font-texture compression.
- [Inno Setup](https://jrsoftware.org/) and its [Chinese translation](https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation): Windows installer.

Dependencies retain their own licenses. Notices for adapted code are preserved in [THIRD_PARTY.md](THIRD_PARTY.md).
