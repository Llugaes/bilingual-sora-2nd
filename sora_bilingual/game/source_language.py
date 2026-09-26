"""Read the game's active text-table language without installing hooks.

The executable report supplies the only accepted runtime address.  Language
names from Steam, Windows, or user settings are intentionally not inputs here.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import time

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.game.native_runtime import native_report
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables, _text_rows


SAMPLE_KEYS = 4
MIN_MATCHES = 3
_REFERENCE_CACHE = {}


@dataclass(frozen=True)
class SourceLanguageReferences:
    """Immutable values for a small, discriminating TXT_* key set."""

    keys: tuple[str, ...]
    values: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class SourceLanguageResult:
    language: str | None
    reason: str
    matched_keys: tuple[str, ...] = ()


def _archive_stamp(game):
    root = Path(game).resolve()
    result = []
    for language in LANGUAGES:
        path = root / "pac" / "steam" / _TABLE_ARCHIVES[language]
        stat = path.stat()
        result.append((language, str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(result)


def _read_text_table(path):
    with FpacArchive(path) as archive:
        logical = _logical_tables(archive)
        try:
            actual = logical["table/t_text.tbl"]
        except KeyError as exc:
            raise FormatError(f"{path.name}: missing table/t_text.tbl") from exc
        return _text_rows(archive.read(actual))


def load_references(game):
    """Load compact source signatures, reusing them while the eight PACs match."""
    stamp = _archive_stamp(game)
    cached = _REFERENCE_CACHE.get(stamp)
    if cached is not None:
        return cached
    rows = {language: _read_text_table(Path(path)) for language, path, _size, _mtime in stamp}
    shared = set.intersection(*(set(values) for values in rows.values()))
    candidates = [
        key
        for key in sorted(shared)
        if key.startswith("TXT_")
        and all(rows[language][key].strip() for language in LANGUAGES)
        and len({rows[language][key] for language in LANGUAGES}) == len(LANGUAGES)
    ]
    if len(candidates) < SAMPLE_KEYS:
        raise ValueError("insufficient distinct TXT_* keys for source-language detection")
    keys = tuple(candidates[:SAMPLE_KEYS])
    reference = SourceLanguageReferences(
        keys,
        tuple((key, tuple(rows[language][key] for language in LANGUAGES)) for key in keys),
    )
    _REFERENCE_CACHE.clear()
    _REFERENCE_CACHE[stamp] = reference
    return reference


def classify_runtime_values(references, values):
    """Accept only one language with three or more independently matching keys."""
    expected = dict(references.values)
    votes = []
    matched = []
    for key, value in values.items():
        if key not in expected or not isinstance(value, str):
            continue
        candidates = [
            language
            for language, expected_value in zip(LANGUAGES, expected[key])
            if value == expected_value
        ]
        if not candidates:
            return SourceLanguageResult(None, "unknown_value")
        if len(candidates) != 1:
            return SourceLanguageResult(None, "ambiguous_value")
        votes.append(candidates[0])
        matched.append(key)
    if len(votes) < MIN_MATCHES:
        return SourceLanguageResult(None, "insufficient_samples", tuple(matched))
    if len(set(votes)) != 1:
        return SourceLanguageResult(None, "inconsistent_samples", tuple(matched))
    return SourceLanguageResult(votes[0], "matched", tuple(matched))


def _probe_source(global_rva, keys):
    """A short one-shot Frida RPC; it installs no Interceptor or NativeFunction."""
    return (
        "const GLOBAL="
        + json.dumps(global_rva)
        + ";const KEYS=new Set("
        + json.dumps(keys)
        + ");rpc.exports={read(){try{"
        + "const base=Process.getModuleByName('sora_2nd.exe').base;"
        + "const manager=base.add(GLOBAL).readPointer();if(manager.isNull())return {state:'unready'};"
        + "const table=manager.add(0x6b8).readPointer();if(table.isNull())return {state:'unready'};"
        + "const data=table.add(0x10).readPointer(),descriptor=table.add(0x20).readPointer(),"
        + "index=table.add(0x28).readPointer(),count=table.add(0x30).readU32();"
        + "if(!count||count>20000||data.isNull()||descriptor.isNull()||index.isNull())return {state:'unready'};"
        + "const start=descriptor.add(0x44).readU32(),stride=descriptor.add(0x48).readU32();"
        + "if(stride!==16)return {state:'unready'};const seen=new Set(),values={};"
        + "for(let i=0;i<count;i++){const entry=index.add(i*8),hash=entry.readU32(),number=entry.add(4).readU32();"
        + "if(number===0xffffffff)continue;if(number>=count||seen.has(hash))return {state:'unready'};seen.add(hash);"
        + "const record=data.add(start+number*stride),key=record.readPointer().readUtf8String();"
        + "if(!key.startsWith('TXT_')||key.length>256)return {state:'unready'};"
        + "if(KEYS.has(key)){const value=record.add(8).readPointer().readUtf8String();"
        + "if(value.length>16384)return {state:'unready'};values[key]=value;}}"
        + "return Object.keys(values).length===KEYS.size?{state:'ready',values:values}:{state:'unready'};"
        + "}catch(e){return {state:'unready'}}}};"
    )


def read_runtime_values(pid, report, keys, *, attach=None, wait_seconds=5, sleep=time.sleep):
    """Read selected values, briefly waiting for the table in one no-hook session."""
    global_rva = report.get("text_table_global")
    if not isinstance(global_rva, int) or global_rva < 0:
        return None
    if attach is None:
        import frida

        attach = frida.attach
    session = attach(pid)
    script = None
    try:
        script = session.create_script(_probe_source(global_rva, keys), runtime="v8")
        script.load()
        deadline = time.monotonic() + max(0, wait_seconds)
        while True:
            result = script.exports_sync.read()
            if result.get("state") == "ready" and isinstance(result.get("values"), dict):
                return result["values"]
            if time.monotonic() >= deadline:
                return None
            sleep(min(0.2, max(0, deadline - time.monotonic())))
    finally:
        if script is not None:
            script.unload()
        session.detach()


def detect_current_language(game, pid, exe=None, *, report=None, attach=None):
    """Identify the live table's source language, failing closed at every boundary."""
    try:
        references = load_references(game)
    except OSError, FormatError, ValueError:
        return SourceLanguageResult(None, "source_unavailable")
    if report is None:
        try:
            report = native_report(exe)
        except OSError, ValueError:
            return SourceLanguageResult(None, "unverified_exe")
    try:
        values = read_runtime_values(pid, report, references.keys, attach=attach)
    except Exception:
        return SourceLanguageResult(None, "probe_unavailable")
    if values is None:
        return SourceLanguageResult(None, "table_unready")
    return classify_runtime_values(references, values)
