"""Compact, atomic cache publication with a private temporary file per writer."""

import json
from itertools import batched
from pathlib import Path
import tempfile
from sora_bilingual.config.native_config import replace_file


def _publish(path, write):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as out:
        temporary = Path(out.name)
        try:
            write(out)
        except Exception:
            out.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_json(path, value):
    """Write nested cache sections in C-encoded batches, preserving JSON bytes."""

    def encode(item):
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"))

    def write(out, item):
        if isinstance(item, dict):
            opening, closing = "{", "}"
        elif isinstance(item, (list, tuple)):
            opening, closing = "[", "]"
        else:
            out.write(encode(item))
            return
        out.write(opening)
        if len(item) > 128:
            values = item.items() if isinstance(item, dict) else item
            for index, batch in enumerate(batched(values, 128)):
                if index:
                    out.write(",")
                out.write(encode(dict(batch) if isinstance(item, dict) else batch)[1:-1])
        else:
            values = item.items() if isinstance(item, dict) else enumerate(item)
            for index, (key, child) in enumerate(values):
                if index:
                    out.write(",")
                if isinstance(item, dict):
                    # Let the C encoder retain JSON's key coercion/escaping;
                    # remove only the braces and the literal null value.
                    out.write(encode({key: None})[1:-5])
                write(out, child)
        out.write(closing)

    _publish(path, lambda out: write(out, value))


def read_model(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        if any(
            not isinstance(value.get(k), dict)
            for k in (
                "pairs",
                "plain_pairs",
                "keyed",
                "scoped",
                "script_identities",
                "table_identities",
            )
        ):
            return None
        if any(
            not isinstance(value.get(k), list) for k in ("numeric", "raw_numeric", "detail_sources")
        ):
            return None
        for key in ("pairs", "plain_pairs"):
            # Raw translations must be complete, but their normalized forms
            # may be empty after stripping formatting (e.g. colour controls).
            # The compiler emits both dictionaries; rejecting a valid normalized
            # value invalidated the entire disk model on every later launch.
            if any(
                not isinstance(s, str)
                or not isinstance(pair, list)
                or len(pair) != 2
                or any(not isinstance(t, str) or (key == "pairs" and not t.strip()) for t in pair)
                for s, pair in value[key].items()
            ):
                return None
        return value
    except PermissionError:
        # An inaccessible model is not a corrupt/missing model. Preserve the
        # original failure; never rebuild or replace it to hide access denial.
        raise
    except OSError, ValueError:
        return None
