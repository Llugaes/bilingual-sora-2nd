"""Compile reviewed native dependencies, never an executable allowlist.

This developer-only compiler uses Capstone. The installed resolver needs only
pefile and hashes of the functions it actually hooks/calls. A reviewed variant
mapping supplies corresponding functions; it is not shipped as an EXE gate.
"""

import argparse
import bisect
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


class Image:
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

    def template(self, span, points, functions, globals_, *, with_chains=True, stack=()):
        start, end = span
        raw = self.pe.get_data(start, end - start)
        assert len(raw) == end - start
        masked = bytearray(raw)
        masks, links, globals_refs, continuations, equal_targets = [], [], [], [], []
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
            if span in (
                value for name, value in FONT_CONTINUATIONS.items() if name.endswith("wrapper")
            ):
                # Audited LEA/SUB image-base pairs and ADD/JMP resume RVAs.
                operands = ins.operands
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
    variant.continuations = {span[0]: (name, span) for name, span in FONT_CONTINUATIONS.items()}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--variant", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline, variant = Image(args.baseline), Image(args.variant)
    try:
        result = compile_contract(baseline, variant, json.loads(args.mapping.read_text("utf-8")))
        args.output.write_text(
            '"""Reviewed native-function contracts; metadata identifies evidence, not allowed EXEs."""\n\n'
            + "CONTRACT = "
            + pprint.pformat(result, width=100, sort_dicts=False)
            + "\n",
            "utf-8",
        )
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
