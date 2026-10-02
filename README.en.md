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

1. Download `bilingual-sora-2nd-VERSION-windows-x64-setup.exe` from the [latest release](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) and run the installer.
2. Open **Bilingual Sora 2nd** from the Start menu or desktop shortcut. Choose the interface language on first launch. The primary language syncs when connecting to a new game process; you can then change either display language.
3. The tool automatically finds the game and prepares multilingual fonts. No folder or game-language selection is needed. You can start the game before preparation finishes; fonts load into the running game when ready. First-time language mapping may take a few minutes, and valid caches are reused.

Supports Windows 10/11 x64 without administrator rights. Python and runtime dependencies are bundled, so the downloaded installer works offline with no separate environment setup. The interface supports English, Japanese, and Simplified Chinese. Updates retain existing settings.

See the [FAQ](#frequently-asked-questions-faq) for portable use, older-version migration, and troubleshooting.

The header’s ··· menu links to the user guide and release notes. Opening the application again shows the existing interface without starting another backend.

The game-art handbook groups settings into Language & display, Text layout, Quick actions, and Appearance. Updates has its own header button. Choose any primary/secondary pair under Language. In-game text language is a read-only detection status, not an editable setting. Failed connections retry automatically; the Language page also offers a manual connection button. The Mod's primary language controls displayed text without changing the game's setting.

### First-run defaults

The primary language defaults to the game's text language. The secondary defaults to Japanese, or English when the game is in Japanese.

The primary language syncs once from the actual game text language each time a new game process starts. You can then change it; reconnecting to that same game process preserves your choice. Secondary language and other preferences survive restarts and updates. Choose English, Simplified Chinese, or Japanese for the interface on first launch, or change **Interface language** under **Appearance**. The Language page places the enable switch first, with primary and secondary choices side by side. Scrolling over a closed dropdown does not change its selection.

The tool automatically finds Steam installations. After the first game launch, it detects the actual text language and builds a cache from local resources. Valid caches are reused; the game language setting is never changed. Text is rendered by native game controls; the Qt interface provides configuration and status. Use windowed or borderless mode; the settings overlay is not guaranteed to appear over exclusive fullscreen.

### Fonts for additional languages

Some language pairs need an expanded game font to avoid missing characters appearing as question marks. Fonts are prepared from local game resources: installed while the game is closed, or loaded together with their atlas into the running game without a font-related restart. Preparation, loading, readiness, and failure are shown separately. Game fonts are not distributed here; two supplementary glyphs are bundled under the OFL.

## Controls and configuration

Choose a display mode and adjust the text layout as needed. These are offline captures of the real settings interface, without a game connection. The left image selects the recommended single-language hold mode.

| Language and mode | Text layout |
|---|---|
| ![Language settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/settings-en.png) | ![Layout settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/layout-en.png) |

Click the bar or its gear to toggle settings; hold and drag to move both windows. The bar shows the language pair and current mode. **— and the settings window’s × hide both windows to the tray**, keeping effects active. Esc collapses settings only. Right-click the tray icon and select Exit tool to stop effects and quit. Click the tray icon or launch the desktop shortcut to restore settings.

**Status bar background transparency**, under Appearance, fades only the bar’s background and borders. Text, icons and settings remain opaque. At 100%, clicking and dragging still work. Transparency and position are saved automatically.

Under **Appearance → Tool theme**, switch instantly between **Trails in the Sky (default)**, **Bracer Notebook**, and **Orbal Workshop**. Each uses original game interface artwork across the settings panel, status bar, and update window. Your choice is saved automatically and does not change the in-game display.

| Action | Default shortcut |
|---|---|
| Show / hide the interface | Ctrl + Shift + F9 |
| Language switch for the selected mode | Ctrl + Shift + F10 |

Record one keyboard or SDL controller combination under **Shortcuts**. The same binding follows the selected mode. Existing custom bindings are retained. By default, bindings respond while the game is in the foreground.

Bindings use device-specific names: L1/R1, L2/R2 and L3/R3 for PlayStation; LB/RB, LT/RT and LS/RS (click) for Xbox; L/R, ZL/ZR and stick clicks for Nintendo Switch. Face buttons, the D-pad and stick directions also follow the device mapping. If Steam Input exposes your controller as Xbox, select a style under **Controller button labels**; this changes names only. Newly recorded bindings retain their names when disconnected; reconnect the matching controller to identify older bindings. Inputs without an SDL mapping retain their raw numbers.

- **Bilingual mode**: shows both languages using the game's native annotation layout. The shortcut turns the secondary language on/off.
- **Single-language mode**: choose **press to switch** or **hold to show secondary**. Holding does not repeatedly toggle; releasing a hold or losing focus restores primary text.

Text size and spacing update live and persist across menus. Secondary color multiplies the original RGB values; defaults are RGB 230 / 230 / 230 and 90% opacity. Adjust opacity with the slider below the color button. The vertical offset applies only in bilingual mode; positive values move text down.

On first connection or after game resources change, language caches are prepared automatically. This may take a few minutes; valid caches are reused.

## Recommended usage and known limitations

For smoother play, select **Single-language mode → Hold for secondary language**, then bind a convenient keyboard or controller combination. Read the primary language normally, hold to switch to the secondary, and release to return. This avoids continuously laying out both languages together and is the recommended everyday setup. Switching can still trigger a brief layout update; zero latency is not guaranteed.

- **Bilingual dialogue-log performance remains an unresolved limitation.** Opening the log can cause a noticeable hitch, and its frame rate can be lower than in single-language mode. In-game feedback has reported opening pauses of around **700 ms**, including on repeated opens. Results vary with history size, language pair, and hardware. Caching and native optimizations reduce some costs but do not guarantee a hitch-free log; the issue should not be considered fixed. Use the single-language hold setup above if it affects your play.
- **The cost includes layout and parsing, not just font drawing.** Bilingual text uses the game's native annotation layout. The log processes historical text in bulk and repeatedly parses some controls while displayed. Changing secondary color or opacity does not remove that work.
- **Preparing a language pair can take time.** First connection, an uncached pair, or changed game resources require local resource processing. Initialization runs automatically, and secondary text appears when it finishes. This is separate from the dialogue-log opening hitch.
- **Coverage and available space have limits.** Uncertain matches keep the original text; text embedded in images or videos is not processed. Bilingual text does not enlarge the game's fixed text boxes, so long text or large fonts may be crowded. Reduce text size or use single-language mode. The full game and every language pair have not been exhaustively verified.

## Automatic updates

**Automatic updates** is enabled by default in the header’s Updates panel. It checks stable releases on startup and every six hours, downloads and verifies updates in the background, and installs after the game connection ends. The interface reloads with settings, caches, and window state preserved. Manual checks remain available when automatic updates are off. An available release turns the button gold with a red dot; the compact gear also shows a dot. Opening the panel does not clear the reminder.

## Frequently asked questions (FAQ)

<details>
<summary>Why does Setup report the tool is running after I exit it?</summary>

In 0.3.15 and earlier, the game connection remains alive until the game exits, so Setup may still detect it. Save and exit the game, then quit the tool from its tray menu and retry.

Starting with 0.3.16, tray **Exit tool** disables bilingual effects and waits for all UI, backend, and preparation processes to finish before removing the tray icon. The game keeps running; reopening the tool restores bilingual display. Hiding or collapsing the interface keeps the connection. A connection established by an older version needs one normal game exit before the new exit mechanism can be used.

</details>

<details>
<summary>How do I use the portable edition, and what are the other release files?</summary>

Download the complete `bilingual-sora-2nd-VERSION-windows-x64.zip` without `app` or `runtime` in its name. Extract it into a separate writable folder and open **BilingualSora2nd.exe**. Keep the entire folder intact; do not move only the EXE.

The `app` and `runtime` ZIPs and `bilingual-sora-2nd-update.json` are for the updater; GitHub Source code archives are for developers. The updater reuses unchanged runtime dependencies, and intermediate versions can be skipped.

</details>

<details>
<summary>How do I upgrade an old version or resolve the “too many files” error?</summary>

Upgrading from **0.2.x** requires a one-time manual migration because the old updater cannot install a bundled runtime. Exit the old tool, extract the new release into a new folder, copy **generated/native-control.json** and **generated/overlay-window.ini** (not **.venv/**, **generated/updates/**, or the old hot-reload manifest), then run the new EXE. Future portable releases automatically update both code and dependencies. Keep source checkouts separate.

The 0.2.2 “too many files” error is also an old-updater limitation; use the migration steps above. Versions 0.3.0–0.3.3 download one complete automatic upgrade before switching to component updates.

</details>

<details>
<summary>How do I reinstall or uninstall?</summary>

Exit the tool from its tray menu and end its game connection before reinstalling or uninstalling. Run the latest installer to reinstall, or uninstall through Windows Installed apps. Personal settings are retained, and setup never force-closes the game.

</details>

<details>
<summary>How do I troubleshoot failed automatic font preparation?</summary>

No manual action is normally needed. Use this command only to diagnose or retry a failed automatic preparation:

```powershell
$runtime = Get-Content runtime/current.txt
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.install_font_patch --game "PATH_TO_GAME" --install
```

The installer includes the audited [sora2looseload](https://github.com/lmaple0/sora2looseload) loader (SHA-256 **e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7**). A mismatch is never bypassed, and files owned by another mod are not overwritten.

</details>

<details>
<summary>How do I recover from an update failure, and where are my settings?</summary>

If an update fails, use the download and log actions on the Updates panel. You can reinstall using the latest setup EXE.

Downloads are verified against the repository, version, file list, and SHA-256 hashes. Installation waits until the game connection ends. The interface then reloads automatically, restoring its position and expanded/hidden state. Settings and caches stay in **generated/**; bundled dependencies stay in **runtime/**. If installation is interrupted, the next shortcut launch completes it or restores the old files. Backups live under **generated/updates/backup-***.

Automatic installation requires a release installation containing **installed-manifest.json**. Git development directories and manually modified software files are not overwritten. Runtime updates install into a new versioned directory and switch on UI reload. Loaded DLLs are not overwritten; old runtimes remain available for recovery and consume additional disk space. Drafts, prereleases, and older versions are not installed automatically.

</details>

## Development and contributing

<details>
<summary>Development setup, tests, and release commands</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m tools.dev check
```

**tests/check_overlay_update.py** exercises real Qt reloads using isolated settings and does not connect to the game. **tests/check_native_transport.py** requires local resources and attaches only to its own test process. These integration checks are separate from CI's game-free unit tests.

Publish local changes with **python -m tools.dev publish-local**. It validates syntax and atomically publishes the hot-reload manifest. The UI and text logic can reload; resident hook changes wait for the next game launch. Do not forcibly kill or unload an injected script while the game is running.

See the [architecture](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/ARCHITECTURE.md) and [contribution guide](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/CONTRIBUTING.md), currently in Chinese. Issues and pull requests are welcome. Include the tool version, game version, language pair, reproduction steps, and a short relevant error excerpt. Do not upload complete game resources.

For a release, maintainers update both **distribution.json** and **pyproject.toml**, then push a matching **vX.Y.Z** tag. GitHub Actions validates on Windows and builds the complete ZIP, update components, and offline installer from an explicit file allowlist. After portable-launch and installer checks pass, it uploads all assets to a draft and publishes them together. Manual build:

```powershell
$distribution = Get-Content distribution.json | ConvertFrom-Json
.venv\Scripts\python.exe -m tools.build_portable --version $distribution.version --repository $distribution.repository
```

The repository includes selected demonstration screenshots in its documentation; release packages omit these images. Neither includes game resource archives, generated game fonts, complete text indexes, logs, or user settings.

</details>

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
