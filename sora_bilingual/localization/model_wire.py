"""Lossless shared-node transport cache; no locale-specific pruning."""

import hashlib
import json
import re
import struct
import tempfile
from pathlib import Path
from sora_bilingual.config.native_config import replace_file
from sora_bilingual.localization.cache_io import publish_json


SCHEMA = 2


def pack_model(model):
    nodes, seen = [], {}

    def intern(value):
        if isinstance(value, dict):
            refs = tuple(ref for key, item in value.items() for ref in (intern(key), intern(item)))
            identity, node = ("object", refs), [1, *refs]
        elif isinstance(value, (tuple, list)):
            refs = tuple(map(intern, value))
            identity, node = ("array", refs), [0, *refs]
        elif value is None or isinstance(value, (str, bool, int, float)):
            identity, node = (type(value), value), value
        else:
            raise TypeError("Unsupported transport value")
        if identity not in seen:
            seen[identity] = len(nodes)
            nodes.append(node)
        return seen[identity]

    try:
        root = intern(model)
    finally:
        # Recursive closures otherwise retain the whole intern table until GC.
        intern = None
    return {"schema": 1, "root": root, "nodes": nodes}


def _indexed_parts(model):
    """Keep the complete DAG outside V8's traced heap; decode only used nodes.

    Objects carry an insertion-order entry table and a collision-checked hash
    index. All references point backwards, so readers can validate the entire
    file without constructing its object graph. Strings are UTF-16 code units,
    matching JS keys (including astral characters and embedded NULs).
    """
    # Paragraph builders need candidates by first line, not a scan/materialized
    # copy of every translation at connection time. Eligibility remains JS's
    # responsibility; this index excludes no multiline source or translation.
    paragraphs = {}
    for source in model.get("pairs", {}):
        parts = re.split(r"\r\n|\n|\\n", source, maxsplit=1)
        if len(parts) > 1:
            paragraphs.setdefault(parts[0], []).append(source)
    table, data = bytearray(), bytearray()
    # Keep one deduplication key per value, not a second full node graph.
    # Separate types retain pack_model's bool/int/float and object/array rules.
    seen = {kind: {} for kind in ("object", "array", str, bool, int, float, type(None))}
    hashes = {}
    node_count = 0

    def key_hash(node_id, key):
        if node_id not in hashes:
            value = 2166136261
            for (unit,) in struct.iter_unpack("<H", key.encode("utf-16-le", "surrogatepass")):
                value = ((value ^ unit) * 16777619) & 0xFFFFFFFF
            hashes[node_id] = value
        return hashes[node_id]

    def intern(value):
        nonlocal node_count
        if isinstance(value, dict):
            refs = tuple(ref for key, item in value.items() for ref in (intern(key), intern(item)))
            cache, identity, kind = seen["object"], refs, 5
        elif isinstance(value, (tuple, list)):
            refs = tuple(map(intern, value))
            cache, identity, kind = seen["array"], refs, 4
        elif value is None or isinstance(value, (str, bool, int, float)):
            cache = seen.get(type(value))
            if cache is None:
                cache = seen[type(value)] = {}
            identity = value
            kind = (
                0
                if value is None
                else 1
                if isinstance(value, bool)
                else 3
                if isinstance(value, str)
                else 2
            )
        else:
            raise TypeError("Unsupported transport value")
        if identity in cache:
            return cache[identity]
        index = node_count
        node_count += 1
        cache[identity] = index
        while len(data) % 4:
            data.append(0)
        offset, count = len(data), 0
        if kind == 1:
            count = int(value)
        elif kind == 2:
            data.extend(struct.pack("<d", value))
        elif kind == 3:
            encoded = value.encode("utf-16-le", "surrogatepass")
            count = len(encoded) // 2
            data.extend(encoded)
        elif kind == 4:
            count = len(refs)
            data.extend(struct.pack(f"<{count}I", *refs))
        elif kind == 5:
            count = len(refs) // 2
            data.extend(struct.pack(f"<{count * 2}I", *refs))
            order = sorted(
                (key_hash(refs[entry * 2], key), entry) for entry, key in enumerate(value)
            )
            data.extend(struct.pack(f"<{count * 2}I", *(item for pair in order for item in pair)))
        table.extend(struct.pack("<4I", kind, count, offset, len(data) - offset))
        return index

    try:
        root = intern({**model, "paragraph_sources": paragraphs})
    finally:
        intern = None
    data_offset = 32 + len(table)
    header = struct.pack(
        "<8s6I", b"SORAMOD2", SCHEMA, node_count, root, 32, data_offset, data_offset + len(data)
    )
    return header, table, data


