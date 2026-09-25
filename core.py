"""Exact local translation lookup and live presentation state; no fuzzy translation."""
from __future__ import annotations

from collections import defaultdict
import re

LANGUAGES = {
    'zh-Hans': '简体中文', 'ja': '日本語', 'en': 'English',
    'zh-Hant': '繁體中文', 'ko': '한국어', 'fr': 'Français',
    'de': 'Deutsch', 'es': 'Español',
}
DEFAULT_CONFIG = {
    'primary_language': 'zh-Hans', 'secondary_language': 'ja', 'overlay_enabled': True,
    'font_size': 24, 'width_percent': 80, 'bottom_offset_percent': 4,
    'display_mode': 'two_lines', 'timeout_seconds': 30,
    'hotkey': {'keyboard': ['CTRL', 'SHIFT', 'F10']},
}


def display_text(text: str) -> str:
    # Keep words/numbers intact. In particular, don't apply the upstream hook's
    # broad [a-z][0-9]+ regex to language-learning text.
    text = re.sub(r'<[^<>]*>', '', text)
    text = re.sub(r'[\x00-\x08\x0b-\x1f]', '', text)
    return text.replace('\r\n', '\n').strip()


def normalize(text: str) -> str:
    return re.sub(r'\s+', '', display_text(text))


class Catalog:
    def __init__(self, data: dict):
        if data.get('version') != 1:
            raise ValueError('不支持的文本索引版本')
        self.entries = data['entries']
        self.raw = defaultdict(set)
        self.cleaned = defaultdict(set)
        for i, entry in enumerate(self.entries):
            for value in entry['texts'].values():
                if value:
                    self.raw[value].add(i)
                    key = normalize(value)
                    if key:
                        self.cleaned[key].add(i)

    def lookup(self, text: str, primary: str, secondary: str):
        """Return a pair only when all matching keys agree in both languages."""
        ids = self.raw.get(text) or self.cleaned.get(normalize(text), set())
        pairs = set()
        for i in ids:
            texts = self.entries[i]['texts']
            if primary not in texts or secondary not in texts:
                return None, 'missing_language'
            pairs.add((display_text(texts[primary]), display_text(texts[secondary])))
        if len(pairs) == 1:
            return pairs.pop(), 'matched'
        return None, 'ambiguous' if pairs else 'not_found'


class Presentation:
    def __init__(self, catalog: Catalog, config: dict):
        self.catalog = catalog
        self.config = {**DEFAULT_CONFIG, **config}
        self.raw = ''
        self.status = 'empty'

    def update(self, raw: str):
        self.raw = raw
        return self.lines()

    def lines(self):
        if not self.raw or not self.config['overlay_enabled']:
            return '', ''
        pair, self.status = self.catalog.lookup(
            self.raw, self.config['primary_language'], self.config['secondary_language'])
        if pair is None:
            return '', ''
        return ('' if self.config.get('display_mode') == 'secondary_only' else pair[0], pair[1])
