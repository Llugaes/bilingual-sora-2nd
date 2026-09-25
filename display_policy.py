"""Pure render-selection state for bilingual annotations and language swaps."""

from __future__ import annotations

from dataclasses import dataclass


INTERACTIONS = frozenset({"annotation", "language_toggle", "language_hold"})
RENDER_MODES = frozenset({"annotation", "primary", "secondary"})


@dataclass(frozen=True)
class DisplayState:
    """A renderer-facing snapshot; language codes are passed through unchanged."""

    primary: str
    secondary: str
    interaction: str
    annotation_enabled: bool
    render_mode: str


class DisplayPolicy:
    """Select a render mode from already-polled input edges and held state.

    ``annotation`` starts enabled and a press toggles its small secondary-text
    annotation.  ``language_toggle`` switches primary/secondary on each press.
    ``language_hold`` renders secondary only while the effective binding is
    held.  It deliberately has no platform or input-polling dependency.
    """

    def __init__(
        self,
        primary: str,
        secondary: str,
        interaction: str = "annotation",
        *,
        annotation_enabled: bool = True,
    ) -> None:
        self.primary = self._language(primary, "primary")
        self.secondary = self._language(secondary, "secondary")
        self.interaction = self._interaction(interaction)
        self.annotation_enabled = bool(annotation_enabled)
        self._language_mode = "primary"

    @staticmethod
    def _language(value: str, name: str) -> str:
        language = str(value).strip()
        if not language:
            raise ValueError(f"{name} language must be non-empty")
        return language

    @staticmethod
    def _interaction(value: str) -> str:
        interaction = str(value).strip()
        if interaction not in INTERACTIONS:
            raise ValueError(f"unknown display interaction: {interaction}")
        return interaction

    def set_interaction(self, interaction: str, *, annotation_enabled: bool | None = None) -> DisplayState:
        """Change interaction and reset language selection to the primary side."""
        self.interaction = self._interaction(interaction)
        self._language_mode = "primary"
        if annotation_enabled is not None:
            self.annotation_enabled = bool(annotation_enabled)
        return self.state()

    def set_languages(self, primary: str, secondary: str) -> DisplayState:
        """Replace either language without changing the current interaction state."""
        self.primary = self._language(primary, "primary")
        self.secondary = self._language(secondary, "secondary")
        return self.state()

    def advance(self, *, held: bool, pressed: bool, released: bool = False) -> DisplayState:
        """Apply one input tick and return the selected renderer mode.

        ``released`` is intentionally accepted even though hold mode can derive
        primary from ``held``.  This keeps the contract symmetric with
        :class:`inputs.HotkeyState` and documents that focus-loss release is a
        valid transition.
        """
        del released
        if self.interaction == "annotation":
            if pressed:
                self.annotation_enabled = not self.annotation_enabled
        elif self.interaction == "language_toggle":
            if pressed:
                self._language_mode = "secondary" if self._language_mode == "primary" else "primary"
        else:  # language_hold
            self._language_mode = "secondary" if held else "primary"
        return self.state()

    def state(self) -> DisplayState:
        if self.interaction == "annotation":
            render_mode = "annotation" if self.annotation_enabled else "primary"
        else:
            render_mode = self._language_mode
        return DisplayState(
            primary=self.primary,
            secondary=self.secondary,
            interaction=self.interaction,
            annotation_enabled=self.annotation_enabled,
            render_mode=render_mode,
        )
