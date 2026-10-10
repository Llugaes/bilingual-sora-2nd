"""Local resource/model cache. Never starts or attaches to the game."""

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from sora_bilingual.config.locales import DEFAULT_PRIMARY, archive_names
from sora_bilingual.localization.cache_io import publish_json, read_model

from sora_bilingual.paths import ROOT


def _resource_snapshot(game):
    result = []
    for path in sorted((Path(game) / "pac" / "steam").glob("*.pac")):
        if not path.name.startswith(("script", "table")):
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                after = path.stat()
        except FileNotFoundError as error:
            raise ResourceChangedError(
                [(path.name, stat.st_size, stat.st_mtime_ns)], [], "resource_content_read"
            ) from error
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ResourceChangedError(
                [(path.name, stat.st_size, stat.st_mtime_ns)],
                [(path.name, after.st_size, after.st_mtime_ns)],
                "resource_content_read",
            )
        result.append((path.name, stat.st_size, stat.st_mtime_ns, digest))
    return result


class ResourceChangedError(ValueError):
    reason = "resource_changed_during_preparation"

    def __init__(self, expected, actual, phase):
        self.phase = phase
        self.expected = [list(row) for row in expected]
        self.actual = [list(row) for row in actual]
        before = {row[0]: row[1:] for row in self.expected}
        after = {row[0]: row[1:] for row in self.actual}
        self.changed_files = sorted(
            name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
        )
        super().__init__(
            f"{self.reason}: {phase}: {', '.join(self.changed_files)}; "
            "准备期间游戏资源发生变化，本次模型未就绪；请在资源稳定后正常重试。"
        )


def _verify_resources(game, expected, phase):
    actual = _resource_snapshot(game)
    if [list(row) for row in expected] != [list(row) for row in actual]:
        raise ResourceChangedError(expected, actual, phase)


def _signature_resources(signature, game):
    # Production signatures contain the complete resource snapshot. Opaque
    # low-level fixture signatures still receive a before/after snapshot.
    try:
        stamp = json.loads(signature)
    except ValueError, TypeError:
        stamp = None
    return (
        stamp["resources"]
        if isinstance(stamp, dict) and "resources" in stamp
        else _resource_snapshot(game)
    )


def fingerprint(game, *, legacy=False):
    resources = _resource_snapshot(game)
    parser_code = b"".join(
        (ROOT / n).read_bytes()
        for n in (
            "sora_bilingual/localization/resources.py",
            "sora_bilingual/localization/control_dialogue.py",
            "sora_bilingual/localization/tables.py",
            "sora_bilingual/localization/menu_tables.py",
            "sora_bilingual/localization/table_alignment.py",
            "sora_bilingual/localization/catalog_build.py",
            "sora_bilingual/localization/dynamic_producers.py",
        )
    )
    # Presentation labels and first-run preferences cannot invalidate parsed game data.
    legacy_parser_code = parser_code + (ROOT / "sora_bilingual/config/locales.py").read_bytes()
    parser_code += json.dumps(
        [archive_names("script"), archive_names("table")], sort_keys=True
    ).encode()
    if legacy:
        parser_code = legacy_parser_code
    code = hashlib.sha256(
        parser_code
        + b"".join(
            (ROOT / n).read_bytes()
            for n in (
                "sora_bilingual/localization/menu_text.py",
                "sora_bilingual/localization/save_summary.py",
                "sora_bilingual/localization/annotation_breaks.py",
                "sora_bilingual/localization/annotation_break_data.json",
                "sora_bilingual/localization/native_catalog.py",
                "sora_bilingual/localization/language_cache.py",
                "sora_bilingual/localization/runtime_identity.py",
                "sora_bilingual/localization/item_help_headers.py",
                "sora_bilingual/localization/dynamic_identity.py",
                "sora_bilingual/localization/speaker_context.py",
                "sora_bilingual/localization/item_help_composition.py",
                "sora_bilingual/localization/npc_facilities.py",
                "sora_bilingual/localization/notebook_composition.py",
            )
        )
    ).hexdigest()
    return {
        "resources": resources,
        "code": code,
        "catalog_code": hashlib.sha256(parser_code).hexdigest(),
    }


