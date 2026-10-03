# Handbook settings UI

The Qt interface implements approved concept A with original game artwork. Since 0.3.29, Appearance offers three complete skins: Trails in the Sky (the existing default), Bracer Notebook, and Orbal Workshop. Seventeen slices are compiled into `app/handbook_resources.py` using Qt RCC and cached as pixmaps. Opening the UI never scans a game archive or requires a game/network connection. Artwork is separate from the code MIT license; THIRD_PARTY.md and the source artwork NOTICE/provenance record its origin.

Rebuild artwork with `.venv/Scripts/pyside6-rcc.exe sora_bilingual/app/assets/handbook/handbook.qrc -o sora_bilingual/app/handbook_resources.py`. Keep the module in the release allowlist and UI reload group. Compiled Python resources are compatible with older updaters' file policy. Source PNGs/QRC/provenance stay in the repository, not as runtime dependencies.

## Navigation and controls

- Game content: Language & display, Text layout, Quick actions. Tool preferences: Appearance. Each page scrolls independently while navigation remains visible. Mode cards stack when large text cannot fit side by side.
- Since 0.3.28, the artwork's leather/paper divider and the navigation share fixed logical column dimensions instead of stretching the whole book. Navigation labels wrap inside their bars, including long words at larger font sizes; one text layout handles both measurement and painting. Group labels and the example caption wrap as needed.
- Language: enable switch first, primary/secondary columns, bilingual/single-language selection and toggle/hold behaviour. Selected controls are solid circles; others are hollow circles. The dialogue sample is labelled as an illustration, not live game output.
- Layout: scale, offsets, spacing, secondary RGB/opacity and reset. Exact typed/loaded numbers do not round-trip through integer sliders. Runtime configuration fields are unchanged.
- Shortcuts: select an action, record keyboard/controller combinations and choose a controller label family. Naming never changes raw input; capture instructions/cancel/clear appear when relevant.
- Appearance: preview cards select a complete skin immediately; UI locale and compact-bar background opacity remain below them. The selected appearance is stored beside window position/opacity in `generated/overlay-window.ini`, never in runtime/game configuration. Missing or unrecognized values use the existing default without rewriting other preferences. Closed dropdowns ignore wheel events.

`app/appearance.py` owns the skin catalog, palettes and ancestor-based lookup. `handbook.paint_surface` renders windows, tabs, cards, popups, the compact bar and chooser previews from the same original slices. Bracer Notebook uses note/quest/camp textures and copper/burgundy controls; Orbal Workshop uses blue circuit and mechanical assets with a dark palette. Appearance changes do not create timers/workers, start archive scans or reload mapping. Decoded pixmaps are cached; only large low-contrast background textures are reduced during asset extraction. Crop rectangles, resampling and mirrored cap assembly are recorded in provenance. The selection circle, text and arrow remain visible rather than relying on colour alone.

The connection strip stays outside scrolling pages. Manual connection is available offline, disabled while connecting and hidden after readiness. Font/progress/error details remain explicit on the language page. The existing connector owns preparation, retries and language detection; the skin starts no additional worker.

## Updates and lifecycle

The persistent Updates button opens a framed popup with installed/available versions, release title, update policy, manual check and recovery actions. Real availability makes the button gold with a red dot and adds a dot to the compact gear. Both use UpdatePage.availability_changed. Opening/closing does not clear availability; a check confirming no newer version clears it. The existing background service performs network/download/install work. Guide, release notes and About are in the ellipsis menu.

The bar and panel move together. Click toggles settings; dragging beyond the system threshold only moves them. **—, × and window-manager close hide both windows to the tray**. Esc collapses settings to the bar; Esc inside the update popup closes that popup. Tray click, shortcut and hotkey restore settings. Only the tray Exit tool action enters the existing safe shutdown flow and stops effects.

Pin is removed. Windows remain on top until hidden; legacy bar_pinned is ignored without rewriting the configuration. Since 0.3.30, the bar control displays opacity: 100% (default) shows the full background, and lower values fade only artwork, not foreground text/icons/dots. The existing `bar_transparency` INI key and renderer retain their original scale; UI read/write and signal boundaries convert with `100 - opacity`, preserving the exact rendered alpha and compatibility with earlier releases. Minimum background alpha one at 0% opacity preserves Windows pointer hit testing.

Regression evidence: [0.3.27 interactions](verification/handbook-0327.md), [0.3.28 sidebar bounds](verification/handbook-0328.md), [0.3.29 appearances](verification/appearance-0329.md).

## Documentation captures

`python -X utf8 tests/render_overlay_preview.py` captures the actual Qt pages in all three UI languages, using isolated temporary configuration and no game connection or network. The navigation labels are asserted; the fourth page is Appearance, while Updates is captured through its separate header popup. The recommended single-language hold mode is selected. Settings windows expand to show all controls without scrolling; the script checks both scrollbar ranges before saving each page.

Review `generated/ui-guide/` visually before copying referenced images into `docs/images/`. The offline screenshots show no connected game and no update result. They demonstrate controls, not successful runtime preparation or release verification. See [the October 3 review](verification/todo-review-20261003.md) for the refreshed README coverage and remaining checks.
