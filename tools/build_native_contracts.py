"""Compile reviewed native dependencies, never an executable allowlist.

This developer-only compiler uses Capstone. The installed resolver needs only
pefile and hashes of the functions it actually hooks/calls. A reviewed variant
mapping supplies corresponding functions; it is not shipped as an EXE gate.
"""

import argparse
import bisect
import copy
import hashlib
import json
from pathlib import Path
import pprint
import struct

import capstone
import pefile

from sora_bilingual.game.native_runtime import POINTS


BASE_GLOBALS = {
    "vtable": 0xB18490,
    "icon_callback_vtable": 0xB18458,
    "text_table_global": 0xC60E88,
    "layout_manager_global": 0xC60E88,
    "font_manager_global": 0xC60ED0,
    "font_allocator_global": 0xC60E78,
    "image_cache_global": 0xC60EF0,
    "log_owner_global": 0xC60E50,
}

# Reviewed diagnostic ABI: ECX=severity, RDX=source file, R8D=source
# line, R9=format. This evidence RVA is used only by the compiler.
BASE_DIAGNOSTIC_REPORT = 0x57C1D0
SOURCE_LINE_FUNCTIONS = {"log_write_commit", "log_record_bind", "log_rows_build"}


def diagnostic_source_line(instructions, index, functions):
    """Normalize a source line only at the reviewed diagnostic call boundary."""
    handler = functions.get("diagnostic_report")
    if handler is None or index < 1 or index + 3 >= len(instructions):
        return False
    previous, line, file_, severity, call = instructions[index - 1 : index + 4]

    def rip_lea(ins, register):
        return (
            ins.mnemonic == "lea"
            and len(ins.operands) == 2
            and ins.operands[0].type == capstone.x86.X86_OP_REG
            and ins.operands[0].reg == register
            and ins.operands[1].type == capstone.x86.X86_OP_MEM
            and ins.operands[1].mem.base == capstone.x86.X86_REG_RIP
        )

    def immediate_mov(ins, register):
        return (
            ins.mnemonic == "mov"
            and len(ins.operands) == 2
            and ins.operands[0].type == capstone.x86.X86_OP_REG
            and ins.operands[0].reg == register
            and ins.operands[1].type == capstone.x86.X86_OP_IMM
        )

    return (
        rip_lea(previous, capstone.x86.X86_REG_R9)
        and immediate_mov(line, capstone.x86.X86_REG_R8D)
        and line.imm_size == 4
        and rip_lea(file_, capstone.x86.X86_REG_RDX)
        and immediate_mov(severity, capstone.x86.X86_REG_ECX)
        and severity.operands[1].imm == 3
        and call.mnemonic == "call"
        and len(call.operands) == 1
        and call.operands[0].type == capstone.x86.X86_OP_IMM
        and call.operands[0].imm == handler[0]
    )


# Developer evidence boundaries, not allowed image identities. These are
# displaced parts of the font entry points and the helpers that preserve the
# tool's reader/path/return contract. Runtime follows references, not RVAs.
FONT_CONTINUATIONS = {
    "cache_entry_wrapper": (0xCEF080, 0xCEF0EE),
    "cache_hash_wrapper": (0xCEF0F0, 0xCEF148),
    "cache_precall_wrapper": (0xCEF150, 0xCEF1B4),
    "cache_postcall_wrapper": (0xCEF1C0, 0xCEF221),
    "file_reader_wrapper": (0xCEF230, 0xCEF29F),
    "cache_entry_helper": (0xCEFDE0, 0xCEFEF9),
    "cache_hash_helper": (0xCEFEF9, 0xCF0366),
    "cache_precall_helper": (0xCF0366, 0xCF046C),
    "cache_postcall_helper": (0xCF046C, 0xCF057F),
    "file_reader_helper": (0xCF057F, 0xCF078F),
    "absolute_path_predicate": (0xCEF36B, 0xCEF3A0),
}
FONT_CONTINUATION_BASE = 0xCEF000