def indexed_model(model):
    """Compatibility byte-buffer entry point for the complete indexed file."""
    header, table, data = _indexed_parts(model)
    return header + table + data


def publish_indexed(path, model):
    parts = _indexed_parts(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, suffix=".tmp", delete=False) as out:
        temporary = Path(out.name)
        try:
            for part in parts:
                out.write(part)
        except Exception:
            out.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def wire_path(model_path, schema=SCHEMA):
    return Path(model_path).with_suffix(".wire.bin" if schema == SCHEMA else ".wire.json")


def wire_ready(model_path):
    source = Path(model_path)
    target = wire_path(source)
    try:
        saved = json.loads(target.with_name(target.name + ".stamp.json").read_text("utf-8"))
        return (
            saved["source"]
            == {"schema": SCHEMA, "size": source.stat().st_size, "mtime": source.stat().st_mtime_ns}
            and target.stat().st_size == saved["size"]
        )
    except PermissionError:
        # Inaccessible transport artifacts are not a missing cache. Report the
        # original error instead of scheduling preparation against denied data.
        raise
    except OSError, ValueError, KeyError, TypeError:
        return False


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepared_summary(model_path):
    """Return only metadata from a verified preparation; never trust stat alone."""
    source = Path(model_path)
    target = wire_path(source)
    try:
        saved = json.loads(target.with_name(target.name + ".stamp.json").read_text("utf-8"))
        summary = saved["summary"]
        if (
            not isinstance(summary, dict)
            or set(summary) != {"coverage", "pair_count"}
            or not isinstance(summary["coverage"], dict)
            or type(summary["pair_count"]) is not int
            or summary["pair_count"] < 0
            or any(type(n) is not int or n < 0 for n in summary["coverage"].values())
        ):
            return None
        before = source.stat(), target.stat()
        if (
            saved["source"]
            != {"schema": SCHEMA, "size": before[0].st_size, "mtime": before[0].st_mtime_ns}
            or before[1].st_size != saved["size"]
            or _digest(source) != saved["source_sha256"]
            or _digest(target) != saved["sha256"]
        ):
            return None
        after = source.stat(), target.stat()
        if any(
            (a.st_size, a.st_mtime_ns) != (b.st_size, b.st_mtime_ns) for a, b in zip(before, after)
        ):
            return None
        return summary
    except PermissionError:
        raise
    except OSError, ValueError, KeyError, TypeError:
        return None


def prepare_wire(model_path, model=None, *, schema=SCHEMA):
    if schema not in (1, SCHEMA):
        raise ValueError("Unsupported model wire schema")
    source = Path(model_path)
    target = wire_path(source, schema)
    stamp = (
        target.with_name(target.name + ".stamp.json")
        if schema == SCHEMA
        else target.with_suffix(".stamp.json")
    )
    identity = {"schema": schema, "size": source.stat().st_size, "mtime": source.stat().st_mtime_ns}
    source_digest = _digest(source)
    try:
        saved = json.loads(stamp.read_text("utf-8"))
        if (
            saved["source"] == identity
            and saved.get("source_sha256") == source_digest
            and target.stat().st_size == saved["size"]
        ):
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == saved.get("sha256"):
                    return target
    except PermissionError:
        # Keep both wire schemas fail-closed: never rebuild/overwrite an
        # inaccessible stamp or payload, even when a model is already supplied.
        raise
    except OSError, ValueError, KeyError, TypeError:
        pass
    if model is None:
        from sora_bilingual.localization.cache_io import read_model

        model = read_model(source)
        if model is None:
            raise ValueError("Invalid source model")
    if schema == SCHEMA:
        publish_indexed(target, model)
    else:
        # Old game-owned scripts keep their connection until the next launch.
        publish_json(target, pack_model(model))
    digest = _digest(target)
    if source_digest != _digest(source):
        raise ValueError("Source model changed during transport preparation")
    metadata = {
        "source": identity,
        "source_sha256": source_digest,
        "size": target.stat().st_size,
        "sha256": digest,
    }
    if schema == SCHEMA:
        metadata["summary"] = {
            "coverage": model.get("coverage", {}),
            "pair_count": len(model.get("pairs", {})),
        }
    publish_json(stamp, metadata)
    return target
