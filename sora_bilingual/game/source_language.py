"""Read the game's active text-table language without installing hooks.

The executable report supplies the only accepted runtime address.  Language
names from Steam, Windows, or user settings are intentionally not inputs here.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import threading
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
    detail: str = ""


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
    unknown = []
    ambiguous = []
    for key, value in values.items():
        if key not in expected or not isinstance(value, str):
            continue
        candidates = [
            language
            for language, expected_value in zip(LANGUAGES, expected[key])
            if value == expected_value
        ]
        if not candidates:
            unknown.append(key)
            continue
        if len(candidates) != 1:
            ambiguous.append(key)
            continue
        votes.append(candidates[0])
        matched.append(key)
    if len(set(votes)) > 1:
        return SourceLanguageResult(None, "inconsistent_samples", tuple(matched))
    if len(votes) >= MIN_MATCHES:
        return SourceLanguageResult(votes[0], "matched", tuple(matched))
    # A modified or ambiguous sample must remain visible when there is no
    # independent threshold-sized agreement.  Once three keys do agree, it is
    # unrelated noise and must not override that result.
    if ambiguous:
        return SourceLanguageResult(None, "ambiguous_value", tuple(matched))
    if unknown:
        return SourceLanguageResult(None, "unknown_value", tuple(matched))
    return SourceLanguageResult(None, "insufficient_samples", tuple(matched))


def _probe_source(global_rva, keys):
    """A short one-shot Frida RPC; it installs no Interceptor or NativeFunction."""
    return (
        "const GLOBAL="
        + json.dumps(global_rva)
        + ";const KEYS=new Set("
        + json.dumps(keys)
        + ");const MIN_MATCHES="
        + json.dumps(MIN_MATCHES)
        + ";rpc.exports={read(){try{"
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
        + "return Object.keys(values).length>=MIN_MATCHES?{state:'ready',values:values}:{state:'unready'};"
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


def detect_current_language(game, pid, exe=None, *, report=None, attach=None, read_values=None):
    """Identify the live table's source language, failing closed at every boundary."""
    try:
        references = load_references(game)
    except (OSError, FormatError, ValueError) as exc:
        return SourceLanguageResult(None, "source_unavailable", detail=str(exc))
    if report is None:
        try:
            report = native_report(exe)
        except OSError as exc:
            return SourceLanguageResult(None, "exe_unreadable", detail=str(exc))
        except ValueError as exc:
            return SourceLanguageResult(None, "unverified_exe", detail=str(exc))
    try:
        values = (
            read_values(report, references.keys)
            if read_values is not None
            else read_runtime_values(pid, report, references.keys, attach=attach)
        )
    except Exception as exc:
        return SourceLanguageResult(None, "probe_unavailable", detail=str(exc))
    if values is None:
        return SourceLanguageResult(None, "table_unready")
    return classify_runtime_values(references, values)


class RuntimeTextTableReader:
    """Read the verified TXT table outside the game; cache only checked row addresses."""

    def __init__(self, pid, exe, *, opener=None):
        self.pid, self.exe, self.opener = pid, exe, opener
        self.memory = None
        self.signature = None
        self.rows = {}

    def close(self):
        if self.memory is not None:
            self.memory.close()
            self.memory = None
        self.signature, self.rows = None, {}

    def _pointer(self, address):
        return struct.unpack("<Q", self.memory.read(address, 8))[0]

    def _header(self, rva):
        manager = self._pointer(self.memory.base + rva)
        table = self._pointer(manager + 0x6B8) if manager else 0
        if not table:
            return None
        header = self.memory.read(table + 0x10, 0x24)
        data, descriptor, index = (struct.unpack_from("<Q", header, n)[0] for n in (0, 16, 24))
        count = struct.unpack_from("<I", header, 32)[0]
        if not all((data, descriptor, index)) or not 0 < count <= 20000:
            return None
        start, stride = struct.unpack("<II", self.memory.read(descriptor + 0x44, 8))
        if stride != 16:
            return None
        return manager, table, data, descriptor, index, count, start, stride

    def _discover(self, header, keys):
        _, _, data, _, index, count, start, stride = header
        indices = struct.iter_unpack("<II", self.memory.read(index, count * 8))
        numbers, seen = [], set()
        for hash_value, number in indices:
            if number == 0xFFFFFFFF:
                continue
            if number >= count or hash_value in seen:
                raise ValueError("invalid TXT table index")
            seen.add(hash_value)
            numbers.append(number)
        records = self.memory.read(data + start, count * stride)
        rows = {}
        for number in numbers:
            key_pointer = struct.unpack_from("<Q", records, number * stride)[0]
            key = self.memory.text(key_pointer, 257)
            if not key.startswith("TXT_"):
                raise ValueError("invalid TXT table key")
            if key in keys:
                if key in rows:
                    raise ValueError("duplicate source-language sample")
                rows[key] = data + start + number * stride
        return rows

    def read(self, report, keys):
        rva = report.get("text_table_global")
        if not isinstance(rva, int) or rva < 0:
            return None
        if self.memory is None:
            from sora_bilingual.platform.process_memory import ReadOnlyProcess

            self.memory = (self.opener or ReadOnlyProcess)(self.pid, self.exe)
        try:
            header = self._header(rva)
            if header is None:
                self.signature, self.rows = None, {}
                return None
            signature = header, tuple(keys)
            if self.signature != signature:
                self.rows = self._discover(header, keys)
                # During reload the index can fill in-place without a new
                # header. Do not permanently cache a partial set of samples.
                self.signature = signature if len(self.rows) == len(keys) else None
            values = {}
            for key, record in self.rows.items():
                key_ptr, value_ptr = struct.unpack("<QQ", self.memory.read(record, 16))
                if self.memory.text(key_ptr, 257) != key:
                    # A table can reuse the same buffers with reordered rows.
                    self.signature = None
                    return None
                values[key] = self.memory.text(value_ptr, 65537)
            if header != self._header(rva):
                self.signature = None
                return None
            return values if len(values) >= MIN_MATCHES else None
        except OSError, ValueError:
            self.signature, self.rows = None, {}
            raise  # Preserve access/format failures instead of calling them initialization.


class SourceLanguageMonitor:
    """One bounded read per interval, off the input loop and the game's threads."""

    def __init__(self, sample, close, *, interval=1.0):
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None

        def run():
            try:
                while not self.stop.is_set():
                    try:
                        result = sample()
                    except Exception as exc:
                        result = SourceLanguageResult(None, "probe_unavailable", detail=str(exc))
                    with self.lock:
                        self.latest = result
                    self.stop.wait(interval)
            finally:
                close()

        self.thread = threading.Thread(target=run, name="source-language", daemon=True)
        self.thread.start()

    def poll(self):
        with self.lock:
            value, self.latest = self.latest, None
        return value

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("来源语言检测尚未退出")
