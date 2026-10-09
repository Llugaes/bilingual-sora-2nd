"""Display-only constructors for the strict, ancestry-bound save surface.

All source strings come from resource chapter/name/party/difficulty fields.
The resource difficulty enum captions are localized here for display; the saved
bytes and the locale recorded by the game are never read or changed.
"""

DIFFICULTY_CAPTIONS = {
    "VERY_EASY": {"ja": "ベリーイージー", "zh-Hans": "极易", "zh-Hant": "極易"},
    "EASY": {"ja": "イージー", "zh-Hans": "简单", "zh-Hant": "簡單"},
    "NORMAL": {"ja": "ノーマル", "zh-Hans": "普通", "zh-Hant": "普通"},
    "ADVANCED": {"ja": "アドバンス", "zh-Hans": "进阶", "zh-Hant": "進階"},
    "HARD": {"ja": "ハード", "zh-Hans": "困难", "zh-Hant": "困難"},
    "NIGHTMARE": {"ja": "ナイトメア", "zh-Hans": "噩梦", "zh-Hant": "噩夢"},
}

PLAYTIME_CAPTIONS = {
    "ja": "プレイ時間",
    "zh-Hans": "游玩时间",
    "zh-Hant": "遊玩時間",
}


def save_display_constructors(entries, source_language):
    catalogue = {e.get("key", ""): e for e in entries}
    result, difficulties = [], []
    # All four verified native resources call this caption "  Playtime".
    # Like difficulty captions, localize only its display on the save surface.
    # The clock itself is data and is left to the existing component splitter.
    raw = catalogue.get("table/t_text.tbl/TXT_SAVE_DETAIL_PLAYTIME", {}).get("texts", {})
    if source_language in raw:
        for indent in (True, False):
            texts = {}
            sources = set()
            for language, value in raw.items():
                if not value:
                    continue
                padding = value[: len(value) - len(value.lstrip())] if indent else ""
                sources.add(value if indent else value.lstrip())
                texts[language] = padding + PLAYTIME_CAPTIONS.get(language, value.lstrip())
            result.append(
                {
                    "key": "table/t_save_generated/playtime/" + str(indent),
                    "texts": texts,
                    "source_variants": {source_language: sorted(sources)},
                }
            )
    for code, captions in DIFFICULTY_CAPTIONS.items():
        key = "table/t_text.tbl/TXT_SAVE_" + code
        raw = catalogue.get(key, {}).get("texts", {})
        if not raw or source_language not in raw:
            continue
        texts = {}
        for language, value in raw.items():
            # Resource-owned brackets and padding remain part of the caption.
            caption = captions.get(language)
            if caption and "＜" in value and value.endswith("＞"):
                value = value[: value.index("＜") + 1] + caption + "＞"
            texts[language] = value
        variants = sorted({v for v in raw.values() if v} | {v.lstrip() for v in raw.values() if v})
        result.append(
            {
                "key": "table/t_save_generated/difficulty/" + code,
                "texts": texts,
                "source_variants": {source_language: variants},
            }
        )
        difficulties.append((code, raw, texts))
    for entry in entries:
        key, raw = entry.get("key", ""), entry.get("texts", {})
        if key.startswith("table/t_chapter.tbl/") and key.endswith(("/title", "/heading")):
            for code, difficulty_raw, difficulty_texts in difficulties:
                languages = raw.keys() & difficulty_raw.keys()
                result.append(
                    {
                        "key": "table/t_save_generated/chapter/" + key + "/" + code,
                        "texts": {l: raw[l] + difficulty_texts[l] for l in languages},
                        # Saved chapter/name text may use the locale
                        # at write time while the live formatter's
                        # prefix/badge uses the current UI locale.
                        "source_variants": {
                            source_language: sorted(
                                {
                                    chapter + badge
                                    for chapter in raw.values()
                                    for badge in difficulty_raw.values()
                                    if chapter and badge
                                }
                            )
                        },
                    }
                )
        if key.startswith("table/t_name.tbl/") and key.endswith("/name"):
            prefix = catalogue.get("table/t_text.tbl/TXT_SAVE_DETAIL_PARTY_HEADER", {}).get(
                "texts", {}
            )
            languages = raw.keys() & prefix.keys()
            for indent in (True, False):
                heads = {l: prefix[l] if indent else prefix[l].lstrip() for l in languages}
                texts = {l: heads[l] + raw[l] for l in languages}
                if source_language in texts:
                    result.append(
                        {
                            "key": "table/t_save_generated/party/" + key + "/" + str(indent),
                            "texts": texts,
                            "source_variants": {
                                source_language: sorted(
                                    {
                                        head + name
                                        for head in heads.values()
                                        for name in raw.values()
                                        if name
                                    }
                                )
                            },
                        }
                    )
    return result