# Game routines a loader helper reaches as ``image base + RVA``. Such a
# routine is compiled as that helper's own continuation, never trusted by RVA.
IMAGE_RELATIVE_CALLEES = {"cache_hash_helper": "path_hash_update"}


def crc32_table():
    """The fixed IEEE CRC-32 polynomial, independent of any evidence EXE."""
    values = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        values.append(value)
    return struct.pack("<256I", *values)


def font_continuations(base=FONT_CONTINUATION_BASE):
    """The reviewed loader layout, rebased onto one sample's loader section."""
    delta = base - FONT_CONTINUATION_BASE
    return {
        start + delta: (name, (start + delta, end + delta))
        for name, (start, end) in FONT_CONTINUATIONS.items()
    }


class Image:
    # A relinked loader carries image-base-relative RVAs in its helpers. Only
    # ``extend_contract`` turns them into verified references; the original
    # baseline/variant compilation keeps its reviewed output unchanged.
    image_relative = False
    _imports = None

    def __init__(self, path):
        self.raw = path.read_bytes()
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.pe = pefile.PE(data=self.raw, fast_load=True)
        self.pe.parse_data_directories(directories=[3])
        self.entries = {
            e.struct.BeginAddress: (e.struct.EndAddress, e.struct.UnwindData)
            for e in self.pe.DIRECTORY_ENTRY_EXCEPTION
        }
        self.functions = sorted(
            (e.struct.BeginAddress, e.struct.EndAddress) for e in self.pe.DIRECTORY_ENTRY_EXCEPTION
        )
        self.starts = [a for a, _ in self.functions]
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.continuations = {}
        self.chains = {}
        for start in self.entries:
            self.chains.setdefault(self.chain_root(start), []).append(
                (start, self.entries[start][0])
            )

    def chain_root(self, start):
        seen = set()
        while start not in seen:
            seen.add(start)
            end, unwind = self.entries[start]
            head = self.pe.get_data(unwind, 4)
            if not head[0] >> 3 & 4:
                return start
            at = unwind + 4 + ((head[2] + 1) & ~1) * 2
            start, _, _ = struct.unpack("<III", self.pe.get_data(at, 12))
        raise ValueError("Cyclic chained unwind evidence")

    def parts(self, span):
        if span[0] not in self.entries:
            return []
        return [row for row in self.chains[self.chain_root(span[0])] if row != span]

    def function_link(self, target, functions):
        # Include CHAININFO fragments belonging to directly used functions.
        for key, (begin, limit) in functions.items():
            if begin <= target < limit:
                return {"function": key, "addend": target - begin}
        for key, span in functions.items():
            if any(a <= target < b for a, b in self.parts(span)):
                return {"function": key, "addend": target - span[0]}
        return None

    def owner(self, point):
        index = bisect.bisect_right(self.starts, point) - 1
        if index >= 0:
            span = self.functions[index]
            if span[0] <= point < span[1]:
                return span
        return None

    def leaf(self, point):
        for ins in self.md.disasm(self.pe.get_data(point, 4096), point):
            if ins.mnemonic == "int3":
                return point, ins.address
        raise ValueError(f"No reviewed leaf extent at {point:x}")

    def import_at(self, slot):
        if self._imports is None:
            self.pe.parse_data_directories(directories=[1])
            base = self.pe.OPTIONAL_HEADER.ImageBase
            self._imports = {
                row.address - base: (entry.dll.decode("ascii"), row.name.decode("ascii"))
                for entry in getattr(self.pe, "DIRECTORY_ENTRY_IMPORT", [])
                for row in entry.imports
                if row.name
            }
        return self._imports.get(slot)

    def in_image(self, value):
        return self.pe.sections[0].VirtualAddress <= value < self.pe.OPTIONAL_HEADER.SizeOfImage

    @staticmethod
    def reaches_call(instructions, register):
        """True when ``register`` is next used, unmodified, as an indirect CALL target."""
        for ins in instructions:
            if ins.mnemonic == "call":
                return (
                    ins.operands[0].type == capstone.x86.X86_OP_REG
                    and ins.operands[0].reg == register
                )
            if ins.mnemonic.startswith(("j", "ret")) or register in ins.regs_access()[1]:
                return False
        return False

    def rip_references(self, span):
        start, end = span
        for ins in self.md.disasm(self.pe.get_data(start, end - start), start):
            for operand in ins.operands:
                if (
                    operand.type == capstone.x86.X86_OP_MEM
                    and operand.mem.base == capstone.x86.X86_REG_RIP
                ):
                    offset = ins.address - start
                    yield (
                        [offset + ins.disp_offset, ins.disp_size],
                        offset + ins.size,
                        ins.address + ins.size + operand.mem.disp,
                    )

    def template(self, span, points, functions, globals_, *, with_chains=True, stack=()):
        start, end = span
        raw = self.pe.get_data(start, end - start)
        assert len(raw) == end - start
        masked = bytearray(raw)
        masks, links, globals_refs, continuations, equal_targets = [], [], [], [], []
        imports, shared_data, callees, data_refs = [], [], {}, []
        role, known = self.continuations.get(start, ("", None))
        role = role if known == span else ""
        wrapper = role.endswith("wrapper")
        helper = self.image_relative and role.endswith("helper")
        consumed = 0
        instructions = list(self.md.disasm(raw, start))
        source_line_function = any(
            name in SOURCE_LINE_FUNCTIONS and span == function_span
            for name, function_span in functions.items()
        )
        for index, ins in enumerate(instructions):
            offset = ins.address - start
            consumed = offset + ins.size
            if source_line_function and diagnostic_source_line(instructions, index, functions):
                # The full instruction sequence remains hashed. Its CALL
                # gets the normal explicit link to diagnostic_report below;
                # only the ABI's non-rendering source-line immediate varies.
                at, width = offset + ins.imm_offset, ins.imm_size
                masks.append([at, width])
                masked[at : at + width] = bytes(width)
            for operand in ins.operands:
                kind = None
                if (
                    operand.type == capstone.x86.X86_OP_MEM
                    and operand.mem.base == capstone.x86.X86_REG_RIP
                ):
                    kind = "rip"
                    at, width = offset + ins.disp_offset, ins.disp_size
                    target = ins.address + ins.size + operand.mem.disp
                elif (
                    ins.mnemonic in ("call", "jmp")
                    and operand.type == capstone.x86.X86_OP_IMM
                    and not start <= operand.imm < end
                ):
                    kind = "branch"
                    at, width, target = offset + ins.imm_offset, ins.imm_size, operand.imm
                if kind is None:
                    continue
                assert width in (1, 2, 4, 8)
                masks.append([at, width])
                masked[at : at + width] = bytes(width)
                ref = {"displacement": [at, width], "next": consumed}
                if kind == "rip":
                    for name, rva in globals_.items():
                        if target == rva:
                            globals_refs.append({"name": name, **ref})
                else:
                    link = self.function_link(target, functions)
                    if (
                        link
                        and link["function"] == "diagnostic_report"
                        and not source_line_function
                    ):
                        link = None
                    if link:
                        links.append({**ref, **link})
                    elif target in self.continuations:
                        name, child_span = self.continuations[target]
                        assert target not in stack, ("cyclic continuation", name)
                        child = self.template(
                            child_span,
                            {},
                            functions,
                            globals_,
                            with_chains=False,
                            stack=(*stack, start),
                        )
                        child.pop("points")
                        continuations.append({**ref, "name": name, "template": child})
            if helper:
                operands = ins.operands
                for operand in operands:
                    # ``[image base + RVA]``: stack frames and the loader's
                    # own RIP-relative state are not image references.
                    if (
                        operand.type != capstone.x86.X86_OP_MEM
                        or operand.mem.base
                        in (
                            capstone.x86.X86_REG_INVALID,
                            capstone.x86.X86_REG_RIP,
                            capstone.x86.X86_REG_RSP,
                            capstone.x86.X86_REG_RBP,
                        )
                        or not self.in_image(operand.mem.disp)
                    ):
                        continue
                    at, width = offset + ins.disp_offset, ins.disp_size
                    assert width == 4
                    imported = self.import_at(operand.mem.disp)
                    if imported and operand.mem.index == capstone.x86.X86_REG_INVALID:
                        imports.append(
                            {
                                "displacement": [at, width],
                                "encoding": "rva32",
                                "dll": imported[0],
                                "name": imported[1],
                            }
                        )
                    else:
                        # A scaled table read is accepted only when a callee
                        # compiled below reads the very same table.
                        assert operand.mem.index != capstone.x86.X86_REG_INVALID, (
                            "unreviewed image-relative operand",
                            hex(ins.address),
                        )
                        assert role == "cache_hash_helper" and operand.mem.scale == 4, (
                            "unreviewed helper data read",
                            hex(ins.address),
                        )
                        shared_data.append(([at, width], operand.mem.disp))
                    masks.append([at, width])
                    masked[at : at + width] = bytes(width)
                if (
                    ins.mnemonic == "add"
                    and len(operands) == 2
                    and operands[0].type == capstone.x86.X86_OP_REG
                    and operands[1].type == capstone.x86.X86_OP_IMM
                    and self.in_image(operands[1].imm)
                    and self.reaches_call(instructions[index + 1 :], operands[0].reg)
                ):
                    name = IMAGE_RELATIVE_CALLEES[role]
                    target = operands[1].imm
                    child_span = self.owner(target) or self.leaf(target)
                    assert child_span[0] == target, ("call into a function body", hex(target))
                    assert name not in callees and start not in stack
                    child = self.template(
                        child_span,
                        {},
                        functions,
                        globals_,
                        with_chains=False,
                        stack=(*stack, start),
                    )
                    child.pop("points")
                    at, width = offset + ins.imm_offset, ins.imm_size
                    assert width == 4
                    masks.append([at, width])
                    masked[at : at + width] = bytes(width)
                    callees[name] = child_span
                    continuations.append(
                        {
                            "displacement": [at, width],
                            "encoding": "rva32",
                            "name": name,
                            "template": child,
                        }
                    )
            if wrapper:
                # Audited resume addresses: a direct LEA/JMP, or LEA/SUB
                # image-base pairs followed by ADD/JMP resume RVAs.
                operands = ins.operands
                if (
                    ins.mnemonic == "lea"
                    and len(operands) == 2
                    and operands[1].type == capstone.x86.X86_OP_MEM
                    and operands[1].mem.base == capstone.x86.X86_REG_RIP
                ):
                    following = next(
                        (row for row in instructions[index + 1 :] if row.mnemonic != "nop"), None
                    )
                    if (
                        following
                        and following.mnemonic == "jmp"
                        and following.operands[0].type == capstone.x86.X86_OP_REG
                        and following.operands[0].reg == operands[0].reg
                    ):
                        # Flag-preserving resume: the address is loaded in
                        # one LEA instead of the SUB/ADD image-base pair.
                        target = ins.address + ins.size + operands[1].mem.disp
                        link = self.function_link(target, functions)
                        assert link, ("unresolved continuation return", ins.address)
                        links.append(
                            {
                                "displacement": [offset + ins.disp_offset, ins.disp_size],
                                "next": offset + ins.size,
                                **link,
                            }
                        )
                if (
                    ins.mnemonic == "sub"
                    and len(operands) == 2
                    and operands[1].type == capstone.x86.X86_OP_IMM
                ):
                    previous = instructions[index - 1] if index else None
                    if (
                        previous
                        and previous.mnemonic == "lea"
                        and previous.operands[0].reg == operands[0].reg
                        and previous.operands[1].type == capstone.x86.X86_OP_MEM
                        and previous.operands[1].mem.base == capstone.x86.X86_REG_RIP
                    ):
                        target = previous.address + previous.size + previous.operands[1].mem.disp
                        assert target == operands[1].imm
                        at, width = offset + ins.imm_offset, ins.imm_size
                        assert width == 4
                        masks.append([at, width])
                        masked[at : at + width] = bytes(width)
                        equal_targets.append(
                            {
                                "left": {
                                    "displacement": [
                                        previous.address - start + previous.disp_offset,
                                        previous.disp_size,
                                    ],
                                    "next": previous.address - start + previous.size,
                                },
                                "right": {"displacement": [at, width], "encoding": "rva32"},
                            }
                        )
                if (
                    ins.mnemonic == "add"
                    and len(operands) == 2
                    and operands[1].type == capstone.x86.X86_OP_IMM
                ):
                    following = instructions[index + 1] if index + 1 < len(instructions) else None
                    if (
                        following
                        and following.mnemonic == "jmp"
                        and following.operands[0].type == capstone.x86.X86_OP_REG
                        and following.operands[0].reg == operands[0].reg
                    ):
                        link = self.function_link(operands[1].imm, functions)
                        assert link, ("unresolved continuation return", ins.address)
                        at, width = offset + ins.imm_offset, ins.imm_size
                        assert width == 4
                        masks.append([at, width])
                        masked[at : at + width] = bytes(width)
                        links.append({"displacement": [at, width], "encoding": "rva32", **link})
        assert consumed == len(raw), (span, consumed, len(raw))
        for displacement, target in shared_data:
            shared = [
                (name, reference)
                for name, child_span in callees.items()
                for reference in self.rip_references(child_span)
                if reference[2] == target
            ]
            assert len(shared) == 1, ("table is not the one a reviewed callee reads", hex(target))
            name, (callee_displacement, callee_next, _target) = shared[0]
            expected = crc32_table()
            assert target % 4 == 0 and self.pe.get_data(target, len(expected)) == expected, (
                "path hash table is not the reviewed IEEE CRC-32 table",
                hex(target),
            )
            data_refs.append(
                {
                    "displacement": displacement,
                    "encoding": "rva32",
                    "size": len(expected),
                    "alignment": 4,
                    "sha256": hashlib.sha256(expected).hexdigest(),
                }
            )
            child = next(ref["template"] for ref in continuations if ref["name"] == name)
            child.setdefault("data_refs", []).append(
                {
                    "displacement": callee_displacement,
                    "next": callee_next,
                    "size": len(expected),
                    "alignment": 4,
                    "sha256": hashlib.sha256(expected).hexdigest(),
                }
            )
            equal_targets.append(
                {
                    "left": {"displacement": displacement, "encoding": "rva32"},
                    "right": {
                        "continuation": name,
                        "displacement": callee_displacement,
                        "next": callee_next,
                    },
                }
            )
        result = {
            "size": len(raw),
            "sha256": hashlib.sha256(masked).hexdigest(),
            "masks": sorted(masks),
            "points": {name: rva - start for name, rva in points.items()},
            "links": links,
            "globals": globals_refs,
        }
        if continuations:
            result["continuations"] = continuations
        if equal_targets:
            result["equal_targets"] = equal_targets
        if imports:
            result["imports"] = imports
        if data_refs:
            result["data_refs"] = data_refs
        if with_chains and self.parts(span):
            result["chained"] = []
            for part in self.parts(span):
                child = self.template(part, {}, functions, globals_, with_chains=False)
                child.pop("points")
                # The CPU may fall through into this fragment. Unordered
                # unwind membership alone must not validate an unused clone.
                child["offset"] = part[0] - start
                result["chained"].append(child)
        return result

    def rtti(self, vtable):
        locator = (
            struct.unpack("<Q", self.pe.get_data(vtable - 8, 8))[0]
            - self.pe.OPTIONAL_HEADER.ImageBase
        )
        signature, offset, cd_offset, descriptor, _, _ = struct.unpack(
            "<6I", self.pe.get_data(locator, 24)
        )
        assert (signature, offset, cd_offset) == (1, 0, 0)
        return self.pe.get_string_at_rva(descriptor + 16).decode("ascii")


