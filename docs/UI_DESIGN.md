# Native settings UI design

The Windows settings surface uses a local, game-adjacent paper panel. It does not load, copy, or depend on game assets, so the first-run language choice and offline configuration remain available without a game process or network connection.

| Role | Token | Use |
| --- | --- | --- |
| Paper surface | `#f8f3e8` | Window and settings panel |
| Ink and title | `#33291f` / `#70451b` | Readable body text and brown-gold hierarchy |
| Teal action | `#167b78` | Primary action, focus, checked state and live status |
| Gold selection | `#d9ac3a` | Selected tab and slider handle |
| Warm border | `#b89555` | Panel, control and divider boundaries |

The window is organized by task rather than implementation fields, with four short tabs that remain legible in every UI locale:

1. A compact, always-visible status line sits above the tabs. It shows the connection state, read-only backend-detected in-game text language, and a connect/reconnect button only when needed. Unknown values say “waiting for detection”; the detected language is never written as a user game setting.
2. **Language** holds interface language, Mod display languages, color and opacity, enable/disable, and mode. Display has only bilingual and single-language modes; the single-language choice then exposes toggle and hold behaviour. The color button opens the RGBA picker, while its adjacent 0–100% slider updates and immediately saves the same normalized `secondary_opacity` value.
3. **Text layout** contains annotation scale, offsets, spacing, and reset action. The color selector stores normalized RGB floats (`secondary_color`) and a normalized alpha (`secondary_opacity`); the bilingual vertical offset is `bilingual_offset_y` and positive values move both lines down.
4. **Shortcuts** holds the selected action and keyboard/controller bindings. Recording instructions and cancellation appear only while recording; clearing appears only for an existing controller binding. There is no separate apply-mode button; selecting the mode already saves and applies it. Retrying a failed language change is offered on the Language page only after a failure.
5. **Updates** holds a single automatic-update checkbox, manual checking, and links to the guide and release notes. Download/recovery/log controls appear only after failure. Desktop shortcut creation belongs to installation and is no longer duplicated here. Legacy notify-only settings behave as off; they do not grant installation consent.

The initial local dialog stores only one UI locale (`zh-Hans`, `en`, or `ja`). It never asks for game source text language. Existing control files remain untouched. UI locale is stored separately from the detected game source and the Mod output pair.

The theme provides visible teal focus rings, labelled controls, gold selected tabs, dark readable status colors, explicit combo chevrons, and check marks. Text settings use a slider and a complete editable numeric box; duplicate plus/minus controls are removed. Values loaded or typed precisely are not rounded through the slider's integer ticks.

Each tab scrolls its own content so navigation stays visible. The small bar and panel form one moving group: either header handle moves both, and opening clamps the whole group to the available screen. The small bar is one compact line: a shaped and colored status marker with text/tooltip semantics, the short language pair, settings toggle, and exit. Its status marker, status text, and unused bar surface all drag the group; the settings and exit buttons retain their click actions. Detailed state and the overlay shortcut remain in tooltips. Existing language, layout, and shortcut preferences are preserved.

The Language page exposes a manual connect/reconnect button only while offline or after a connection error. During a connection attempt it stays visible but disabled with explicit progress text; after a ready acknowledgement it is hidden. The button delegates retry policy to the resident auto-connector, which never replaces a live backend connection.
