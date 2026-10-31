# Sora Bilingual — Trails in the Sky the 2nd bilingual mod

[简体中文](README.md) · **English** · [日本語](README.ja.md)

Display two languages together in the PC game, or hold a shortcut to switch temporarily. Supports Japanese, English, Simplified and Traditional Chinese, Korean, French, German and Spanish.

**[Download · GitHub](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) · [Gitee mirror](https://gitee.com/Llugaes/bilingual-sora-2nd/releases) · [Release notes](RELEASE_NOTES.md)**

![English–Japanese dialogue](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-en-ja.jpg)

## See it in game

Compare dialogue, menus and item descriptions side by side, or hold a shortcut when you need a second language. These are gameplay examples from previous project versions; size and spacing depend on the version and your settings. They are not a screen-by-screen validation of 1.0.2.

| Item names and descriptions | Equipment and stats |
|---|---|
| ![Items](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/items.jpg) | ![Equipment](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/equipment.jpg) |

<details>
<summary>More examples: dialogue logs, field prompts and other language pairs</summary>

![Bilingual dialogue log](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-log-zh-ja.jpg)

![Field interactions](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/field.jpg)

![Chinese–Japanese dialogue](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-zh-ja.jpg)

![English–Japanese arts and descriptions](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/arts-en-ja.jpg)

</details>

## Install

1. Download the stable `windows-x64-setup.exe` from [GitHub Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) or [Gitee](https://gitee.com/Llugaes/bilingual-sora-2nd/releases) and install it.
2. Open **Bilingual Sora 2nd**, choose an interface language, then launch the game. Game discovery, text-language detection, fonts and mapping preparation are automatic. The first preparation may take several minutes.
3. Choose a secondary language under **Language & display**. The primary follows the game automatically. If the game switches to your secondary, the two swap; otherwise your secondary stays unchanged. The languages must differ.

Windows 10/11 x64; no administrator rights or separate Python installation required. The installer works offline and upgrades preserve settings. For the portable edition, extract and run `BilingualSora2nd.exe`. First game-language detection sets the initial secondary. Your secondary preference is then preserved, except when a language collision requires a swap. Game language settings, original PACs and EXE are unchanged.

Enable **Experimental**, off by default, to choose a primary manually. This experimental feature may introduce instability, unpredictable behavior and bugs. To experience another primary language, we recommend changing the language in the game. Turn it off to follow the game again.

## Use

**Recommended: single-language mode → hold for secondary.** Hold to compare, release to return. Bilingual mode shows both together. Adjust size, spacing, color and opacity under **Text layout**.

| Mode | Normally shows | Language shortcut |
|---|---|---|
| Single language · hold | Primary language | Hold for secondary; release to return |
| Single language · toggle | One selected language | Switch between primary and secondary |
| Bilingual | Both languages | Show or hide secondary |

These screenshots were generated offline from the **actual 1.0.2 settings UI**, without a game connection. Choose the mode and secondary language on the left; adjust text size, spacing and color on the right. Changes save automatically.

| Language & display | Text layout |
|---|---|
| ![1.0.2 language settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/settings-en.png) | ![1.0.2 text layout](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/layout-en.png) |

| Action | Default shortcut |
|---|---|
| Show / hide interface | Ctrl + Shift + F9 |
| Language switch for the current mode | Ctrl + Shift + F10 |

Under **Quick actions**, select an action and record a keyboard or controller combination. Controller names are detected automatically or selected as PlayStation, Xbox or Switch; changing names preserves the binding.

<details>
<summary>Where to record keyboard and controller shortcuts</summary>

![Quick actions](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/shortcuts-en.png)

</details>

Click the compact window or gear to open settings; hold and drag to move it. **—** and the settings **×** hide to tray; right-click the tray to exit completely. Text, symbols and color distinguish building, connecting, ready, disabled and error states. **Appearance** provides three themes, Chinese/English/Japanese interface languages and background opacity.

![Compact window: languages, connection status and settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/status-bar-en.png)

<details>
<summary>Three themes, interface languages and background opacity</summary>

![Appearance settings](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/appearance-en.png)

</details>

Additional fonts are prepared automatically from your local game resources and loaded on connection. The UI reports progress and errors. Manual font installation is normally unnecessary; allow time for the first preparation.

## Limits and compatibility

- Bilingual dialogue logs can still hitch when opened and reduce frame rate. Single-language hold mode can reduce the burden.
- Uncertain matches retain original text. Text in images or videos is excluded. Fixed game text boxes may crowd long text; reduce size or use single-language mode.
- New combinations still require mapping work. Valid language-local parsing and identity caches are reused; zero waiting is not guaranteed.
- This release was tested on Steam PC 1.04. The tool is for **Trails in the Sky the 2nd**; it does not support **Trails in the Sky the 1st**.
- Accepted 0.4.2 samples include original Steam build 25386012 / EXE 1.03.2 and the EXE bundled with full-voice MOD 1.0.7. The latter tested only the replacement EXE, not the complete voice resources. Other modified EXEs, the full game and all language combinations have not been individually tested.

## Updates and help

**1.1.0 reduces stalls while loading a complete mapping model.** Reading, validation and construction run in batches; callbacks keep using the complete previous model until its replacement is ready. Valid existing caches remain reusable. Compatibility checks locate the native functions and data structures the tool uses, without locking to a game version number. See the [1.1.0 verification report](docs/verification/compatibility-1.1.0.md) for performance evidence and in-game validation limits. The dynamic-call and NPC-branch fixes from 1.0.4 remain included. Eight audited Chinese dialogue lines lack corresponding official Japanese text and retain their source text; see the [text coverage report](docs/verification/dialogue-coverage-1.0.4.md).

**1.0.2 fixes continuous memory growth with bilingual display enabled and reduces model preparation peaks.** It also adds equipment restriction labels, unifies small-title and item-description layouts, and fixes text shifting on menu entry. See the [memory verification report](docs/verification/memory-r8.md) for methods, comparisons against the r7 candidate and coverage limits. Memory improvements are not a claim of higher frame rates throughout the game.

The startup fixes from 1.0.1 remain included. First use and changed game resources still require preparation; 1.0.0 remains withdrawn from stable updates.

Automatic checks only notify. Download, install and rollback require manual confirmation; exit the game before updating. Gitee is preferred for downloads in China; GitHub retains full portable packages and older releases. Roll back with an older complete package, preserve settings and optionally disable update checks.

<details>
<summary>Where to update or choose a previous version</summary>

![1.0.2 update panel](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/updates-en.png)

</details>

| Download | Purpose |
|---|---|
| `windows-x64-setup.exe` | Recommended: install or upgrade |
| `windows-x64.zip` without `app` / `runtime` | Complete portable edition; extract and run |
| `app` / `runtime` ZIPs and `update.json` | In-app update components; no separate manual installation needed |

For connection failures, read status details and retry; for font failures, check font status. Windowed/borderless mode works best for the tool interface. Report tool/game versions, game text language, primary/secondary languages and a short error excerpt. Do not upload complete game resources, caches or saves.

Development: [Contributing](CONTRIBUTING.md), [Architecture](docs/ARCHITECTURE.md), [Debugging](docs/DEBUGGING.md), [Verification](docs/verification/README.md). Local candidates require explicit in-game user acceptance before public release.

## License and thanks

Code: [MIT](LICENSE). Dependency and adapted-code notices: [THIRD_PARTY.md](THIRD_PARTY.md). Thanks to the maintainers of 0xDC00/scripts, Tom, FPACker, Ingert, sora2looseload, Frida, Qt/PySide6, pygame-ce/SDL, pefile, LZ4, Inno Setup and its Chinese translation.

Unofficial tool; game, trademarks and artwork belong to their owners. Releases exclude game archives, generated game fonts, complete text indexes and user settings.
