"""Read-only catalogue builder for Trails in the Sky 2nd Chapter script PACs.

The game files are never opened for writing.  The parser deliberately accepts
only the SCP subset described by Ingert's ``src/scp/io`` implementation.  A
function contributes text within validated structural groups. Static dialogue
wrapping may vary; command identities, dynamic arguments and control flow remain
part of the validation contract.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import mmap
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


from sora_bilingual.config.locales import LANGUAGES, archive_names

_ARCHIVES = archive_names("script")
_U32 = struct.Struct("<I")
_SCP_HEADER = struct.Struct("<4sIIIII")
_FUNCTION = struct.Struct("<IBHBIIIIII")
_CALLED = struct.Struct("<IHHI")


class FormatError(ValueError):
    """The input is not a bounded, understood FPAC/SCP structure."""


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FormatError(f"u32 outside input at {offset:#x}")
    return _U32.unpack_from(data, offset)[0]


def _slice(data: bytes, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise FormatError(f"range outside input at {offset:#x}+{size:#x}")
    return data[offset : offset + size]


def _utf8z(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise FormatError(f"string outside input at {offset:#x}")
    end = data.find(b"\0", offset)
    if end < 0:
        raise FormatError(f"unterminated string at {offset:#x}")
    try:
        return data[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FormatError(f"non-UTF-8 string at {offset:#x}") from exc


def _value(data: bytes, offset: int) -> tuple[str, object]:
    raw = _u32(data, offset)
    tag, payload = raw >> 30, raw & 0x3FFFFFFF
    if tag == 0:
        # The compiler emits raw special values (notably null) in defaults and
        # call metadata.  They are non-text, but retaining their exact raw
        # value in the shape prevents a locale mismatch being hidden.
        return "special", raw
    if tag == 1:
        return "int", (payload << 2 >> 2) if payload < (1 << 29) else payload - (1 << 30)
    if tag == 2:
        # Ingert recovers the two discarded low bits heuristically.  They do
        # not affect structural matching, so retain the stored 30-bit payload.
        return "float", payload
    if tag == 3:
        return "string", _utf8z(data, payload)
    raise AssertionError("unreachable SCP value tag")


def _string_value(data: bytes, offset: int) -> str:
    kind, value = _value(data, offset)
    if kind != "string":
        raise FormatError(f"expected string SCP value at {offset:#x}, got {kind}")
    return str(value)


@dataclass(frozen=True)
class Called:
    target: str | None
    kind: int
    args: tuple[tuple[str, object | None], ...]

    def shape(self) -> tuple[object, ...]:
        # Extern and tailcall records encode their callee name in the first
        # string argument (rather than ``target``).  It is an identifier, not
        # display text, so it must remain part of the structural signature.
        return (
            self.target,
            self.kind,
            tuple(
                (
                    kind,
                    value if kind != "string" or (self.kind in (1, 2) and index == 0) else None,
                )
                for index, (kind, value) in enumerate(self.args)
            ),
        )

    def display_text_slots(self) -> Iterable[tuple[int, str]]:
        """Yield static display strings, excluding an external callee name."""
        for index, (kind, value) in enumerate(self.args):
            if kind == "string" and not (self.kind in (1, 2) and index == 0) and value:
                yield index, str(value)

    def dialogue_shape(self) -> tuple[object, ...]:
        """Treat verified static dialogue as one payload, regardless of wrapping.

        The full ordered call sequence, command, speaker and voice identifiers
        still have to match. No dynamic argument or non-newline opcode is erased.
        """
        if self.kind == 3 and self.args[:2] == (("int", 5), ("int", 8)):
            panel = static_panel_parts(self)
            if panel is None:
                return self.shape()
            return self.target, self.kind, self.args[:3], panel[1], "static-dialogue"
        if assembled_dialogue(self) is None:
            return self.shape()
        first = next(i for i, (kind, _) in enumerate(self.args) if kind == "string")
        controls = tuple(
            arg for arg in self.args[first:] if arg[0] != "string" and arg != ("int", 10)
        )
        return self.target, self.kind, self.args[:first], controls, "static-dialogue"


PANEL_FLAGS = frozenset((7, 8, 9, 13, 14, 15, 16, 19, 20, 22, 24, 26, 28))


def static_panel_parts(call: Called) -> tuple[str, tuple] | None:
    """Decode command 8's verified static text and non-text control stream.

    Native builder 0x4ad670 appends strings/newlines, consumes voice IDs for
    11/12. Command 8's handler 0x4aee20 delegates window flags to 0x4affd0.
    Those controls may repeat
    anywhere; their number is not a fixed text-argument offset. Interpolations
    17/18/21/23 and unknown operations remain rejected, including before the
    first literal. Keep controls in the alignment signature, not just text.
    """
    if (
        call.kind != 3
        or len(call.args) < 4
        or call.args[:2] != (("int", 5), ("int", 8))
        or call.args[2][0] != "int"
    ):
        return None
    parts, controls = [], []
    saw_string = False
    i = 3
    while i < len(call.args):
        kind, value = call.args[i]
        if kind == "string":
            parts.append(str(value))
            saw_string = True
        elif kind == "int" and value == 10:
            parts.append("\n")
        elif kind == "int" and value in PANEL_FLAGS:
            controls.append((value,))
        elif kind == "int" and value in (11, 12):
            if i + 1 >= len(call.args) or call.args[i + 1][0] != "int":
                return None
            i += 1
            controls.append((value, call.args[i][1]))
        else:
            return None
        i += 1
    return ("".join(parts), tuple(controls)) if saw_string else None


def assembled_dialogue(call: Called) -> str | None:
    """Join only the verified static talk/cinematic argument grammar.

    System group 5 commands 0/6/7/19 use literal strings and integer 10 for a
    newline after the first text argument. Verified talk callbacks also admit
    non-text tail flags; command 7 retains the narrower grammar. Command 8 decodes
    its verified non-text control stream. Other operations after
    text begins may contain dynamic substitutions; they are not fabricated.
    """
    if call.kind != 3 or len(call.args) < 3 or call.args[0] != ("int", 5):
        return None
    command = call.args[1]
    if command in (("int", 0), ("int", 6), ("int", 7), ("int", 19)):
        first = next((i for i, (kind, _) in enumerate(call.args) if kind == "string"), None)
    elif command == ("int", 8):
        panel = static_panel_parts(call)
        return panel[0] if panel else None
    else:
        return None
    if first is None:
        return None
    if any(kind != "int" for kind, _ in call.args[3:first]):
        # Args[2] is the speaker/window; later variables belong to the builder.
        # Their runtime values may emit text or controls before the first literal.
        return None
    parts = []
    for kind, value in call.args[first:]:
        if kind == "string":
            parts.append(str(value))
        elif (kind, value) == ("int", 10):
            parts.append("\n")
        elif (
            command in (("int", 0), ("int", 6), ("int", 19))
            and kind == "int"
            and value in (7, 8, 9, 13, 14, 15, 16, 19, 20, 22, 24, 25, 26, 28)
        ):
            # 0x4b02d0 (talk) / 0x4b0140 (message) only set window flags
            # or return the unchanged argument index for these operations.
            continue
        else:
            return None
    return "".join(parts)


@dataclass(frozen=True)
class Function:
    name: str
    flags: int
    arg_types: tuple[int, ...]
    called: tuple[Called, ...]
    code_shape: tuple[tuple[object, ...], ...]
    code_strings: tuple[str, ...]

    def shape(self) -> tuple[object, ...]:
        return (
            self.flags,
            self.arg_types,
            tuple(call.shape() for call in self.called),
            self.code_shape,
        )

    def called_sequence_shape(self) -> tuple[object, ...]:
        """The complete static-call sequence, independent of locale bytecode layout."""
        return (self.flags, self.arg_types, tuple(call.dialogue_shape() for call in self.called))

    def dialogue_sequence_shape(self) -> tuple[object, ...]:
        # A reward/UI call can have locale-specific arguments without changing
        # any dialogue. Keep the complete dialogue order, original call indices,
        # speaker/voice identities and total call count as a separate contract.
        return (
            self.flags,
            self.arg_types,
            len(self.called),
            tuple(
                (i, call.dialogue_shape())
                for i, call in enumerate(self.called)
                if assembled_dialogue(call) is not None
            ),
        )


@dataclass(frozen=True)
class Script:
    functions: dict[str, Function]

    def shape(self) -> tuple[object, ...]:
        return tuple((name, self.functions[name].shape()) for name in sorted(self.functions))


class FpacArchive:
    """An indexed FPAC reader.  It maps game archives read-only and owns no output."""

    def __init__(self, path: Path):
        self.path = path
        self._file = path.open("rb")
        self._map = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            self.entries = self._read_entries()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self._map.close()
        self._file.close()

    def __enter__(self) -> "FpacArchive":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_entries(self) -> dict[str, tuple[int, int]]:
        data = self._map
        if len(data) < 16 or data[:4] != b"FPAC":
            raise FormatError(f"{self.path.name}: missing FPAC header")
        count, first_data, unknown = struct.unpack_from("<III", data, 4)
        if unknown != 1 or count > (len(data) - 16) // 32:
            raise FormatError(f"{self.path.name}: invalid FPAC header")
        entries: dict[str, tuple[int, int]] = {}
        for number in range(count):
            offset = 16 + number * 32
            _crc, padding, name_at, size, data_at = struct.unpack_from("<IIQQQ", data, offset)
            if padding != 0 or data_at < first_data or data_at + size > len(data):
                raise FormatError(f"{self.path.name}: invalid FPAC entry {number}")
            name = _utf8z(data, name_at)
            if name in entries:
                raise FormatError(f"{self.path.name}: duplicate FPAC path {name}")
            entries[name] = (data_at, size)
        return entries

    def read(self, name: str) -> bytes:
        offset, size = self.entries[name]
        return bytes(self._map[offset : offset + size])


def _parse_code(
    data: bytes,
    start: int,
    end: int | None,
    func_id: int,
    function_names: tuple[str, ...],
    global_names: tuple[str, ...],
    string_offsets: list[int] | None = None,
    instruction_positions: list[int] | None = None,
) -> tuple[tuple[tuple[object, ...], ...], tuple[str, ...]]:
    """Parse/normalise Ingert's SCP bytecode, retaining only text values."""
    pos = start
    extent = start
    # Keep source byte positions until all labels are known.  Branch target
    # offsets are locale-dependent addresses, but their *instruction index* is
    # semantic and must match across languages.
    result: list[tuple[int, tuple[object, ...]]] = []
    strings: list[str] = []
    while True:
        if pos >= len(data) or (end is not None and pos >= end):
            if end is not None and pos == end:
                return _normalise_code_labels(result, pos), tuple(strings)
            raise FormatError(f"bytecode ends before a valid boundary at {pos:#x}")
        op_at = pos
        if instruction_positions is not None:
            instruction_positions.append(op_at)
        opcode = data[pos]
        pos += 1
        if opcode == 0:
            if pos >= len(data) or data[pos] != 4:
                raise FormatError(f"invalid Push size at {pos:#x}")
            pos += 1
            if pos + 4 > len(data):
                raise FormatError("truncated Push")
            # PrepareCallLocal is a two-Push sequence encoded specially by SCP.
            candidate = _u32(data, pos)
            if (
                candidate == func_id
                and pos + 10 <= len(data)
                and data[pos + 4] == 0
                and data[pos + 5] == 4
                and 0 < _u32(data, pos + 6) < 0x40000000
            ):
                label = _u32(data, pos + 6)
                extent = max(extent, label)
                pos += 10
                result.append((op_at, ("prepare-local", label)))
                continue
            kind, value = _value(data, pos)
            pos += 4
            if kind == "string":
                strings.append(str(value))
                if string_offsets is not None:
                    string_offsets.append(candidate & 0x3FFFFFFF)
                result.append((op_at, ("push", "string")))
            else:
                result.append((op_at, ("push", kind, value)))
        elif opcode == 1:
            total = 0
            while True:
                if pos >= len(data):
                    raise FormatError("truncated Pop")
                value = data[pos]
                pos += 1
                total += value
                if value != 255:
                    break
                if pos >= len(data) or data[pos] != 1:
                    raise FormatError("invalid extended Pop")
                pos += 1
            if total % 4:
                raise FormatError("unaligned Pop")
            result.append((op_at, ("pop", total // 4)))
        elif opcode in (2, 3, 4, 5, 6):
            slot = _u32(data, pos)
            pos += 4
            signed = slot if slot < 0x80000000 else slot - 0x100000000
            if signed >= 0 or signed % 4:
                raise FormatError("invalid stack slot")
            result.append((op_at, ("slot", opcode, signed // -4)))
        elif opcode in (7, 8):
            global_id = _u32(data, pos)
            if global_id >= len(global_names):
                raise FormatError("invalid global id")
            result.append((op_at, ("global", opcode, global_names[global_id])))
            pos += 4
        elif opcode in (9, 10, 39):
            if pos >= len(data):
                raise FormatError("truncated one-byte opcode")
            result.append((op_at, ("byte", opcode, data[pos])))
            pos += 1
        elif opcode in (11, 14, 15, 37):
            label = _u32(data, pos)
            pos += 4
            if label == 0 or label >> 30:
                raise FormatError("invalid branch label")
            extent = max(extent, label)
            result.append((op_at, ("branch", opcode, label)))
        elif opcode == 12:
            if pos + 2 > len(data):
                raise FormatError("truncated local call")
            function_id = struct.unpack_from("<H", data, pos)[0]
            if function_id >= len(function_names):
                raise FormatError("invalid local function id")
            result.append((op_at, ("local-call", function_names[function_id])))
            pos += 2
        elif opcode == 13:
            result.append((op_at, ("return",)))
            if end is None and pos >= extent:
                return _normalise_code_labels(result, pos), tuple(strings)
        elif 16 <= opcode <= 33:
            result.append((op_at, ("op", opcode)))
        elif opcode in (34, 35):
            # These namespace/function identifiers are non-display text, but
            # are executable semantics and therefore belong in the shape.
            namespace = _string_value(data, pos)
            function = _string_value(data, pos + 4)
            if pos + 8 >= len(data):
                raise FormatError("truncated external call")
            argc = data[pos + 8]
            pos += 9
            result.append((op_at, ("external-call", opcode, namespace, function, argc)))
        elif opcode == 36:
            if pos + 3 > len(data):
                raise FormatError("truncated system call")
            result.append((op_at, ("system-call", data[pos], data[pos + 1], data[pos + 2])))
            pos += 3
        elif opcode == 38:
            if pos + 2 > len(data):
                raise FormatError("truncated line marker")
            # Op 38 is Ingert's debug/source line marker.  Preserve its opcode
            # position, but source line numbers naturally differ by locale.
            result.append((op_at, ("line",)))
            pos += 2
        else:
            raise FormatError(f"unknown SCP opcode {opcode} at {pos - 1:#x}")
        if end is not None and pos > end:
            raise FormatError("bytecode crosses its next-function boundary")
        if end is not None and pos == end:
            return _normalise_code_labels(result, pos), tuple(strings)


def _normalise_code_labels(
    positioned: list[tuple[int, tuple[object, ...]]],
    end: int,
) -> tuple[tuple[object, ...], ...]:
    targets = {position: index for index, (position, _) in enumerate(positioned)}
    targets[end] = len(positioned)
    normalised: list[tuple[object, ...]] = []
    for _, instruction in positioned:
        if instruction[0] in ("branch", "prepare-local"):
            target = instruction[-1]
            index = targets.get(target)
            if index is None:
                raise FormatError(f"branch target is not an instruction boundary: {target:#x}")
            normalised.append((*instruction[:-1], index))
        else:
            normalised.append(instruction)
    return tuple(normalised)


def parse_scp(data: bytes) -> Script:
    if len(data) < _SCP_HEADER.size:
        raise FormatError("SCP header truncated")
    magic, func_start, func_count, global_start, global_count, reserved = _SCP_HEADER.unpack_from(
        data
    )
    if magic != b"#scp" or reserved != 0 or func_count > (len(data) - func_start) // 32:
        raise FormatError("invalid SCP header")
    if global_start > len(data) or global_count > (len(data) - global_start) // 8:
        raise FormatError("invalid SCP globals range")

    raw: list[tuple[str, int, int, tuple[int, ...], int, int, int]] = []
    names: list[str] = []
    for number in range(func_count):
        at = func_start + number * 32
        (
            code_at,
            arg_count,
            flags,
            default_count,
            default_at,
            args_at,
            called_count,
            called_at,
            crc,
            name_value,
        ) = _FUNCTION.unpack_from(data, at)
        if flags & ~1 or code_at >= len(data) or called_count > (len(data) - called_at) // 12:
            raise FormatError(f"invalid function header {number}")
        name = _string_value(data, at + 28)
        if (~binascii.crc32(name.encode("utf-8")) & 0xFFFFFFFF) != crc:
            raise FormatError(f"function CRC mismatch for {name}")
        if args_at > len(data) or arg_count > (len(data) - args_at) // 4:
            raise FormatError(f"invalid argument range for {name}")
        arg_types = tuple(_u32(data, args_at + index * 4) for index in range(arg_count))
        if any((item & ~8) not in (1, 2, 5) for item in arg_types):
            raise FormatError(f"unknown argument type for {name}")
        if sum(bool(item & 8) for item in arg_types) != default_count:
            raise FormatError(f"default count mismatch for {name}")
        if default_count:
            if default_at >= len(data):
                raise FormatError(f"invalid defaults range for {name}")
            for index in range(default_count):
                _value(data, default_at + index * 4)
        raw.append((name, code_at, flags, arg_types, called_count, called_at, number))
        names.append(name)
    if len(set(names)) != len(names):
        raise FormatError("duplicate function names")

    globals_: list[str] = []
    for number in range(global_count):
        at = global_start + number * 8
        globals_.append(_string_value(data, at))
        if _u32(data, at + 4) not in (0, 1):
            raise FormatError("unknown global type")

    ordered = sorted(raw, key=lambda item: item[1])
    if len({item[1] for item in ordered}) != len(ordered):
        raise FormatError("duplicate function code offsets")
    functions: dict[str, Function] = {}
    for index, (name, code_at, flags, arg_types, called_count, called_at, number) in enumerate(
        ordered
    ):
        called: list[Called] = []
        for call_index in range(called_count):
            at = called_at + call_index * 12
            target_id, kind, arg_count, args_at = _CALLED.unpack_from(data, at)
            if kind not in (0, 1, 2, 3) or arg_count > (len(data) - args_at) // 8:
                raise FormatError(f"invalid called entry {name}/{call_index}")
            if target_id == 0xFFFFFFFF:
                target = None
            elif target_id < len(names):
                target = names[target_id]
            else:
                raise FormatError(f"invalid called target {name}/{call_index}")
            args: list[tuple[str, object | None]] = []
            for slot in range(arg_count):
                value_at = args_at + slot * 8
                value_kind = _u32(data, value_at + 4)
                if value_kind == 0:
                    value_type, value = _value(data, value_at)
                    args.append((value_type, value))
                elif value_kind in (1, 2, 3) and _u32(data, value_at) == 0:
                    args.append((("call", "var", "expr")[value_kind - 1], None))
                else:
                    raise FormatError(f"invalid called argument {name}/{call_index}/{slot}")
            called.append(Called(target, kind, tuple(args)))
        end = ordered[index + 1][1] if index + 1 < len(ordered) else None
        code_shape, code_strings = _parse_code(
            data, code_at, end, number, tuple(names), tuple(globals_)
        )
        functions[name] = Function(name, flags, arg_types, tuple(called), code_shape, code_strings)
    return Script(functions)


def _add_counter(audit: dict[str, object], key: str, amount: int = 1) -> None:
    counters = audit["counters"]
    assert isinstance(counters, Counter)
    counters[key] += amount


def _function_difference(reference: Function, candidate: Function) -> str:
    """Give the audit a bounded reason without weakening the comparison."""
    if reference.flags != candidate.flags:
        return "function flags differ"
    if reference.arg_types != candidate.arg_types:
        return "function argument signature differs"
    if len(reference.called) != len(candidate.called):
        return "called metadata count differs"
    for index, (left, right) in enumerate(zip(reference.called, candidate.called)):
        if left.shape() != right.shape():
            return f"called metadata differs at call {index}"
    if reference.code_shape != candidate.code_shape:
        return "normalised bytecode differs"
    return "function missing or structurally different"


def _logical_script_entries(archive: FpacArchive) -> dict[str, str]:
    """Remove the locale-specific FPAC root (``script_en`` -> ``script``)."""
    result: dict[str, str] = {}
    for path in archive.entries:
        root, separator, remainder = path.partition("/")
        if not separator or (root != "script" and not root.startswith("script_")):
            continue
        logical = f"script/{remainder}"
        if logical in result:
            raise FormatError(f"{archive.path.name}: duplicate logical path {logical}")
        result[logical] = path
    return result


def _script_paths(entries_by_language: Iterable[dict[str, str]]) -> list[str]:
    return sorted(
        {
            path
            for entries in entries_by_language
            for path in entries
            if path.startswith("script/") and path.endswith(".dat")
        }
    )


def _dialogue_metadata_shape(call: Called) -> tuple[object, ...] | None:
    """Normalize only actor/voice identity for a rejected static dialogue.

    This shape is never enough to pair the dialogue itself.  It only proves
    that an equal-length function did not insert, delete or reorder calls, so
    later exact calls may retain their original ordinal mapping.
    """
    if assembled_dialogue(call) is None or call.kind != 3 or len(call.args) < 2:
        return None
    if call.args[0] != ("int", 5) or call.args[1] not in tuple(
        ("int", command) for command in (0, 6, 7, 19)
    ):
        return None
    first = next(i for i, (kind, _) in enumerate(call.args) if kind == "string")
    prefix = list(call.args[:first])
    # Commands 0/6/7/19 use arg 2 as the actor/window identity when it is
    # present.  Some locale scripts omit it entirely.
    if len(prefix) > 2 and prefix[2][0] in ("int", "var"):
        del prefix[2]
    normalized = []
    index = 0
    while index < len(prefix):
        arg = prefix[index]
        normalized.append(arg)
        if arg in (("int", 11), ("int", 12)) and index + 1 < len(prefix):
            index += 1
            normalized.append((prefix[index][0], "voice"))
        index += 1
    shape = call.dialogue_shape()
    return call.target, call.kind, tuple(normalized), shape[3], "static-dialogue"


def _has_display_text(call: Called) -> bool:
    return any(call.display_text_slots())


def _speaker_payload_shape(call: Called):
    """Name text is independent of the native setter's boolean persistence flag.

    chr_set_display_name passes operation 0 to command 1/120. At 0x4784b6
    the last argument becomes actor_name_set's r8b; 0x217f90 copies the same
    rdx text unconditionally, then stores that flag at actor+0x25c6. Retain
    actor identity and reject unknown tails; this shape only aligns payloads.
    """
    if (
        call.kind != 0
        or call.target != "chr_set_display_name"
        or len(call.args) not in (2, 3)
        or call.args[0][0] != "int"
        or call.args[1][0] != "string"
    ):
        return None
    if len(call.args) == 3 and call.args[2] not in (("int", 0), ("int", 1)):
        return None
    return call.target, call.kind, call.args[0], "name-payload"


def _item_notification_metadata_shape(call: Called):
    """Align the same item event despite locale-specific prefix/suffix helpers.

    Both helper families run the same opcode-17 item resolver. The split
    family adds a localized prefix; EV's omitted style is declared as 9.
    This guards call order only; dynamic texts still use their own producer.
    """
    targets = {
        "ITEM_ADD_MESSAGE_EV": ("EV", 2),
        "ITEM_ADD_MESSAGE2_EV": ("EV", 3),
        "ITEM_ADD_MESSAGE_TK": ("TK", 2),
        "ITEM_ADD_MESSAGE2_TK": ("TK", 3),
    }
    if call.kind != 0 or call.target not in targets:
        return None
    family, required = targets[call.target]
    if (
        len(call.args) not in (required, required + (family == "EV"))
        or call.args[0][0] != "int"
        or any(arg[0] != "string" for arg in call.args[1:required])
    ):
        return None
    style = call.args[required:] or (("int", 9),) if family == "EV" else ()
    if any(kind != "int" for kind, _ in style):
        return None
    return "item-notification", family, call.args[0], style


def _same_known_payload(left: Called, right: Called) -> bool:
    for shape in (_speaker_payload_shape, _item_notification_metadata_shape):
        value = shape(left)
        if value is not None and value == shape(right):
            return True
    return False


def _optional_default_speaker_equivalent(left: Called, right: Called) -> bool:
    """Accept only command-0's explicitly encoded zero versus its omission.

    This is narrower than ``_dialogue_metadata_shape``: non-zero actors,
    voices and controls remain identity-bearing.  Some official locale scripts
    spell the default actor as argument 2 while others start the static string
    stream immediately after the command.
    """
    if left.kind != 3 or right.kind != 3 or left.target != right.target:
        return False
    if assembled_dialogue(left) is None or assembled_dialogue(right) is None:
        return False
    base = (("int", 5), ("int", 0))

    def prefix(call):
        first = next(i for i, (kind, _) in enumerate(call.args) if kind == "string")
        return call.args[:first]

    left_prefix, right_prefix = prefix(left), prefix(right)
    explicit = base + (("int", 0),)
    if {left_prefix, right_prefix} != {base, explicit}:
        return False
    left_shape, right_shape = left.dialogue_shape(), right.dialogue_shape()
    return left_shape[0:2] == right_shape[0:2] and left_shape[3:] == right_shape[3:]


def _whole_sequence_allows_default_speaker(reference: Function, candidate: Function) -> bool:
    """Prove an optional default speaker against the complete call sequence."""
    if (
        reference.flags != candidate.flags
        or reference.arg_types != candidate.arg_types
        or len(reference.called) != len(candidate.called)
    ):
        return False
    return all(
        left.dialogue_shape() == right.dialogue_shape()
        or _optional_default_speaker_equivalent(left, right)
        for left, right in zip(reference.called, candidate.called, strict=True)
    )


def _unique_non_display_gap(longer: Function, shorter: Function) -> tuple[int, int] | None:
    """Return the sole removable non-display span making both sequences exact."""
    difference = len(longer.called) - len(shorter.called)
    if difference <= 0:
        return None
    long_shapes = tuple(call.dialogue_shape() for call in longer.called)
    short_shapes = tuple(call.dialogue_shape() for call in shorter.called)
    candidates = []
    for start in range(len(shorter.called) + 1):
        end = start + difference
        if any(_has_display_text(call) for call in longer.called[start:end]):
            continue
        if long_shapes[:start] + long_shapes[end:] == short_shapes:
            candidates.append((start, end))
    return candidates[0] if len(candidates) == 1 else None


def _aligned_call_map(reference: Function, candidate: Function) -> dict[int, int]:
    """Map proven physical calls; consumers select their display record types."""
    if reference.flags != candidate.flags or reference.arg_types != candidate.arg_types:
        return {}
    reference_shapes = tuple(call.dialogue_shape() for call in reference.called)
    candidate_shapes = tuple(call.dialogue_shape() for call in candidate.called)
    mapped = {}
    if len(reference.called) == len(candidate.called):
        allow_default_speaker = _whole_sequence_allows_default_speaker(reference, candidate)
        for index, (left, right) in enumerate(zip(reference.called, candidate.called, strict=True)):
            if reference_shapes[index] == candidate_shapes[index] or _same_known_payload(
                left, right
            ):
                mapped[index] = index
                continue
            if allow_default_speaker and _optional_default_speaker_equivalent(left, right):
                mapped[index] = index
                continue
            if _dialogue_metadata_shape(left) is not None and _dialogue_metadata_shape(
                left
            ) == _dialogue_metadata_shape(right):
                # This differing dialogue keeps the sequence aligned but is
                # itself rejected because actor/voice identity is not equal.
                continue
            break
        return mapped

    prefix = 0
    while (
        prefix < min(len(reference.called), len(candidate.called))
        and reference_shapes[prefix] == candidate_shapes[prefix]
    ):
        mapped[prefix] = prefix
        prefix += 1

    if len(reference.called) < len(candidate.called):
        gap = _unique_non_display_gap(candidate, reference)
        if gap is not None:
            start, end = gap
            offset = end - start
            return {
                index: index if index < start else index + offset
                for index in range(len(reference.called))
            }
    else:
        gap = _unique_non_display_gap(reference, candidate)
        if gap is not None:
            start, end = gap
            offset = end - start
            return {
                index: index if index < start else index - offset
                for index in range(len(reference.called))
                if not start <= index < end
            }
    return mapped


def _speaker_ids(functions, called_ids):
    result = {}
    for language, called in called_ids.items():
        args = functions[language].called[called].args
        if (
            len(args) >= 3
            and args[0] == ("int", 5)
            and args[1] in (("int", 0), ("int", 6), ("int", 19))
            and args[2][0] == "int"
        ):
            result[language] = args[2][1]
    return result


def _aligned_display_records(path, function_name, functions, called_shapes, audit):
    """Join exact dialogue and speaker records across different function groups."""
    reference_language = min(functions)
    reference = functions[reference_language]
    mappings = {
        language: _aligned_call_map(reference, functions[language])
        for language in sorted(functions)
    }
    called_groups = defaultdict(set)
    dialogue_groups = defaultdict(set)
    for language, function in functions.items():
        called_groups[called_shapes[language]].add(language)
        dialogue_groups[function.dialogue_sequence_shape()].add(language)
    existing_groups = [languages for languages in called_groups.values() if len(languages) >= 2]
    existing_groups.extend(
        languages
        for shape, languages in dialogue_groups.items()
        if shape[-1]
        and len(languages) >= 2
        and len({called_shapes[language] for language in languages}) >= 2
    )
    entries = []
    for reference_called, reference_call in enumerate(reference.called):
        if (
            reference_call.target == "chr_set_display_name"
            and len(reference_call.args) >= 2
            and reference_call.args[1][0] == "string"
        ):
            called_ids = {
                language: called
                for language in sorted(functions)
                if (called := mappings[language].get(reference_called)) is not None
                and (
                    functions[language].called[called].shape() == reference_call.shape()
                    or _same_known_payload(functions[language].called[called], reference_call)
                )
            }
            languages = set(called_ids)
            if len(languages) >= 2 and not any(
                languages <= group for group in called_groups.values()
            ):
                identity = (
                    "speaker-record",
                    reference_language,
                    reference_called,
                    tuple(sorted(called_ids.items())),
                    tuple(
                        (language, functions[language].called[called].shape())
                        for language, called in sorted(called_ids.items())
                    ),
                )
                suffix = "/alignment/" + hashlib.sha256(repr(identity).encode()).hexdigest()
                entries.append(
                    {
                        "key": f"{path}/{function_name}/called/{reference_called}/arg/1{suffix}",
                        "texts": {
                            language: str(functions[language].called[called].args[1][1])
                            for language, called in called_ids.items()
                        },
                        "display_role": "speaker",
                        "called_ids": called_ids,
                    }
                )
                _add_counter(audit, "speaker_record_alignments")
        reference_text = assembled_dialogue(reference_call)
        if reference_text is None:
            continue
        called_ids = {}
        texts = {}
        for language in sorted(functions):
            called = mappings[language].get(reference_called)
            if called is None:
                continue
            call = functions[language].called[called]
            text = assembled_dialogue(call)
            if text is None or (
                call.dialogue_shape() != reference_call.dialogue_shape()
                and not _optional_default_speaker_equivalent(call, reference_call)
            ):
                continue
            called_ids[language] = called
            texts[language] = text
        languages = set(called_ids)
        if len(languages) < 2 or any(languages <= group for group in existing_groups):
            continue
        identity = (
            "called-record",
            reference_language,
            reference_called,
            tuple(sorted(called_ids.items())),
            reference_call.dialogue_shape(),
        )
        suffix = "/alignment/" + hashlib.sha256(repr(identity).encode()).hexdigest()
        key = f"{path}/{function_name}/called/{reference_called}/assembled_dialogue{suffix}"
        speaker_ids = _speaker_ids(functions, called_ids)
        entry = {
            "key": key,
            "texts": texts,
            "display_role": "dialogue",
            "called_ids": called_ids,
        }
        if speaker_ids:
            entry["speaker_ids"] = speaker_ids
        entries.append(entry)
        display = {
            language: re.sub(r"^(?:<#[^<>]*>)+", "", text) for language, text in texts.items()
        }
        if display != texts:
            display_entry = {
                **entry,
                "key": key.replace("/assembled_dialogue", "/assembled_display"),
                "texts": display,
            }
            entries.append(display_entry)
        _add_counter(audit, "assembled_dialogue_record_alignments")
        for language in texts:
            _add_counter(audit, "entries_with_" + language, 1 + (display != texts))
    return entries


def align_functions(path, function_name, functions, audit):
    """Only equal complete structural signatures may share localized records.

    Each equivalence class is independent: a damaged/missing/unrelated locale
    cannot deny a valid pair in another class, nor supply its translations.
    """
    entries = []
    called_shapes = {lang: fn.called_sequence_shape() for lang, fn in functions.items()}
    for family, method in (
        ("called", "called_sequence_shape"),
        ("code", "shape"),
        ("dialogue", "dialogue_sequence_shape"),
    ):
        if family == "dialogue" and len(set(called_shapes.values())) < 2:
            continue
        groups = {}
        for lang, fn in functions.items():
            shape = called_shapes[lang] if family == "called" else getattr(fn, method)()
            groups.setdefault(shape, []).append(lang)
        for group_index, (shape, languages) in enumerate(groups.items()):
            if family == "dialogue" and (
                not shape[-1] or len({called_shapes[l] for l in languages}) < 2
            ):
                continue
            for lang in languages:
                metric = {
                    "called": "functions_called_aligned_",
                    "code": "functions_aligned_",
                    "dialogue": "functions_dialogue_aligned_",
                }[family]
                _add_counter(audit, metric + lang)
                if group_index:
                    metric = {
                        "called": "functions_called_mismatch_",
                        "code": "functions_mismatch_",
                        "dialogue": "functions_dialogue_mismatch_",
                    }[family]
                    _add_counter(audit, metric + lang)
            if len(languages) < 2:
                _add_counter(audit, "alignment_classes_without_secondary")
                continue
            suffix = (
                "/alignment/" + hashlib.sha256(repr(shape).encode()).hexdigest()
                if len(groups) > 1
                else ""
            )
            reference = functions[languages[0]]

            def emit(key, texts, display_role=None, speaker_ids=None):
                entry = {"key": f"{path}/{function_name}/{key}" + suffix, "texts": texts}
                if display_role:
                    entry["display_role"] = display_role
                if speaker_ids:
                    entry["speaker_ids"] = speaker_ids
                entries.append(entry)
                for lang in texts:
                    _add_counter(audit, "entries_with_" + lang)

            if family == "code":
                for ordinal in range(len(reference.code_strings)):
                    emit(
                        f"code/{ordinal}",
                        {l: functions[l].code_strings[ordinal] for l in languages},
                    )
                continue
            for index, call in enumerate(reference.called):
                complete = {l: assembled_dialogue(functions[l].called[index]) for l in languages}
                if all(t is not None for t in complete.values()):
                    # The native history retains speaker names even when a
                    # saved record no longer has a live script-call identity.
                    # Keep the explicit actor argument; resolve it through the
                    # validated name table later, never through call position.
                    speaker_ids = {}
                    for language in languages:
                        args = functions[language].called[index].args
                        if (
                            len(args) >= 3
                            and args[0] == ("int", 5)
                            and args[1] in (("int", 0), ("int", 6), ("int", 19))
                            and args[2][0] == "int"
                        ):
                            speaker_ids[language] = args[2][1]
                    emit(f"called/{index}/assembled_dialogue", complete, "dialogue", speaker_ids)
                    display = {l: re.sub(r"^(?:<#[^<>]*>)+", "", t) for l, t in complete.items()}
                    if display != complete:
                        emit(f"called/{index}/assembled_display", display, "dialogue", speaker_ids)
                    _add_counter(audit, "assembled_dialogue_calls")
                if family == "dialogue":
                    continue
                slots = tuple(call.display_text_slots())
                if not slots:
                    continue
                shape = call.shape()
                slots_aligned = all(functions[l].called[index].shape() == shape for l in languages)
                for slot, _ in slots:
                    # A different wrapping/chunk boundary has no per-slot
                    # correspondence. The assembled paragraph above is exact.
                    if not slots_aligned:
                        continue
                    emit(
                        f"called/{index}/arg/{slot}",
                        {l: str(functions[l].called[index].args[slot][1]) for l in languages},
                        "speaker" if call.target == "chr_set_display_name" and slot == 1 else None,
                    )
    entries.extend(_aligned_display_records(path, function_name, functions, called_shapes, audit))
    return entries


def _build_script_paths(paths, archives, logical_entries):
    audit = {"counters": Counter(), "diagnostics": []}
    entries = []
    for path in paths:
        parsed = {}
        # Exact bytes, not a locale assumption or a truncated hash. Keep this
        # bounded to one file so large archives do not accumulate in memory.
        unique = {}
        for language, archive in archives.items():
            if path not in logical_entries[language]:
                continue
            data = archive.read(logical_entries[language][path])
            if data not in unique:
                try:
                    unique[data] = parse_scp(data)
                except FormatError as exc:
                    unique[data] = str(exc)
            result = unique[data]
            if isinstance(result, str):
                _add_counter(audit, f"scp_invalid_{language}")
                audit["diagnostics"].append({"path": path, "language": language, "reason": result})
            else:
                parsed[language] = result
        for name in sorted({name for script in parsed.values() for name in script.functions}):
            functions = {
                l: script.functions[name]
                for l, script in parsed.items()
                if name in script.functions
            }
            entries.extend(align_functions(path, name, functions, audit))
    return entries, audit


def _build_script_batch(request):
    """Process entry point: no Qt, game attachment or shared output writes."""
    game, languages, paths = request
    archives = {}
    try:
        for language in languages:
            archives[language] = FpacArchive(Path(game) / "pac/steam" / _ARCHIVES[language])
        logical = {l: _logical_script_entries(a) for l, a in archives.items()}
        return _build_script_paths(paths, archives, logical)
    finally:
        for archive in archives.values():
            archive.close()


def build_catalog(
    game_dir: str | Path, output_dir: str | Path, *, workers=None
) -> dict[str, object]:
    """Build ``catalog.json`` and ``audit.json`` from a game directory read-only."""
    game = Path(game_dir)
    output = Path(output_dir)
    audit: dict[str, object] = {
        "version": 1,
        "languages": list(LANGUAGES),
        "counters": Counter(),
        "diagnostics": [],
    }
    diagnostics = audit["diagnostics"]
    assert isinstance(diagnostics, list)
    archives: dict[str, FpacArchive] = {}
    try:
        for language, archive_name in _ARCHIVES.items():
            path = game / "pac" / "steam" / archive_name
            if not path.is_file():
                diagnostics.append(
                    {"language": language, "reason": f"missing script archive: {path}"}
                )
                continue
            archives[language] = FpacArchive(path)
        if not archives:
            raise FileNotFoundError("No script archives found")
        logical_entries = {
            language: _logical_script_entries(archive) for language, archive in archives.items()
        }
        paths = _script_paths(logical_entries.values())
        _add_counter(audit, "script_files_common", len(paths))
        entries: list[dict[str, object]] = []
        import os
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing

        if workers is None:
            workers = min(4, max(1, (os.process_cpu_count() or 1) // 2)) if len(paths) >= 16 else 1

        def collect(results):
            for batch, stats in results:
                entries.extend(batch)
                audit["counters"].update(stats["counters"])
                diagnostics.extend(stats["diagnostics"])

        if workers <= 1:
            collect([_build_script_paths(paths, archives, logical_entries)])
        else:
            # Ordered bounded results preserve output and audit order. Workers
            # own only archive reads; the parent is the sole cache writer.
            batches = [
                (str(game), tuple(archives), paths[n : n + 16]) for n in range(0, len(paths), 16)
            ]
            with ProcessPoolExecutor(
                max_workers=min(workers, 4), mp_context=multiprocessing.get_context("spawn")
            ) as pool:
                collect(pool.map(_build_script_batch, batches, buffersize=workers * 2))
        _add_counter(audit, "entries_emitted", len(entries))
        catalog = {"version": 1, "languages": list(LANGUAGES), "entries": entries}
        output.mkdir(parents=True, exist_ok=True)
        (output / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        audit["counters"] = dict(sorted(audit["counters"].items()))  # type: ignore[index]
        (output / "audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return catalog
    finally:
        for archive in archives.values():
            archive.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a validated multilingual Trails SCP catalogue"
    )
    parser.add_argument("--game-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    catalog = build_catalog(args.game_dir, args.output)
    print(f"wrote {len(catalog['entries'])} aligned text entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
