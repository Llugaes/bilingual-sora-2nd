"""Lossless shared-node transport cache; no locale-specific pruning."""

import hashlib
import json
from pathlib import Path
from sora_bilingual.localization.cache_io import publish_json


SCHEMA = 1


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
    return {"schema": SCHEMA, "root": root, "nodes": nodes}


def wire_path(model_path):
    return Path(model_path).with_suffix(".wire.json")


def wire_ready(model_path):
    source = Path(model_path)
    target = wire_path(source)
    try:
        saved = json.loads(target.with_suffix(".stamp.json").read_text("utf-8"))
        return (
            saved["source"]
            == {"schema": SCHEMA, "size": source.stat().st_size, "mtime": source.stat().st_mtime_ns}
            and target.stat().st_size == saved["size"]
        )
    except OSError, ValueError, KeyError, TypeError:
        return False


def prepare_wire(model_path, model=None):
    source = Path(model_path)
    target = wire_path(source)
    stamp = target.with_suffix(".stamp.json")
    identity = {"schema": SCHEMA, "size": source.stat().st_size, "mtime": source.stat().st_mtime_ns}
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
    publish_json(target, pack_model(model))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    publish_json(stamp, {"source": identity, "size": target.stat().st_size, "sha256": digest})
    return target