def compile_contract(baseline, variant, mapping):
    assert baseline.digest == mapping["old_sha256"]
    assert variant.digest == mapping["new_sha256"]
    variant.continuations = font_continuations()
    points = {**POINTS, "font_file_read": 0x654640}
    rows = {row["name"]: row for row in mapping["points"]}
    assert set(points) == set(rows)
    groups = {}
    for name, rva in points.items():
        row = rows[name]
        assert row["old_rva"] == rva
        span = baseline.owner(rva) or baseline.leaf(rva)
        assert span == tuple(row["old_function"])
        groups.setdefault(span, {})[name] = rva
    old_functions = {next(iter(names)): span for span, names in groups.items()}
    new_functions = {key: tuple(rows[key]["new_function"]) for key in old_functions}
    old_diagnostic = baseline.owner(BASE_DIAGNOSTIC_REPORT)
    assert old_diagnostic and old_diagnostic[0] == BASE_DIAGNOSTIC_REPORT
    diagnostic_template = baseline.template(old_diagnostic, {}, {}, {})
    diagnostic_candidates = [
        span
        for span in variant.functions
        if span[1] - span[0] == diagnostic_template["size"]
        and variant.template(span, {}, {}, {}) == diagnostic_template
    ]
    assert len(diagnostic_candidates) == 1, "Diagnostic dependency is not unique"
    old_functions["diagnostic_report"] = old_diagnostic
    new_functions["diagnostic_report"] = diagnostic_candidates[0]
    groups[old_diagnostic] = {}
    new_globals = {}
    for row in mapping["global_dependencies"]:
        assert len(row["new_candidates"]) == 1
        for name in row["name"].split("/"):
            assert BASE_GLOBALS[name] == row["old_rva"]
            new_globals[name] = row["new_candidates"][0]
    assert set(new_globals) == set(BASE_GLOBALS)
    contract = {"schema": 1, "functions": {}, "global_specs": {}}
    for key, old_span in old_functions.items():
        old_points = groups[old_span]
        new_points = {name: rows[name]["new_rva"] for name in old_points}
        span = new_functions[key]
        assert all(span[0] <= rva < span[1] for rva in new_points.values())
        old = baseline.template(old_span, old_points, old_functions, BASE_GLOBALS)
        new = variant.template(span, new_points, new_functions, new_globals)
        variants = [old] if old == new else [old, new]
        contract["functions"][key] = {
            "leaf": baseline.owner(old_span[0]) is None,
            "variants": variants,
        }
    for name in BASE_GLOBALS:
        # We read these pointers; only the game writes the manager globals.
        spec = {"alignment": 8, "writable": False}
        if name in ("vtable", "icon_callback_vtable"):
            spec["rtti"] = baseline.rtti(BASE_GLOBALS[name])
            assert spec["rtti"] == variant.rtti(new_globals[name])
        contract["global_specs"][name] = spec
    referenced = {
        link["function"]
        for row in contract["functions"].values()
        for v in row["variants"]
        for link in v["links"]
    }
    assert all(not row["leaf"] or key in referenced for key, row in contract["functions"].items())
    # Provenance only. The runtime must never compare these EXE identities.
    contract["metadata"] = {
        "baseline_evidence_sha256": baseline.digest,
        "variant_evidence_sha256": variant.digest,
        "review": "docs/verification/exe-compatibility.md",
        "point_count": len(points),
    }
    return contract