def load_entries(game, output=ROOT / "generated"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    stamp = fingerprint(game)
    signature = json.dumps(stamp, sort_keys=True)
    catalog_signature = json.dumps(
        {"resources": stamp["resources"], "code": stamp["catalog_code"]}, sort_keys=True
    )
    manifest = output / "catalog-signature.json"
    catalog = output / "catalog.json"
    if (
        manifest.exists()
        and catalog.exists()
        and manifest.read_text(encoding="utf-8") != catalog_signature
    ):
        legacy = json.dumps(
            {
                "resources": stamp["resources"],
                "code": fingerprint(game, legacy=True)["catalog_code"],
            },
            sort_keys=True,
        )
        if manifest.read_text(encoding="utf-8") == legacy:
            manifest.write_text(catalog_signature, encoding="utf-8")
    if (
        not manifest.exists()
        or manifest.read_text(encoding="utf-8") != catalog_signature
        or not catalog.exists()
    ):
        # The UI uses fingerprint/model_path to schedule preparation. Keep the
        # compiler and script parser out of that long-lived polling process.
        from sora_bilingual.localization.catalog_build import build_all

        result = build_all(game, output)
        _verify_resources(game, stamp["resources"], "catalog_build")
        manifest.write_text(catalog_signature, encoding="utf-8")
        return result["entries"], signature
    entries = json.loads(catalog.read_text(encoding="utf-8"))["entries"]
    _verify_resources(game, stamp["resources"], "catalog_read")
    return entries, signature


def model_path(signature, config, output=ROOT / "generated"):
    identity = [
        signature,
        config["primary"],
        config["secondary"],
        config.get("game_language", DEFAULT_PRIMARY),
        config.get("scope", "all"),
        config.get("sources", []),
    ]
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
    return Path(output) / ("runtime-" + digest[:20] + ".json")


def ready_model(game, config, output=ROOT / "generated"):
    """Fast startup: a current model does not need the 500k-entry catalog."""
    signature = json.dumps(fingerprint(game), sort_keys=True)
    path = model_path(signature, config, output)
    cached = read_model(path)
    if cached is not None:
        _verify_resources(game, _signature_resources(signature, game), "model_read")
        return cached, signature, None
    entries, signature = load_entries(game, output)
    return load_model(entries, signature, config, output, game=game), signature, entries


def load_model(entries, signature, config, output=ROOT / "generated", *, game):
    from sora_bilingual.localization.language_cache import language_facts

    start = time.perf_counter()
    timings = {}
    resources = _signature_resources(signature, game)
    _verify_resources(game, resources, "model_input")
    try:
        with language_facts(output) as facts:
            model = _load_model(
                entries,
                signature,
                config,
                output,
                game=game,
                timings=timings,
                resource_snapshot=resources,
            )
    except ResourceChangedError:
        raise
    except Exception:
        # A resource replacement can first manifest as a strict raw/catalog
        # mismatch. Keep strict refusal, but report the changed generation.
        _verify_resources(game, resources, "model_compilation")
        raise
    publish_json(
        Path(output) / "model-preparation.json",
        {
            "primary": config["primary"],
            "secondary": config["secondary"],
            "game_language": config.get("game_language", DEFAULT_PRIMARY),
            "seconds": time.perf_counter() - start,
            "language_facts": facts.stats,
            "phases_seconds": timings,
        },
    )
    return model


def _load_model(
    entries, signature, config, output=ROOT / "generated", *, game, timings=None, resource_snapshot
):
    timings = {} if timings is None else timings
    start = time.perf_counter()
    path = model_path(signature, config, output)
    cached = read_model(path)
    timings["model_read"] = time.perf_counter() - start
    if cached is not None:
        _verify_resources(game, resource_snapshot, "model_read")
        return cached
    from sora_bilingual.localization.menu_text import MenuTranslator

    start = time.perf_counter()
    selected = entries
    if config.get("scope") == "menu":
        selected = [e for e in entries if e.get("key", "").startswith("table/")]
    if config.get("scope") == "selected":
        sources = set(config.get("sources", []))
        lang = config.get("game_language", DEFAULT_PRIMARY)
        selected = [e for e in entries if e["texts"].get(lang) in sources]
    grammar = None
    if config.get("scope", "all") != "selected" and any(
        e.get("key", "").startswith("table/t_itemhelp.tbl/SkillEffectHelpData/") for e in selected
    ):
        from sora_bilingual.localization.item_help_composition import build_item_help_grammar

        source = config.get("game_language", DEFAULT_PRIMARY)
        grammar = build_item_help_grammar(
            game, selected, source, languages=(source, config["primary"], config["secondary"])
        )
    from sora_bilingual.localization.npc_facilities import compile_npc_facilities

    facility_entries = compile_npc_facilities(
        game,
        selected,
        (config.get("game_language", DEFAULT_PRIMARY), config["primary"], config["secondary"]),
    )
    from sora_bilingual.localization.item_help_headers import compile_item_help_headers

    item_headers = (
        compile_item_help_headers(
            game,
            selected,
            config["primary"],
            config["secondary"],
            config.get("game_language", DEFAULT_PRIMARY),
        )
        if grammar
        else {}
    )
    from sora_bilingual.localization.notebook_composition import (
        compile_fishing_lists,
        compile_bracer_history,
    )

    notebook_entries = (
        compile_fishing_lists(
            game,
            selected,
            (config.get("game_language", DEFAULT_PRIMARY), config["primary"], config["secondary"]),
        )
        if config.get("scope", "all") != "selected"
        else []
    )
    history_entries = (
        compile_bracer_history(
            game,
            selected,
            (config.get("game_language", DEFAULT_PRIMARY), config["primary"], config["secondary"]),
            config.get("game_language", DEFAULT_PRIMARY),
        )
        if config.get("scope", "all") != "selected"
        else []
    )
    translator = MenuTranslator(
        selected
        + facility_entries
        + notebook_entries
        + history_entries
        + (grammar["status_entries"] + grammar["detail_entries"] if grammar else []),
        config["primary"],
        config["secondary"],
        config.get("game_language", DEFAULT_PRIMARY),
        item_help_headers=item_headers,
    )
    model = translator.runtime_model()
    timings["combination_mapping"] = time.perf_counter() - start
    start = time.perf_counter()
    source = config.get("game_language", DEFAULT_PRIMARY)
    model["books"] = {
        str(entry["book_id"]): {
            "source": entry["book_pages"][source],
            "primary": entry["book_pages"][config["primary"]],
            "secondary": entry["book_pages"][config["secondary"]],
        }
        for entry in selected
        if "book_pages" in entry
        and all(
            language in entry["book_pages"]
            for language in (source, config["primary"], config["secondary"])
        )
    }
    if grammar:
        model["item_help_audit"] = grammar["audit"]
    coverage = Counter()
    source = config.get("game_language", DEFAULT_PRIMARY)
    for entry in selected:
        texts = entry["texts"]
        if not texts.get(source, "").strip():
            continue
        coverage["source_records"] += 1
        missing = [
            side for side in ("primary", "secondary") if not texts.get(config[side], "").strip()
        ]
        for side in missing:
            coverage["missing_" + side] += 1
        if not missing:
            coverage["complete_pair_records"] += 1
    model["coverage"] = dict(coverage)
    timings["coverage_books"] = time.perf_counter() - start
    if config.get("scope", "all") != "selected" and not coverage["complete_pair_records"]:
        raise ValueError(
            "本地资源没有所选源语言、主语言和副语言的可用配对；请检查资源与源语言设置。"
        )
    from sora_bilingual.localization.runtime_identity import (
        compile_script_identities,
        compile_table_identities,
    )

    args = (
        game,
        selected,
        config["primary"],
        config["secondary"],
        config.get("game_language", DEFAULT_PRIMARY),
    )
    start = time.perf_counter()
    model["script_identities"] = compile_script_identities(*args, resolved_pairs=translator.pairs)
    timings["script_identity_history"] = time.perf_counter() - start
    start = time.perf_counter()
    model["table_identities"] = compile_table_identities(*args, resolved_pairs=translator.pairs)
    timings["table_identity"] = time.perf_counter() - start
    from sora_bilingual.localization.speaker_context import (
        compile_history_contexts,
        compile_speaker_contexts,
        read_speaker_names,
    )

    start = time.perf_counter()
    names_by_locale = {
        locale: read_speaker_names(game, locale)
        for locale, archive in archive_names("table").items()
        if any(e.get("speaker_ids") for e in selected)
        and (Path(game) / "pac/steam" / archive).exists()
    }
    model["speaker_contexts"] = compile_speaker_contexts(
        selected,
        names_by_locale.get(source, {}),
        config["primary"],
        config["secondary"],
        source,
        translator.pairs,
    )
    model["history_contexts"] = compile_history_contexts(
        selected, names_by_locale, config["primary"], config["secondary"]
    )
    timings["speaker_history_mapping"] = time.perf_counter() - start
    start = time.perf_counter()
    _verify_resources(game, resource_snapshot, "model_publication")
    publish_json(path, model)
    _verify_resources(game, resource_snapshot, "model_publication")
    timings["model_publication"] = time.perf_counter() - start
    return model


if __name__ == "__main__":
    import argparse, time

    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", required=True, type=Path)
    args = parser.parse_args()
    start = time.perf_counter()
    entries, signature = load_entries(args.game_dir)
    from sora_bilingual.config.native_config import read_config

    model = load_model(entries, signature, read_config(), game=args.game_dir)
    print(
        json.dumps(
            {
                "entries": len(entries),
                "exact_sources": len(model["pairs"]),
                "seconds": round(time.perf_counter() - start, 2),
            }
        )
    )
