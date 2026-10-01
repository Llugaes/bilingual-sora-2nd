# Handbook settings UI

The 0.3.27 Qt interface implements approved concept A with original game handbook, metal bars, emblem, selection arrow and dialogue corners. Seven slices are compiled into `app/handbook_resources.py` using Qt RCC and cached as pixmaps. Opening the UI never scans a game archive or requires a game/network connection. Artwork is separate from the code MIT license; THIRD_PARTY.md and the source artwork NOTICE/provenance record its origin.

Rebuild artwork with `.venv/Scripts/pyside6-rcc.exe sora_bilingual/app/assets/handbook/handbook.qrc -o sora_bilingual/app/handbook_resources.py`. Keep the module in the release allowlist and UI reload group. Compiled Python resources are compatible with older updaters' file policy. Source PNGs/QRC/provenance stay in the repository, not as runtime dependencies.

## Navigation and controls

- Game content: Language & display, Text layout, Quick actions. Tool preferences: Appearance. Each page scrolls independently while navigation remains visible. Mode cards stack when large text cannot fit side by side.
- Since 0.3.28, the artwork's leather/paper divider and the navigation share fixed logical column dimensions instead of stretching the whole book. Navigation labels wrap inside their bars, including long words at larger font sizes; one text layout handles both measurement and painting. Group labels and the example caption wrap as needed.
- Language: enable switch first, primary/secondary columns, bilingual/single-language selection and toggle/hold behaviour. Selected controls are solid circles; others are hollow circles. The dialogue sample is labelled as an illustration, not live game output.
- Layout: scale, offsets, spacing, secondary RGB/opacity and reset. Exact typed/loaded numbers do not round-trip through integer sliders. Runtime configuration fields are unchanged.
- Shortcuts: select an action, record keyboard/controller combinations and choose a controller label family. Naming never changes raw input; capture instructions/cancel/clear appear when relevant.
- Appearance: UI locale and compact-bar background transparency. UI preferences do not modify game language or backend-owned fields. Closed dropdowns ignore wheel events.

The connection strip stays outside scrolling pages. Manual connection is available offline, disabled while connecting and hidden after readiness. Font/progress/error details remain explicit on the language page. The existing connector owns preparation, retries and language detection; the skin starts no additional worker.

## Updates and lifecycle

The persistent Updates button opens a framed popup with installed/available versions, release title, update policy, manual check and recovery actions. Real availability makes the button gold with a red dot and adds a dot to the compact gear. Both use UpdatePage.availability_changed. Opening/closing does not clear availability; a check confirming no newer version clears it. The existing background service performs network/download/install work. Guide, release notes and About are in the ellipsis menu.

The bar and panel move together. Click toggles settings; dragging beyond the system threshold only moves them. **—, × and window-manager close hide both windows to the tray**. Esc collapses settings to the bar; Esc inside the update popup closes that popup. Tray click, shortcut and hotkey restore settings. Only the tray Exit tool action enters the existing safe shutdown flow and stops effects.

Pin is removed. Windows remain on top until hidden; legacy bar_pinned is ignored without rewriting the configuration. Bar transparency fades only artwork, not foreground text/icons/dots. Minimum background alpha one preserves Windows pointer hit testing.

Regression evidence: [0.3.27 interactions](verification/handbook-0327.md), [0.3.28 sidebar bounds](verification/handbook-0328.md).