def extend_contract(contract, sample):
    """Verify relocation against reviewed bodies; never learn unknown code.

    Address normalization should make a relinked sample compile to an existing
    template. A different continuation body needs an independent review and
    explicit contract edit, rather than a production bypass in this compiler.
    """
    from sora_bilingual.game.native_contracts import resolve_native_contracts

    resolved = resolve_native_contracts(sample.pe, contract)
    starts = resolved["functions"]
    # Product modules are independently reviewed and already verified above.
    # Preserve them verbatim; their extra global aliases must not alter the
    # original compiler's interpretation of the same baseline instructions.
    from sora_bilingual.game.shop_contract_data import SHOP_FUNCTIONS, SHOP_GLOBAL_SPECS
    from sora_bilingual.game.tips_contract_data import TIPS_FUNCTIONS, TIPS_GLOBAL_SPECS

    product_functions = set(SHOP_FUNCTIONS) | set(TIPS_FUNCTIONS)
    product_globals = set(SHOP_GLOBAL_SPECS) | set(TIPS_GLOBAL_SPECS)
    compiler_globals = {
        name: target for name, target in resolved["globals"].items() if name not in product_globals
    }
    spans = {
        name: (start, sample.entries[start][0]) if start in sample.entries else sample.leaf(start)
        for name, start in starts.items()
        if name not in product_functions
    }
    bases = set()
    for name, row in contract["functions"].items():
        for variant in row["variants"]:
            body = bytearray(sample.pe.get_data(starts[name], variant["size"]))
            for at, width in variant["masks"]:
                body[at : at + width] = bytes(width)
            if hashlib.sha256(body).hexdigest() != variant["sha256"]:
                continue
            for ref in variant.get("continuations", []):
                if ref.get("name") not in FONT_CONTINUATIONS:
                    continue
                at, width = ref["displacement"]
                raw = sample.pe.get_data(starts[name] + at, width)
                target = starts[name] + ref["next"] + int.from_bytes(raw, "little", signed=True)
                bases.add(FONT_CONTINUATION_BASE + target - FONT_CONTINUATIONS[ref["name"]][0])
    assert len(bases) <= 1, ("loader continuations do not share the reviewed layout", bases)
    if bases:
        sample.continuations = font_continuations(bases.pop())
    sample.image_relative = True
    for name, row in contract["functions"].items():
        if name in product_functions:
            continue
        points = {point for variant in row["variants"] for point in variant["points"]}
        template = sample.template(
            spans[name],
            {point: resolved["points"][point] for point in points},
            spans,
            compiler_globals,
        )
        assert template in row["variants"], ("unreviewed template requires explicit audit", name)
    return []


