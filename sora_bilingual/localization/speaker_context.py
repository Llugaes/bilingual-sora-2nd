"""Resolve copied history by its retained speaker and complete dialogue text.

No neighbouring dialogue or current scene is used. A name narrows the resource
set only; same-speaker wording conflicts still use the normal admission gate.
"""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import struct

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.menu_text import (
    MenuTranslator,
    _without_line_padding,
    complete_pair,
    display_text,
)
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _logical_tables, _zutf8


def speaker_names(data):
    layout = sections(data)
    floor = max(start + size * count for _, start, size, count in layout)
    names = defaultdict(list)
    for kind, start, size, count in layout:
        if kind != "NameTableData":
            continue
        if size != 104:
            raise FormatError("Unexpected speaker name record stride")
        for number in range(count):
            at = start + number * size
            identity = struct.unpack_from("<I", data, at)[0]
            pointer = struct.unpack_from("<Q", data, at + 8)[0]
            if not floor <= pointer < len(data):
                raise FormatError("Speaker name outside pool")
            name, _ = _zutf8(data, pointer)
            if identity != 0xFFFF:
                names[identity].append(name)
    # Costume/entity variants may share an ID. Do not infer their actor state.
    return {
        identity: values[0] for identity, values in names.items() if len(values) == 1 and values[0]
    }


def read_speaker_names(game, language):
    with FpacArchive(Path(game) / "pac/steam" / archive_names("table")[language]) as archive:
        return speaker_names(archive.read(_logical_tables(archive)["table/t_name.tbl"]))


def compile_speaker_contexts(entries, names, primary, secondary, language, resolved_pairs=None):
    groups = defaultdict(list)
    for entry in entries:
        if entry.get("display_role") != "dialogue":
            continue
        ids = entry.get("speaker_ids", {})
        actor = ids.get(language)
        if actor not in names or any(ids.get(locale) != actor for locale in (primary, secondary)):
            continue
        source = entry["texts"].get(language)
        if not source or (resolved_pairs is not None and source in resolved_pairs):
            continue
        groups[names[actor]].append(entry)
    result = {}
    for name, records in groups.items():
        tr = MenuTranslator(records, primary, secondary, language, True)
        if tr.pairs:
            result[name] = {
                "pairs": tr.pairs,
                "plain_pairs": tr.plain_pairs,
                "ambiguous_display": sorted(tr.ambiguous_display),
                "same_language": tr.same_language,
            }
    return result


def _static_speaker_name_candidates(entries, primary, secondary):
    """Return complete target pairs for direct ``mes`` name setters.

    A generic display label is not necessarily present in ``t_name``: the
    announcement voice, for example, is a literal string in ``arg/1`` just
    before the dialogue calls.  History retains that literal but not its
    setter call ID.  We can therefore admit it only when every *physical*
    setter using the same source label agrees on one complete target pair.

    Alignment fragments for the same setter are not independent evidence.  A
    complete direct row dominates their missing-language fragment, while a
    different setter with the same label remains a real ambiguity.
    """

    def physical_setter(entry):
        key = entry.get("key", "").split("/alignment/", 1)[0]
        prefix, separator, suffix = key.partition("/called/")
        if not prefix or not separator:
            return None
        parts = suffix.split("/")
        if len(parts) != 3 or not parts[0].isdigit() or parts[1:] != ["arg", "1"]:
            return None
        return key

    physical_claims = defaultdict(lambda: defaultdict(set))
    for entry in entries:
        if entry.get("display_role") != "speaker":
            continue
        setter = physical_setter(entry)
        texts = entry.get("texts", {})
        values = {value for value in texts.values() if value and value.strip()}
        if setter is None or not values:
            continue
        pair = complete_pair(texts, primary, secondary)
        # Source-localized labels are a set, but their insertion order reaches
        # the shared history name index and its serialized fallback. Keep the
        # complete ambiguity set; stabilize only its traversal, not selection.
        for source in sorted(values):
            physical_claims[setter][source].add(pair)

    candidates = defaultdict(set)
    for claims in physical_claims.values():
        for source, pairs in claims.items():
            complete = {pair for pair in pairs if pair is not None}
            # A partial alignment row of this same raw setter is dominated by
            # its complete row.  Do not let it erase verified setter evidence.
            candidates[source].update(complete or {None})
    return candidates


