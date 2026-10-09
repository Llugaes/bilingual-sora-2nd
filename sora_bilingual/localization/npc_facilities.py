"""Complete NPC facility labels from validated SCP configuration calls.

The NPC facility builder copies chr_set_shop_function's complete name argument
between <c990> and </c>. Map/place homonyms are a separate resource domain.
Neither the colour nor a fragment of a configured name grants this contract.
"""

from collections import defaultdict
from contextlib import ExitStack
import hashlib
from pathlib import Path

from sora_bilingual.localization.resources import (
    FpacArchive,
    _ARCHIVES,
    _logical_script_entries,
    parse_scp,
)
from sora_bilingual.localization.language_cache import notification_metadata


def compile_npc_facilities(game, entries, languages):
    languages = tuple(dict.fromkeys(languages))
    paths = defaultdict(list)
    for entry in entries:
        key = entry.get("key", "").split("/alignment/", 1)[0]
        if not key.startswith("script/") or ".dat/" not in key or not key.endswith("/arg/2"):
            continue
        path, rest = key.split(".dat/", 1)
        if "/called/" not in rest:
            continue
        function, called = rest.rsplit("/called/", 1)
        index = called.split("/", 1)[0]
        if index.isdecimal():
            paths[path + ".dat"].append((entry, function, int(index)))
    result = []
    with ExitStack() as stack:
        archives = {
            language: stack.enter_context(
                FpacArchive(Path(game) / "pac/steam" / _ARCHIVES[language])
            )
            for language in languages
        }
        logical = {
            language: _logical_script_entries(archive) for language, archive in archives.items()
        }
        for path, candidates in sorted(paths.items()):
            if any(path not in logical[language] for language in languages):
                continue
            source = languages[0]
            source_data = archives[source].read(logical[source][path])
            metadata = notification_metadata(source_data, source)
            candidates = [
                (entry, function, canonical)
                for entry, function, canonical in candidates
                if (record := metadata.get(function)) is not None
                and "chr_set_shop_function" in record.call_targets
            ]
            if not candidates:
                continue
            data = {
                language: (
                    source_data
                    if language == source
                    else archives[language].read(logical[language][path])
                )
                for language in languages
            }
            scripts = {language: parse_scp(raw) for language, raw in data.items()}
            for entry, function, canonical in candidates:
                calls = []
                for language in languages:
                    record = scripts[language].functions.get(function)
                    index = entry.get("called_ids", {}).get(language, canonical)
                    if (
                        record is None
                        or not isinstance(index, int)
                        or not 0 <= index < len(record.called)
                    ):
                        break
                    call = record.called[index]
                    if (
                        call.target != "chr_set_shop_function"
                        or tuple(kind for kind, _ in call.args)
                        != ("int", "string", "string", "string")
                        or call.args[2][1] != entry.get("texts", {}).get(language)
                        or not call.args[2][1].strip()
                        or any(c in call.args[2][1] for c in "<>\r\n")
                    ):
                        break
                    calls.append(call)
                if (
                    len(calls) != len(languages)
                    or len({(c.args[0], c.args[1]) for c in calls}) != 1
                ):
                    continue
                result.append(
                    {
                        "key": entry["key"] + "/generated/npc_facility",
                        "texts": {
                            language: "<c990>" + entry["texts"][language] + "</c>"
                            for language in languages
                        },
                        "npc_facility_contract": {
                            "callee": "chr_set_shop_function",
                            "argument": 2,
                            "source_key": entry["key"],
                            "scripts": {
                                language: hashlib.sha256(raw).hexdigest()
                                for language, raw in data.items()
                            },
                        },
                    }
                )
    return result