def write_contract(path, contract, *, include_product_contracts=False):
    path.write_text(
        '"""Reviewed native-function contracts; metadata identifies evidence, not allowed EXEs."""\n\n'
        + "CONTRACT = "
        + pprint.pformat(contract, width=100, sort_dicts=False)
        + "\n"
        + (
            "\nfrom sora_bilingual.game.shop_contract_data import SHOP_FUNCTIONS, SHOP_GLOBAL_SPECS\n"
            'CONTRACT["functions"].update(SHOP_FUNCTIONS)\n'
            'CONTRACT["global_specs"].update(SHOP_GLOBAL_SPECS)\n'
            "\nfrom sora_bilingual.game.tips_contract_data import TIPS_FUNCTIONS, TIPS_GLOBAL_SPECS\n"
            'CONTRACT["functions"].update(TIPS_FUNCTIONS)\n'
            'CONTRACT["global_specs"].update(TIPS_GLOBAL_SPECS)\n'
            if include_product_contracts
            else ""
        ),
        "utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--variant", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument(
        "--extend",
        type=Path,
        action="append",
        default=[],
        help="verify a relocated sample recompiles to reviewed templates; never learn bodies",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.extend:
        if args.baseline or args.variant or args.mapping:
            parser.error("--extend starts from the committed contract, not from evidence images")
        from sora_bilingual.game.native_contract_data import CONTRACT

        result, added = copy.deepcopy(CONTRACT), {}
        for path in args.extend:
            sample = Image(path)
            try:
                added[sample.digest] = extend_contract(result, sample)
            finally:
                sample.pe.close()
        write_contract(args.output, result, include_product_contracts=True)
        print(json.dumps({"added_variants": added, "output": str(args.output)}))
        return
    if not (args.baseline and args.variant and args.mapping):
        parser.error("--baseline, --variant and --mapping are required without --extend")
    baseline, variant = Image(args.baseline), Image(args.variant)
    try:
        result = compile_contract(baseline, variant, json.loads(args.mapping.read_text("utf-8")))
        write_contract(args.output, result, include_product_contracts=True)
        print(
            json.dumps(
                {
                    "functions": len(result["functions"]),
                    "points": result["metadata"]["point_count"],
                    "output": str(args.output),
                }
            )
        )
    finally:
        baseline.pe.close()
        variant.pe.close()


if __name__ == "__main__":
    main()
