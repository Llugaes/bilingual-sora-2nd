#!/usr/bin/env python3
"""Read the static status-layout and texture contracts without modifying the game.

The game's ``.lay`` records are a bounded binary JSON container.  This tool
only decodes the record types observed in the installed 1.0.0.0 layout pack;
unknown records are retained as opaque and never guessed as object links.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.localization.resources import FpacArchive


MAGIC = b"JSON"
STRING = 2
NUMBER = 3
OBJECT = 4
ARRAY = 5
BOOLEAN = 6
NODE = 20
MAX_CHILDREN = 8192
MAX_DECOMPRESSED = 16 * 1024 * 1024

# Each binary layout owns its own serialization-key table. These pairs were
# read from the installed layouts' named-node/child-array records; they are
# not native offsets and must not be reused for another .lay file.
LAYOUT_NODE_KEYS = {
    "layout/camp_status.lay": (152, 391),
    "layout/status_window.lay": (152, 369),
}


class LayoutFormatError(ValueError):
    pass


class Layout:
    def __init__(self, data: bytes, name: str, node_keys: tuple[int, int]) -> None:
        if len(data) < 16 or data[:4] != MAGIC:
            raise LayoutFormatError(f"{name}: missing JSON layout header")
        self.data = data
        self.name = name
        self.root = self.u32(8)
        self._validate_offset(self.root)
        self.node_name_key, self.node_children_key = node_keys

    def _validate_offset(self, offset: int) -> None:
        if offset >= len(self.data):
            raise LayoutFormatError(f"{self.name}: record offset {offset:#x} outside layout")

    def u32(self, offset: int) -> int:
        if offset < 0 or offset + 4 > len(self.data):
            raise LayoutFormatError(f"{self.name}: truncated u32 at {offset:#x}")
        return struct.unpack_from("<I", self.data, offset)[0]

    def tag(self, offset: int) -> int:
        self._validate_offset(offset)
        return self.data[offset]

    def key(self, offset: int) -> int:
        return self.u32(offset + 1)

    def refs(self, offset: int) -> tuple[int, ...]:
        tag = self.tag(offset)
        if tag in (OBJECT, ARRAY):
            count, start = self.u32(offset + 5), offset + 9
        elif tag == NODE:
            count, start = self.key(offset), offset + 5
        else:
            return ()
        if count > MAX_CHILDREN or start + count * 4 > len(self.data):
            raise LayoutFormatError(
                f"{self.name}: invalid record links at {offset:#x}, count={count}"
            )
        result = struct.unpack_from(f"<{count}I", self.data, start)
        for child in result:
            self._validate_offset(child)
        return result

    def string(self, offset: int) -> str | None:
        if self.tag(offset) != STRING:
            return None
        start = offset + 5
        end = self.data.find(b"\0", start, min(len(self.data), start + 32768))
        if end < 0:
            raise LayoutFormatError(f"{self.name}: unbounded string at {offset:#x}")
        return self.data[start:end].decode("utf-8", errors="strict")

    def number(self, offset: int) -> float | None:
        if self.tag(offset) != NUMBER or offset + 13 > len(self.data):
            return None
        return struct.unpack_from("<d", self.data, offset + 5)[0]

    def _direct_strings(self, offset: int) -> list[tuple[int, str]]:
        return [
            (self.key(child), self.string(child))
            for child in self.refs(offset)
            if self.tag(child) == STRING
        ]

    def _all_nodes(self) -> list[int]:
        found: list[int] = []
        seen: set[int] = set()

        def visit(offset: int) -> None:
            if offset in seen:
                return
            seen.add(offset)
            if self.tag(offset) == NODE:
                found.append(offset)
            for child in self.refs(offset):
                visit(child)

        visit(self.root)
        return found

    def node_name(self, offset: int) -> str | None:
        if self.tag(offset) != NODE:
            return None
        values = [value for key, value in self._direct_strings(offset) if key == self.node_name_key]
        if len(values) > 1:
            raise LayoutFormatError(f"{self.name}: node at {offset:#x} has multiple names")
        return values[0] if values else None

    def node_children(self, offset: int) -> tuple[int, ...]:
        if self.tag(offset) != NODE:
            return ()
        children: list[int] = []
        for field in self.refs(offset):
            if self.tag(field) != ARRAY or self.key(field) != self.node_children_key:
                continue
            children.extend(child for child in self.refs(field) if self.tag(child) == NODE)
        return tuple(children)

    def all_nodes(self) -> list[int]:
        return self._all_nodes()


def lz4_block(data: bytes) -> bytes:
    result = bytearray()
    pos = 0
    while pos < len(data):
        token = data[pos]
        pos += 1
        literal = token >> 4
        if literal == 15:
            while True:
                if pos >= len(data):
                    raise LayoutFormatError("truncated LZ4 literal length")
                value = data[pos]
                pos += 1
                literal += value
                if value != 255:
                    break
        if pos + literal > len(data):
            raise LayoutFormatError("LZ4 literal exceeds its block")
        result.extend(data[pos : pos + literal])
        pos += literal
        if pos == len(data):
            break
        if pos + 2 > len(data):
            raise LayoutFormatError("truncated LZ4 match offset")
        match_offset = data[pos] | data[pos + 1] << 8
        pos += 2
        if not match_offset or match_offset > len(result):
            raise LayoutFormatError("invalid LZ4 match offset")
        match = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                if pos >= len(data):
                    raise LayoutFormatError("truncated LZ4 match length")
                value = data[pos]
                pos += 1
                match += value
                if value != 255:
                    break
        if len(result) + match > MAX_DECOMPRESSED:
            raise LayoutFormatError("LZ4 output exceeds diagnostic cap")
        for _ in range(match):
            result.append(result[-match_offset])
    return bytes(result)


def lz4_frame(data: bytes) -> bytes:
    if len(data) < 7 or data[:4] != b"\x04\x22\x4d\x18":
        raise LayoutFormatError("expected standard LZ4 frame")
    flags = data[4]
    if flags >> 6 != 1:
        raise LayoutFormatError(f"unsupported LZ4 version flags {flags:#x}")
    pos = 6 + (8 if flags & 0x08 else 0) + (4 if flags & 0x01 else 0) + 1
    if pos > len(data):
        raise LayoutFormatError("truncated LZ4 frame header")
    result = bytearray()
    while True:
        if pos + 4 > len(data):
            raise LayoutFormatError("truncated LZ4 block header")
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if size == 0:
            return bytes(result)
        packed_size = size & 0x7FFFFFFF
        if pos + packed_size > len(data):
            raise LayoutFormatError("LZ4 block exceeds frame")
        block = data[pos : pos + packed_size]
        pos += packed_size
        decoded = block if size & 0x80000000 else lz4_block(block)
        if len(result) + len(decoded) > MAX_DECOMPRESSED:
            raise LayoutFormatError("LZ4 output exceeds diagnostic cap")
        result.extend(decoded)


def texture_metadata(data: bytes) -> dict[str, Any]:
    decoded = lz4_frame(data)
    if len(decoded) < 148 or decoded[:4] != b"DDS " or decoded[84:88] != b"DX10":
        raise LayoutFormatError("camp000 is not a DX10 DDS after LZ4 decoding")
    return {
        "compressed_sha256": hashlib.sha256(data).hexdigest(),
        "compressed_bytes": len(data),
        "decoded_bytes": len(decoded),
        "width": struct.unpack_from("<I", decoded, 16)[0],
        "height": struct.unpack_from("<I", decoded, 12)[0],
        "mip_count": struct.unpack_from("<I", decoded, 28)[0],
        "dxgi_format": struct.unpack_from("<I", decoded, 128)[0],
    }


def layout_summary(layout: Layout) -> dict[str, Any]:
    nodes = layout.all_nodes()
    named = {offset: layout.node_name(offset) for offset in nodes}
    targets = []
    for offset, name in named.items():
        if name not in {"status_root", "temp_status_root"}:
            continue
        targets.append(
            {
                "record_offset": f"0x{offset:x}",
                "name": name,
                "serialized_direct_child_nodes": len(layout.node_children(offset)),
            }
        )
    target_paths: list[dict[str, Any]] = []

    def walk(offset: int, path: list[str]) -> None:
        name = layout.node_name(offset)
        if name is None:
            return
        current = [*path, name]
        if current[-3:] == ["param", "item_template", "name"]:
            strings = [
                {"serialization_key": key, "value": value}
                for key, value in layout._direct_strings(offset)
                if value != name
            ]
            target_paths.append(
                {
                    "path": "/".join(current),
                    "record_offset": f"0x{offset:x}",
                    "direct_field_count": len(layout.refs(offset)),
                    "non_name_string_fields": strings,
                    "four_number_fields": [
                        {
                            "serialization_key": layout.key(field),
                            "values": [layout.number(value) for value in layout.refs(field)],
                        }
                        for field in layout.refs(offset)
                        if layout.tag(field) == OBJECT
                        and len(layout.refs(field)) == 4
                        and all(layout.tag(value) == NUMBER for value in layout.refs(field))
                    ],
                }
            )
        for child in layout.node_children(offset):
            walk(child, current)

    child_nodes = {child for offset in nodes for child in layout.node_children(offset)}
    for offset in nodes:
        if offset not in child_nodes:
            walk(offset, [])
    return {
        "path": layout.name,
        "serialization_keys": {
            "node_name": layout.node_name_key,
            "node_children": layout.node_children_key,
        },
        "node_count": len(nodes),
        "status_containers": targets,
        "param_item_template_name_paths": target_paths,
        "has_name_text_literal": b"name_text\0" in layout.data,
        "has_item_template_literal": b"item_template\0" in layout.data,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "generated/diagnostic-135-status-sprite-contract.json"
    )
    parser.add_argument(
        "--node-snapshot", type=Path, default=ROOT / "generated/diagnostic-134-status-nodes.json"
    )
    args = parser.parse_args()
    pac = args.game_dir / "pac/steam"
    layouts = tuple(LAYOUT_NODE_KEYS)
    with FpacArchive(pac / "layout.pac") as archive:
        layout_result = [
            layout_summary(Layout(archive.read(path), path, LAYOUT_NODE_KEYS[path]))
            for path in layouts
        ]

    image_archives = ("image.pac", "image_en.pac", "image_sc.pac", "image_tc.pac", "image_ko.pac")
    resource_names = {"camp000"}
    for layout in layout_result:
        for target in layout["param_item_template_name_paths"]:
            resource_names.update(field["value"] for field in target["non_name_string_fields"])
    image_result: dict[str, Any] = {}
    for archive_name in image_archives:
        with FpacArchive(pac / archive_name) as archive:
            resources = {}
            for resource_name in sorted(resource_names):
                keys = [key for key in archive.entries if key.endswith(f"/{resource_name}.dds")]
                resources[resource_name] = {
                    "entries": keys,
                    **({"metadata": texture_metadata(archive.read(keys[0]))} if keys else {}),
                }
            image_result[archive_name] = resources

    observed_nodes: list[dict[str, Any]] = []
    if args.node_snapshot.exists():
        values = json.loads(args.node_snapshot.read_text(encoding="utf-8"))
        observed_nodes = [
            value
            for value in values
            if value.get("path", "").endswith("/status_root/root/param/item_template/name")
        ]
    result = {
        "safety": "PAC reads only; no game process attach, writes, injection, or archive changes",
        "layout_parser": {
            "verified_record_types": {
                "string": STRING,
                "number": NUMBER,
                "object": OBJECT,
                "array": ARRAY,
                "node": NODE,
            },
            "key_scope": "serialization keys are discovered independently for each .lay file",
        },
        "layouts": layout_result,
        "images": image_result,
        "observed_runtime_snapshot": {
            "path": str(args.node_snapshot),
            "matching_nodes": observed_nodes,
        },
        "conclusion": (
            "camp_status serializes empty status_root containers, while status_window provides the "
            "reused param/item_template/name Sprite with a window3 resource string and a four-number "
            "field. Static records establish the locale atlas candidates but do not establish how the "
            "runtime status nodes select a locale or bind that field as UV. The existing status-list "
            "name_text literal belongs to a different layout and is not a reusable child of "
            "camp_status/status_root."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