def compile_history_contexts(entries, names_by_locale, primary, secondary):
    """Exact old-log lookup across source locales, with shared target pairs.

    This is only for records whose native history provenance was validated.
    It does not fabricate call IDs. True wording conflicts remain explicit,
    including collisions between different source locales.
    """
    texts, names = defaultdict(set), defaultdict(set)
    speakers = defaultdict(lambda: defaultdict(set))
    pending = defaultdict(list)
    selected = [entry for entry in entries if entry.get("display_role") == "dialogue"]
    # Equal resource payloads recur across source languages, partial alignment
    # rows and speaker buckets. Memoize only these pure normalizations within
    # this compilation; target decisions and ambiguities are never cached here.
    body_text = lru_cache(maxsize=16384)(display_text)

    @lru_cache(maxsize=16384)
    def padded_pair(pair):
        return tuple(_without_line_padding(value) for value in pair)

    def physical_call(entry, locale, body):
        key = entry.get("key", "").split("/alignment/", 1)[0]
        prefix, separator, suffix = key.partition("/called/")
        if separator and suffix.split("/", 1)[0].isdigit():
            ordinal = entry.get("called_ids", {}).get(locale, int(suffix.split("/", 1)[0]))
            return prefix, ordinal, locale, body
        return key or id(entry), locale, body

    # An incomplete record must not disappear from the ambiguity denominator.
    # Only a complete row for the same physical call may dominate its partial
    # alignment row; a different call with equal text is not that evidence.
    for entry in selected:
        if complete_pair(entry["texts"], primary, secondary):
            continue
        available = tuple(
            body_text(entry["texts"][locale]) if locale in entry["texts"] else None
            for locale in (primary, secondary)
        )
        for locale, value in entry["texts"].items():
            body = body_text(value)
            if not body.strip():
                continue
            actor = entry.get("speaker_ids", {}).get(locale)
            name = names_by_locale.get(locale, {}).get(actor)
            pending[physical_call(entry, locale, body)].append((body, name, available))

    for entry in selected:
        pair = complete_pair(entry["texts"], primary, secondary)
        if not pair:
            continue
        pair = tuple(body_text(value) for value in pair)
        for locale, value in entry["texts"].items():
            body = body_text(value)
            if not body.strip():
                continue
            texts[body].add(pair)
            actor = entry.get("speaker_ids", {}).get(locale)
            name = names_by_locale.get(locale, {}).get(actor)
            if name:
                speakers[name][body].add(pair)
            identity = physical_call(entry, locale, body)
            if identity in pending:
                pending[identity] = [
                    item
                    for item in pending[identity]
                    if any(
                        value is not None and value != pair[i] for i, value in enumerate(item[2])
                    )
                ]
    unknown_speakers = set()
    for claims in pending.values():
        for body, name, _ in claims:
            texts[body].add(None)
            if name:
                speakers[name][body].add(None)
            else:
                unknown_speakers.add(body)
    for locale_names in names_by_locale.values():
        for actor, name in locale_names.items():
            pair = tuple(
                names_by_locale.get(locale, {}).get(actor) for locale in (primary, secondary)
            )
            if all(pair):
                names[name].add(pair)
    for source, candidates in _static_speaker_name_candidates(entries, primary, secondary).items():
        names[source].update(candidates)

    pool, indices = [], {}

    def compact(candidates):
        result = {}
        for source, pairs in candidates.items():
            normalized = {padded_pair(pair) for pair in pairs if pair}
            if None in pairs or len(normalized) != 1:
                result[source] = -1
                continue
            pair = min(pairs, key=lambda value: (sum(map(len, value)), value))
            if pair not in indices:
                indices[pair] = len(pool)
                pool.append(pair)
            result[source] = indices[pair]
        return result

    def fallback(candidates):
        """Choose a deterministic complete pair without changing exact ambiguity."""
        result = {}
        for source, pairs in candidates.items():
            normalized = defaultdict(list)
            for pair in pairs:
                if pair is not None:
                    normalized[padded_pair(pair)].append(pair)
            if not normalized:
                continue
            key = min(normalized)
            pair = min(normalized[key], key=lambda value: (sum(map(len, value)), value))
            if pair not in indices:
                indices[pair] = len(pool)
                pool.append(pair)
            result[source] = indices[pair]
        return result

    shared = compact(texts)
    fallback_texts = fallback(
        {source: pairs for source, pairs in texts.items() if shared[source] < 0}
    )
    # Speaker maps only need to narrow global conflicts. Unique full bodies
    # already have one O(1) lookup and do not need eight duplicate actor maps.
    narrowed = {}
    fallback_speakers = {}
    for name, candidates in speakers.items():
        selected_candidates = {
            source: pairs | {None} if source in unknown_speakers else pairs
            for source, pairs in candidates.items()
            if shared[source] < 0
        }
        selected = compact(selected_candidates)
        if selected:
            narrowed[name] = selected
        selected_fallback = fallback(selected_candidates)
        if selected_fallback:
            fallback_speakers[name] = selected_fallback
    name_index = compact(names)
    fallback_names = fallback(
        {source: pairs for source, pairs in names.items() if name_index[source] < 0}
    )
    result = {
        "texts": shared,
        "speakers": narrowed,
        "names": name_index,
        "fallback_texts": fallback_texts,
        "fallback_speakers": fallback_speakers,
        "fallback_names": fallback_names,
        "pairs": pool,
        "same_language": primary == secondary,
    }
    return result
