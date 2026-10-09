"""Compile the reviewed shop resource-key -> owned-copy boundary contracts.

Only reads EXE samples. Requires identical normalized instruction/data/link
contracts across every supplied reviewed sample. Output contains hashes, not
game code, and is included in the normal resident contract and revision.
"""

import argparse
import hashlib
import pprint
import re
import struct
from pathlib import Path

import capstone

from tools.build_native_contracts import Image
from sora_bilingual.game.native_contracts import resolve_native_contracts


def compile_sample(path):
    image = Image(path)
    try:
        resolved = resolve_native_contracts(image.pe)
        data = image.pe.get_memory_mapped_image()
        target = data.find(b"TXT_SHOP_CUSTOMIZE_YES\0") + 1
        references = []
        for section in image.pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            code = section.get_data()
            for match in re.finditer(b"\x48\x8d\x0d", code):
                at = match.start()
                rva = section.VirtualAddress + at
                if rva + 7 + struct.unpack_from("<i", code, at + 3)[0] == target:
                    references.append(rva)
        assert len(references) == 1, "shop resource selector must be unique"
        owner = image.owner(references[0])
        assert owner and owner[1] - owner[0] == 596, "unreviewed shop control flow"
        instructions = list(
            image.md.disasm(image.pe.get_data(owner[0], owner[1] - owner[0]), owner[0])
        )

        def calls_after(operand, mnemonic=None):
            return [
                ins
                for n, ins in enumerate(instructions)
                if ins.mnemonic == "call"
                and ins.operands[0].type == capstone.x86.X86_OP_IMM
                and n
                and instructions[n - 1].op_str == operand
                and (mnemonic is None or instructions[n - 1].mnemonic == mnemonic)
            ]

        copies = calls_after("rcx, rdi")
        assert len(copies) == 2 and all(
            c.operands[0].imm == resolved["functions"]["set_text"] for c in copies
        )
        points = {
            "shop_yes_copy_return": copies[0].address + copies[0].size,
            "shop_no_copy_return": copies[1].address + copies[1].size,
        }
        assert tuple(v - owner[0] for v in points.values()) == (438, 507)
        fmt_calls = calls_after("rcx, [rsp + 0x20]", "lea")
        assert len(fmt_calls) == 2 and fmt_calls[0].operands[0].imm == fmt_calls[1].operands[0].imm
        formatter = image.owner(fmt_calls[0].operands[0].imm)
        assert formatter
        fmt = list(
            image.md.disasm(
                image.pe.get_data(formatter[0], formatter[1] - formatter[0]), formatter[0]
            )
        )
        engine = next(
            i.operands[0].imm
            for i in fmt
            if i.mnemonic == "call"
            and i.operands[0].type == capstone.x86.X86_OP_IMM
            and i.address > formatter[0] + 0x80
        )
        direct_fmt_calls = [
            i for i in fmt if i.mnemonic == "call" and i.operands[0].type == capstone.x86.X86_OP_IMM
        ]
        assert [i.address - formatter[0] for i in direct_fmt_calls] == [50, 79, 104, 147]
        managers = [
            i
            for i in instructions
            if i.mnemonic == "mov"
            and i.op_str.startswith("rax, qword ptr [rip")
            and i.address >= owner[0] + 381
        ]
        assert [i.address - owner[0] for i in managers] == [381, 451]
        manager_targets = [i.address + i.size + i.operands[1].mem.disp for i in managers]
        assert len(set(manager_targets)) == 1
        globals_ = {**resolved["globals"], "shop_text_owner_global": manager_targets[0]}
        lookup = calls_after("edx, esi")[0].operands[0].imm
        # These predicates choose trade/create; preserve their actual calls,
        # not just address masks in the caller. RCX is the same native owner.
        predicates = calls_after("rcx, rbp")
        assert len(predicates) == 2
        key_hash = next(
            i.operands[0].imm
            for i in instructions
            if i.mnemonic == "call"
            and i.operands[0].type == capstone.x86.X86_OP_IMM
            and i.address > owner[0] + 0x40
        )
        starts = {
            "shop_action_copy": owner[0],
            "shop_printf": formatter[0],
            "shop_printf_engine": engine,
            "shop_text_lookup": lookup,
            "shop_key_hash": key_hash,
            "shop_trade_mode": predicates[0].operands[0].imm,
            "shop_create_mode": predicates[1].operands[0].imm,
            "shop_printf_length": direct_fmt_calls[0].operands[0].imm,
            "shop_printf_copy": direct_fmt_calls[1].operands[0].imm,
            "shop_printf_options": direct_fmt_calls[2].operands[0].imm,
        }
        spans = {k: image.owner(v) or image.leaf(v) for k, v in starts.items()}
        for name, global_name, expected_count in (
            ("shop_printf_length", "shop_strlen_cpu_flags", 2),
            ("shop_printf_options", "shop_printf_options_global", 1),
        ):
            span = spans[name]
            targets = [
                ins.address + ins.size + op.mem.disp
                for ins in image.md.disasm(image.pe.get_data(span[0], span[1] - span[0]), span[0])
                for op in ins.operands
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP
            ]
            assert len(targets) == expected_count and len(set(targets)) == 1
            globals_[global_name] = targets[0]
        functions = {
            **{k: image.owner(v) or image.leaf(v) for k, v in resolved["functions"].items()},
            **spans,
        }
        result = {}
        for name, span in spans.items():
            template = image.template(
                span, points if name == "shop_action_copy" else {}, functions, globals_
            )
            # Input-key literals and the formatter's initial empty string are
            # required data, unlike unrelated addresses. Bind their contents.
            refs = []
            for ins in image.md.disasm(image.pe.get_data(span[0], span[1] - span[0]), span[0]):
                for op in ins.operands:
                    if (
                        ins.mnemonic == "lea"
                        and op.type == capstone.x86.X86_OP_MEM
                        and op.mem.base == capstone.x86.X86_REG_RIP
                    ):
                        dest = ins.address + ins.size + op.mem.disp
                        end = data.find(b"\0", dest)
                        if name == "shop_key_hash":
                            payload = data[dest : dest + 1024]
                            assert len(payload) == 1024
                            refs.append(
                                {
                                    "displacement": [
                                        ins.address - span[0] + ins.disp_offset,
                                        ins.disp_size,
                                    ],
                                    "next": ins.address - span[0] + ins.size,
                                    "size": 1024,
                                    "sha256": hashlib.sha256(payload).hexdigest(),
                                }
                            )
                        elif name == "shop_action_copy" or name == "shop_printf":
                            assert 0 <= dest < end + 1 <= len(data) and end - dest < 256
                            payload = data[dest : end + 1]
                            refs.append(
                                {
                                    "displacement": [
                                        ins.address - span[0] + ins.disp_offset,
                                        ins.disp_size,
                                    ],
                                    "next": ins.address - span[0] + ins.size,
                                    "size": len(payload),
                                    "sha256": hashlib.sha256(payload).hexdigest(),
                                }
                            )
            if refs:
                template["data_refs"] = refs
            result[name] = {"leaf": image.owner(span[0]) is None, "variants": [template]}
        assert len(result["shop_action_copy"]["variants"][0]["globals"]) == 2
        return result, {
            "sha256": image.digest,
            "functions": spans,
            "points": points,
            "shop_text_owner_global": manager_targets[0],
        }
    finally:
        image.pe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [compile_sample(path) for path in args.sample]
    contract = results[0][0]
    assert all(result[0] == contract for result in results), (
        "sample behavior changed; requires separate review"
    )
    args.output.write_text(
        '"""Reviewed shop choice ownership contracts; sample hashes are provenance only."""\n\n'
        + "SHOP_FUNCTIONS = "
        + pprint.pformat(contract, width=100, sort_dicts=False)
        + "\n\nSHOP_GLOBAL_SPECS = "
        + pprint.pformat(
            {
                "shop_text_owner_global": {"alignment": 8, "writable": True},
                "shop_strlen_cpu_flags": {"alignment": 4, "writable": True},
                "shop_printf_options_global": {"alignment": 8, "writable": True},
            },
            width=100,
            sort_dicts=False,
        )
        + "\n",
        "utf-8",
    )
    print(pprint.pformat([result[1] for result in results], width=100))


if __name__ == "__main__":
    main()
