"""Installed game locale metadata. Display logic must not branch on locale IDs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Locale:
    name: str
    short_name: str
    archive_suffix: str
    font_suffix: str
    default_secondary: str = "ja"


LOCALES = {
    "ja": Locale("日本語", "日文", "", "", "en"),
    "en": Locale("English", "英文", "_en", ""),
    "zh-Hans": Locale("简体中文", "简中", "_sc", "_sc"),
    "zh-Hant": Locale("繁體中文", "繁中", "_tc", "_tc"),
    "ko": Locale("한국어", "韩文", "_ko", "_ko"),
    "fr": Locale("Français", "法文", "_fr", ""),
    "de": Locale("Deutsch", "德文", "_de", ""),
    "es": Locale("Español", "西文", "_es", ""),
}
LANGUAGES = tuple(LOCALES)
DEFAULT_PRIMARY = "zh-Hans"
DEFAULT_SECONDARY = "ja"


def language_defaults(game_language):
    """First-run preferences only; never constrain an explicitly selected pair."""
    if not isinstance(game_language, str) or game_language not in LOCALES:
        raise ValueError("未知语言")
    return {
        "game_language": game_language,
        "primary": game_language,
        "secondary": LOCALES[game_language].default_secondary,
    }


def archive_names(kind):
    return {code: kind + value.archive_suffix + ".pac" for code, value in LOCALES.items()}
