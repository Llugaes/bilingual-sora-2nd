#!/usr/bin/env python3
"""Read a bounded, external-only snapshot of Sora 2nd's native UI layouts.

This is a diagnostic collector.  It opens the game with PROCESS_VM_READ and
PROCESS_QUERY_INFORMATION only; it never injects, writes memory, suspends a
thread, or sends input to the game.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import time
from typing import Any


PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
LIST_MODULES_ALL = 0x03
PTR_SIZE = 8

LAYOUT_MANAGER_GLOBAL_RVA = 0xC60E88
LABEL_VTABLE_RVA = 0xB18490

LAYOUT_VECTOR_DATA = 0x50
LAYOUT_VECTOR_COUNT = 0x58
LAYOUT_ID = 0x80
LAYOUT_ROOT = 0xA8

NODE_PARENT = 0x80
NODE_NAME = 0x88
# Verified in sora_2nd.exe 1.0.0.0 by the base node update virtual method at
# RVA 0x581168: data=[node+0x228], count=[node+0x230], then it visits data[i].
# The immediately preceding +0x240/+0x248 loop is a distinct component list.
NODE_CHILDREN_DATA = 0x228
NODE_CHILDREN_COUNT = 0x230
NODE_MATRIX = 0x08

LABEL_FLAGS = 0x2E8
LABEL_SIZE = 0x304
LABEL_TEXT = 0x318
LABEL_GLYPH_COUNT = 0x330
LABEL_MEASURED_GLYPH_COUNT = 0x334
LABEL_LINE_BREAKS = 0x358
LABEL_LINE_BREAK_COUNT = 0x360
LABEL_MEASURED_BOUNDS = 0x368
LABEL_MEASURED_FLOATS = 0x378
LABEL_LINE_STORAGE = 0x390
LABEL_LINE_COUNT = 0x398
LABEL_HORIZONTAL_ALIGN = 0x3B4
LABEL_LINE_INFO_DATA = 0x660
LABEL_LINE_INFO_COUNT = 0x668
LABEL_GLYPH_MANAGER = 0x680
GLYPH_MANAGER_ARRAY = 0x20
LABEL_UPDATE_DIRTY = 0x688
LABEL_MEASURE_DIRTY = 0x689
GLYPH_RECORD_SIZE = 0xC4
LINE_INFO_RECORD_SIZE = 12

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", wintypes.LPVOID),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", wintypes.LPVOID),
    ]


kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HMODULE),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]
psapi.EnumProcessModulesEx.restype = wintypes.BOOL
psapi.GetModuleFileNameExW.argtypes = [
    wintypes.HANDLE,
    wintypes.HMODULE,
    wintypes.LPWSTR,
    wintypes.DWORD,
]
psapi.GetModuleFileNameExW.restype = wintypes.DWORD
psapi.GetModuleInformation.argtypes = [
    wintypes.HANDLE,
    wintypes.HMODULE,
    ctypes.POINTER(MODULEINFO),
    wintypes.DWORD,
]
psapi.GetModuleInformation.restype = wintypes.BOOL


class ReadError(RuntimeError):
    pass


def hx(value: int | None) -> str | None:
    return None if value is None else f"0x{value:016X}"


def clean_float(value: float) -> float | None:
    return value if math.isfinite(value) else None


class RemoteProcess:
    """A deliberately narrow ReadProcessMemory wrapper."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "RemoteProcess":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def read(self, address: int, length: int) -> bytes:
        if address <= 0 or length < 0 or length > 16 * 1024 * 1024:
            raise ReadError(f"refused read address={hx(address)} length={length}")
        buffer = ctypes.create_string_buffer(length)
        read = ctypes.c_size_t()
        ok = kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buffer, length, ctypes.byref(read)
        )
        if not ok or read.value != length:
            error = ctypes.get_last_error()
            raise ReadError(
                f"ReadProcessMemory address={hx(address)} length={length} read={read.value} "
                f"winerror={error}"
            )
        return buffer.raw

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def i32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]

    def u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def f32s(self, address: int, count: int) -> list[float | None]:
        return [
            clean_float(value)
            for value in struct.unpack(f"<{count}f", self.read(address, count * 4))
        ]

    def cstring(self, address: int, limit: int) -> str:
        if address == 0:
            return ""
        chunks: list[bytes] = []
        while sum(map(len, chunks)) < limit:
            remaining = limit - sum(map(len, chunks))
            chunk = self.read(address + sum(map(len, chunks)), min(256, remaining))
            end = chunk.find(b"\0")
            if end >= 0:
                chunks.append(chunk[:end])
                return b"".join(chunks).decode("utf-8", errors="replace")
            chunks.append(chunk)
        raise ReadError(f"CString at {hx(address)} exceeds {limit} bytes")

    def module(self, expected_path: Path) -> tuple[int, int, str]:
        modules = (wintypes.HMODULE * 1024)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(
            self.handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), LIST_MODULES_ALL
        ):
            raise OSError(ctypes.get_last_error(), "EnumProcessModulesEx failed")
        for module in modules[: needed.value // ctypes.sizeof(wintypes.HMODULE)]:
            path = ctypes.create_unicode_buffer(32768)
            if not psapi.GetModuleFileNameExW(self.handle, module, path, len(path)):
                continue
            if Path(path.value).resolve() != expected_path.resolve():
                continue
            info = MODULEINFO()
            if not psapi.GetModuleInformation(
                self.handle, module, ctypes.byref(info), ctypes.sizeof(info)
            ):
                raise OSError(ctypes.get_last_error(), "GetModuleInformation failed")
            return (
                ctypes.cast(info.lpBaseOfDll, ctypes.c_void_p).value,
                info.SizeOfImage,
                path.value,
            )
        raise RuntimeError(f"target module not loaded: {expected_path}")


def field(address: int, value: Any) -> dict[str, Any]:
    return {"address": hx(address), "value": value}


def bounded_count(value: int, cap: int, what: str) -> tuple[int, str | None]:
    if value > cap:
        return cap, f"{what}={value} exceeds cap={cap}; snapshot truncated"
    return value, None


def raw_scalars(remote: RemoteProcess, address: int, length: int) -> dict[str, Any]:
    """Keep raw bits beside float views so diagnostics never guess a type."""
    raw = remote.read(address, length)
    words = list(struct.unpack(f"<{length // 4}I", raw))
    return {
        "bytes_le_hex": raw.hex(),
        "u32_le": words,
        "i32_le": [struct.unpack("<i", struct.pack("<I", value))[0] for value in words],
        "f32_le": [
            clean_float(struct.unpack("<f", struct.pack("<I", value))[0]) for value in words
        ],
    }


class Collector:
    def __init__(self, remote: RemoteProcess, base: int, args: argparse.Namespace) -> None:
        self.remote = remote
        self.base = base
        self.args = args
        self.errors: list[dict[str, str]] = []
        self.source_re = re.compile(args.source_regex) if args.source_regex else None

    def note_error(self, where: str, error: Exception) -> None:
        self.errors.append({"where": where, "error": str(error)})

    def read_node_name(self, node: int) -> tuple[int, str]:
        name_ptr = self.remote.u64(node + NODE_NAME)
        return name_ptr, self.remote.cstring(name_ptr, self.args.max_string_bytes)

    def read_node_transform(self, node: int) -> dict[str, Any]:
        raw = raw_scalars(self.remote, node + NODE_MATRIX, 0x40)
        return {
            "matrix_0x08_0x47": field(node + NODE_MATRIX, raw),
            "translation_row_0x38_0x47": field(
                node + 0x38,
                {
                    "u32_le": raw["u32_le"][12:16],
                    "f32_le": raw["f32_le"][12:16],
                },
            ),
        }

    def read_parent_chain(self, node: int) -> list[dict[str, Any]]:
        """Follow known parent pointers only; never reverse-scan heap memory."""
        result: list[dict[str, Any]] = []
        seen: set[int] = {node}
        current = self.remote.u64(node + NODE_PARENT)
        while current and len(result) < self.args.max_parent_depth:
            if current in seen:
                result.append({"ptr": hx(current), "status": "cycle"})
                break
            seen.add(current)
            parent = self.remote.u64(current + NODE_PARENT)
            name_ptr, name = self.read_node_name(current)
            result.append(
                {
                    "ptr": hx(current),
                    "parent_ptr": field(current + NODE_PARENT, hx(parent)),
                    "name_ptr": field(current + NODE_NAME, hx(name_ptr)),
                    "name": name,
                    "transform": self.read_node_transform(current),
                }
            )
            current = parent
        if current and len(result) >= self.args.max_parent_depth:
            result.append({"ptr": hx(current), "status": "truncated_by_max_parent_depth"})
        return result

    def read_line_info(self, label: int) -> dict[str, Any]:
        data = self.remote.u64(label + LABEL_LINE_INFO_DATA)
        requested_count = self.remote.u64(label + LABEL_LINE_INFO_COUNT)
        result: dict[str, Any] = {
            "record_size": LINE_INFO_RECORD_SIZE,
            "data": field(label + LABEL_LINE_INFO_DATA, hx(data)),
            "count": field(label + LABEL_LINE_INFO_COUNT, requested_count),
            "records": [],
        }
        if not data:
            return result
        count, warning = bounded_count(
            requested_count, self.args.max_lines_per_label, "line_info_count"
        )
        if warning:
            result["truncation"] = warning
        for index in range(count):
            address = data + index * LINE_INFO_RECORD_SIZE
            result["records"].append(
                {"index": index, "raw": field(address, raw_scalars(self.remote, address, 12))}
            )
        return result

    def read_line_breaks(self, label: int) -> dict[str, Any]:
        data = self.remote.u64(label + LABEL_LINE_BREAKS)
        requested_count = self.remote.u32(label + LABEL_LINE_BREAK_COUNT)
        result: dict[str, Any] = {
            "data": field(label + LABEL_LINE_BREAKS, hx(data)),
            "count": field(label + LABEL_LINE_BREAK_COUNT, requested_count),
            "entries_i32": [],
        }
        if not data:
            return result
        count, warning = bounded_count(
            requested_count, self.args.max_line_breaks, "line_break_count"
        )
        if warning:
            result["truncation"] = warning
        if count:
            result["entries_i32"] = list(
                struct.unpack(f"<{count}i", self.remote.read(data, count * 4))
            )
        return result

    def read_glyphs(self, label: int, requested_count: int) -> dict[str, Any]:
        manager_address = label + LABEL_GLYPH_MANAGER
        manager = self.remote.u64(manager_address)
        result: dict[str, Any] = {
            "count": field(label + LABEL_GLYPH_COUNT, requested_count),
            "manager_ptr": field(manager_address, hx(manager)),
            "array_ptr": None,
            "records": [],
        }
        if not manager:
            return result
        array = self.remote.u64(manager + GLYPH_MANAGER_ARRAY)
        result["array_ptr"] = field(manager + GLYPH_MANAGER_ARRAY, hx(array))
        if not array:
            return result
        count, warning = bounded_count(
            requested_count, self.args.max_glyphs_per_label, "glyph_count"
        )
        if warning:
            result["truncation"] = warning
        pointers = (
            struct.unpack(f"<{count}Q", self.remote.read(array, count * PTR_SIZE)) if count else ()
        )
        for index, glyph in enumerate(pointers):
            if not glyph:
                result["records"].append({"index": index, "ptr": None})
                continue
            raw = self.remote.read(glyph, GLYPH_RECORD_SIZE)
            float_at = lambda offset: clean_float(struct.unpack_from("<f", raw, offset)[0])
            result["records"].append(
                {
                    "index": index,
                    "ptr": hx(glyph),
                    "geometry": {
                        "w_0x08": float_at(0x08),
                        "h_0x1c": float_at(0x1C),
                        "x_0x38": float_at(0x38),
                        "y_0x3c": float_at(0x3C),
                    },
                    "color_0x98_0xa4": [float_at(offset) for offset in (0x98, 0x9C, 0xA0, 0xA4)],
                    "kind_0xc0": struct.unpack_from("<I", raw, 0xC0)[0],
                }
            )
        return result

    def snapshot_label(
        self, node: int, path: str, parent: int, name_ptr: int, name: str
    ) -> dict[str, Any] | None:
        text_ptr = self.remote.u64(node + LABEL_TEXT)
        text = self.remote.cstring(text_ptr, self.args.max_string_bytes) if text_ptr else ""
        if self.source_re and not self.source_re.search(text):
            return None
        glyph_count = self.remote.u32(node + LABEL_GLYPH_COUNT)
        if glyph_count > self.args.max_native_glyph_count:
            raise ReadError(
                f"label {hx(node)} has unvalidated glyph count {glyph_count} "
                f"> {self.args.max_native_glyph_count}"
            )
        child_data = self.remote.u64(node + NODE_CHILDREN_DATA)
        child_count = self.remote.u64(node + NODE_CHILDREN_COUNT)
        raw_line_storage = self.remote.u64(node + LABEL_LINE_STORAGE)
        return {
            "path": path,
            "ptr": hx(node),
            "vtable": field(node, hx(self.remote.u64(node))),
            "node": {
                "parent_ptr": field(node + NODE_PARENT, hx(parent)),
                "name_ptr": field(node + NODE_NAME, hx(name_ptr)),
                "name": name,
                "children": {
                    "data": field(node + NODE_CHILDREN_DATA, hx(child_data)),
                    "count": field(node + NODE_CHILDREN_COUNT, child_count),
                },
                # The base node constructor (RVA 0x57C530) initializes this
                # matrix to identity; RVA 0x584CA0 consumes label+0x08..0x47
                # while projecting glyph geometry.  It is emitted as raw bits
                # because a separate local/world field name is unproven.
                "transform": self.read_node_transform(node),
                "transform_raw_0x08_0x7f": field(
                    node + NODE_MATRIX, raw_scalars(self.remote, node + NODE_MATRIX, 0x78)
                ),
                "parent_chain": self.read_parent_chain(node),
                "world_matrix": {
                    "status": "unknown",
                    "reason": "no static proof yet maps a separate world matrix field",
                },
            },
            "label": {
                "alignment_box_raw_0x2d8_0x2e7": field(
                    node + 0x2D8, raw_scalars(self.remote, node + 0x2D8, 0x10)
                ),
                "measurement_control_raw_0x2d8_0x317": field(
                    node + 0x2D8, raw_scalars(self.remote, node + 0x2D8, 0x40)
                ),
                "flags": field(node + LABEL_FLAGS, self.remote.u32(node + LABEL_FLAGS)),
                "size": field(node + LABEL_SIZE, self.remote.u32(node + LABEL_SIZE)),
                "text_ptr": field(node + LABEL_TEXT, hx(text_ptr)),
                "text": text,
                "measurement_state_raw_0x330_0x3bf": field(
                    node + LABEL_GLYPH_COUNT,
                    raw_scalars(self.remote, node + LABEL_GLYPH_COUNT, 0x90),
                ),
                "measured_raw_0x368_0x37f": field(
                    node + LABEL_MEASURED_BOUNDS,
                    raw_scalars(self.remote, node + LABEL_MEASURED_BOUNDS, 0x18),
                ),
                "line_breaks": self.read_line_breaks(node),
                "line_storage": {
                    "status": "opaque",
                    "storage_ptr_0x390": field(node + LABEL_LINE_STORAGE, hx(raw_line_storage)),
                    "count_0x398": field(
                        node + LABEL_LINE_COUNT, self.remote.u32(node + LABEL_LINE_COUNT)
                    ),
                    "reason": "constructor identifies storage but record layout is not statically validated",
                },
                "line_info": self.read_line_info(node),
                "update_gates": {
                    "update_dirty_0x688": field(
                        node + LABEL_UPDATE_DIRTY, self.remote.read(node + LABEL_UPDATE_DIRTY, 1)[0]
                    ),
                    "measure_dirty_0x689": field(
                        node + LABEL_MEASURE_DIRTY,
                        self.remote.read(node + LABEL_MEASURE_DIRTY, 1)[0],
                    ),
                },
                "glyphs": self.read_glyphs(node, glyph_count),
            },
        }

    def walk_root(self, root: int) -> list[dict[str, Any]]:
        labels: list[dict[str, Any]] = []
        queue: list[tuple[int, str, int]] = [(root, "", 0)]
        seen: set[int] = set()
        while queue:
            node, parent_path, expected_parent = queue.pop(0)
            if not node or node in seen:
                continue
            if len(seen) >= self.args.max_nodes:
                self.errors.append(
                    {"where": hx(node) or "node", "error": "node cap reached; traversal truncated"}
                )
                break
            seen.add(node)
            try:
                parent = self.remote.u64(node + NODE_PARENT)
                name_ptr, name = self.read_node_name(node)
                component = name.replace("/", "\\/") if name else f"@{node:016X}"
                path = f"{parent_path}/{component}" if parent_path else component
                vtable = self.remote.u64(node)
                if vtable == self.base + LABEL_VTABLE_RVA:
                    label = self.snapshot_label(node, path, parent, name_ptr, name)
                    if label is not None:
                        labels.append(label)

                child_data = self.remote.u64(node + NODE_CHILDREN_DATA)
                child_count = self.remote.u64(node + NODE_CHILDREN_COUNT)
                count, warning = bounded_count(
                    child_count, self.args.max_children_per_node, "child_count"
                )
                if warning:
                    self.errors.append({"where": hx(node) or "node", "error": warning})
                if child_data and count:
                    children = struct.unpack(
                        f"<{count}Q", self.remote.read(child_data, count * PTR_SIZE)
                    )
                    queue.extend((child, path, node) for child in children if child)
            except (ReadError, struct.error) as error:
                self.note_error(f"node {hx(node)}", error)
        return labels

    def collect(self) -> dict[str, Any]:
        global_address = self.base + LAYOUT_MANAGER_GLOBAL_RVA
        manager = self.remote.u64(global_address)
        result: dict[str, Any] = {
            "collector": "tools/read_native_layout.py",
            "safety": "OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION) + ReadProcessMemory only",
            "module_base": hx(self.base),
            "layout_manager_global": field(global_address, hx(manager)),
            "verified_offsets": {
                "layout_vector": {"data": "0x50", "count": "0x58", "instance": "pointer[8]"},
                "layout": {"id": "0x80", "root": "0xa8"},
                "node_children": {
                    "data": "0x228",
                    "count": "0x230",
                    "static_evidence": "sora_2nd.exe RVA 0x581168 iterates pointer[8] from data to data+count*8",
                },
                "label": {
                    "vtable_rva": "0xb18490",
                    "text": "0x318",
                    "size": "0x304",
                    "flags": "0x2e8",
                },
                "measurement_and_latebound": {
                    "0x2e0_alignment_selector": {
                        "source_rva": "0x584CF4",
                        "evidence": "passed with +0x2d8 into alignment helper 0x589130",
                    },
                    "0x2f8_0x2fc_start_y_adjustment": {
                        "source_rva": "0x5885CC, 0x58860C",
                        "evidence": "parser reads +0x2fc for first line and +0x2f8 for later lines",
                    },
                    "0x334_0x358_0x360_measurement_state": {
                        "source_rva": "0x5888D7..0x588922, 0x58761B..0x587669",
                        "evidence": "measurement copies parser output into glyph count and bounded line-break slots",
                    },
                    "0x368_0x37c_measured_bounds_scale": {
                        "source_rva": "0x5889B5, 0x588963, 0x58867A..0x5886FD",
                        "evidence": "measurement stores bounds/scale and alignment consumes them",
                    },
                    "0x3b4_horizontal_alignment_mode": {
                        "source_rva": "0x588661",
                        "evidence": "selects the horizontal X offset calculation for parsed line data",
                    },
                    "0x660_0x668_line_info": {
                        "source_rva": "0x58875B, 0x5888BC, 0x5885A5..0x5885B9",
                        "evidence": "measure resets count, passes line storage to parser, then indexes 12-byte records",
                    },
                    "0x688_0x689_gates": {
                        "source_rva": "0x584CB0..0x584CEF, 0x5889BC",
                        "evidence": "0x689 gates measure function 0x588710; 0x688/flag 0x40 gate update 0x5875A0",
                    },
                },
                "glyph": {"count": "0x330", "manager": "0x680", "manager_array": "0x20"},
            },
            "layouts": [],
            "errors": self.errors,
        }
        if not manager:
            result["errors"].append({"where": "layout manager", "error": "null global pointer"})
            return result
        count = self.remote.u32(manager + LAYOUT_VECTOR_COUNT)
        high = self.remote.u32(manager + LAYOUT_VECTOR_COUNT + 4)
        data = self.remote.u64(manager + LAYOUT_VECTOR_DATA)
        result["layout_vector"] = {
            "data": field(manager + LAYOUT_VECTOR_DATA, hx(data)),
            "count": field(manager + LAYOUT_VECTOR_COUNT, count),
            "high_dword": field(manager + LAYOUT_VECTOR_COUNT + 4, high),
        }
        if high != 0 or count > self.args.max_layouts:
            raise ReadError(f"unvalidated layout vector count={count} high_dword={high}")
        if not data and count:
            raise ReadError("layout vector has a null data pointer with nonzero count")
        layouts = (
            struct.unpack(f"<{count}Q", self.remote.read(data, count * PTR_SIZE)) if count else ()
        )
        for index, layout in enumerate(layouts):
            if not layout:
                continue
            try:
                layout_id = self.remote.u32(layout + LAYOUT_ID)
                root = self.remote.u64(layout + LAYOUT_ROOT)
                if self.args.layout_id is not None and layout_id != self.args.layout_id:
                    continue
                item = {
                    "index": index,
                    "ptr": hx(layout),
                    "layout_id": field(layout + LAYOUT_ID, layout_id),
                    "root_ptr": field(layout + LAYOUT_ROOT, hx(root)),
                    "labels": self.walk_root(root) if root else [],
                }
                result["layouts"].append(item)
            except (ReadError, struct.error) as error:
                self.note_error(f"layout[{index}] {hx(layout)}", error)
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    environment = os.environ.get("SORA_GAME_EXE")
    parser.add_argument("--pid", type=int, required=True, help="running sora_2nd.exe PID")
    parser.add_argument(
        "--exe",
        type=Path,
        default=Path(environment) if environment else None,
        help="exact module path to locate; defaults to SORA_GAME_EXE when set",
    )
    parser.add_argument(
        "--source-regex", help="only emit labels whose UTF-8 source text matches this regex"
    )
    parser.add_argument("--layout-id", type=int, help="only traverse this native layout id")
    parser.add_argument("--max-layouts", type=int, default=8192)
    parser.add_argument("--max-nodes", type=int, default=20000)
    parser.add_argument("--max-children-per-node", type=int, default=8192)
    parser.add_argument("--max-native-glyph-count", type=int, default=32768)
    parser.add_argument("--max-glyphs-per-label", type=int, default=2048)
    parser.add_argument("--max-lines-per-label", type=int, default=2048)
    parser.add_argument("--max-line-breaks", type=int, default=8)
    parser.add_argument("--max-parent-depth", type=int, default=32)
    parser.add_argument("--max-string-bytes", type=int, default=32768)
    parser.add_argument("--out", type=Path, help="JSON output path; defaults under generated/")
    args = parser.parse_args()
    if args.exe is None:
        parser.error("--exe is required unless SORA_GAME_EXE is set")
    return args


def main() -> int:
    args = parse_args()
    if args.pid <= 0:
        raise SystemExit("--pid must be positive")
    started = time.perf_counter()
    with RemoteProcess(args.pid) as remote:
        base, image_size, module_path = remote.module(args.exe)
        result = Collector(remote, base, args).collect()
    result["pid"] = args.pid
    result["module"] = {"path": module_path, "image_size": image_size}
    result["captured_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    if args.out is None:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        args.out = Path("generated") / f"diagnostic-082-layout-{args.pid}-{stamp}.json"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    label_count = sum(len(layout["labels"]) for layout in result["layouts"])
    print(
        f"wrote {args.out} ({label_count} labels, {result['elapsed_ms']} ms, {len(result['errors'])} read errors)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ReadError, RuntimeError, re.error, struct.error) as error:
        print(f"read_native_layout: {error}", file=sys.stderr)
        raise SystemExit(2)
