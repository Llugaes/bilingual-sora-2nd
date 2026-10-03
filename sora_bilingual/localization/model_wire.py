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

    root = intern(model)
    return {"schema": 1, "root": root, "nodes": nodes}


def indexed_model(model):
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
    packed = pack_model({**model, "paragraph_sources": paragraphs})
    nodes = packed["nodes"]
    table = bytearray(len(nodes) * 16)
    data = bytearray()
    hashes = {}

    def key_hash(node_id):
        if node_id not in hashes:
            value = 2166136261
            for (unit,) in struct.iter_unpack(
                "<H", nodes[node_id].encode("utf-16-le", "surrogatepass")
            ):
                value = ((value ^ unit) * 16777619) & 0xFFFFFFFF
            hashes[node_id] = value
        return hashes[node_id]

    for index, node in enumerate(nodes):
        while len(data) % 4:
            data.append(0)
        offset, count = len(data), 0
        if node is None:
            kind = 0
        elif isinstance(node, bool):
            kind, count = 1, int(node)
        elif isinstance(node, (int, float)):
            kind = 2
            data.extend(struct.pack("<d", node))
        elif isinstance(node, str):
            kind = 3
            encoded = node.encode("utf-16-le", "surrogatepass")
            count = len(encoded) // 2
            data.extend(encoded)
        elif node[0] == 0:
            kind, count = 4, len(node) - 1
            data.extend(struct.pack(f"<{count}I", *node[1:]))
        else:
            kind, count = 5, (len(node) - 1) // 2
            data.extend(struct.pack(f"<{count * 2}I", *node[1:]))
            order = sorted((key_hash(node[1 + entry * 2]), entry) for entry in range(count))
            data.extend(struct.pack(f"<{count * 2}I", *(item for pair in order for item in pair)))
        struct.pack_into("<4I", table, index * 16, kind, count, offset, len(data) - offset)
    data_offset = 32 + len(table)
    header = struct.pack(
        "<8s6I",
        b"SORAMOD2",
        SCHEMA,
        len(nodes),
        packed["root"],
        32,
        data_offset,
        data_offset + len(data),
    )
    return header + table + data


def publish_indexed(path, model):
    content = indexed_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, suffix=".tmp", delete=False) as out:
        temporary = Path(out.name)
        try:
            out.write(content)
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
    except OSError, ValueError, KeyError, TypeError:
        return False


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
    try:
        saved = json.loads(stamp.read_text("utf-8"))
        if saved["source"] == identity and target.stat().st_size == saved["size"]:
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == saved.get("sha256"):
                    return target
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
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    publish_json(stamp, {"source": identity, "size": target.stat().st_size, "sha256": digest})
    return target
