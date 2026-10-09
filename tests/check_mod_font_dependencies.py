"""Static MOD/voice PE regression. Never executes, installs or attaches a game."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pefile
from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
from sora_bilingual.game.native_runtime import native_report
from sora_bilingual.game import native_contracts as nc
from sora_bilingual.game.native_contract_data import CONTRACT


def helper_at(pe, name, wrapper_name, helper_name):
    matches = []
    for variant in CONTRACT["functions"][name]["variants"]:
        if not variant.get("continuations"):
            continue
        for start, end, _ in nc._exception_entries(pe):
            if end - start == variant["size"] and nc._variant_matches(pe, start, variant):
                wrapper = next(r for r in variant["continuations"] if r["name"] == wrapper_name)
                wrapper_start = nc._reference_target(pe, start, wrapper)
                helper = next(
                    r for r in wrapper["template"]["continuations"] if r["name"] == helper_name
                )
                address = nc._reference_target(pe, wrapper_start, helper)
                if nc._variant_matches(pe, address, helper["template"]):
                    matches.append(address)
    assert len(set(matches)) == 1, "dependency must be uniquely located"
    return matches[0]


def check(path, temporary):
    original = path.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    report = native_report(path)
    assert len(report["native"]) == 70  # 1.0 also retains Shop/Tips takeover points.
    with pefile.PE(data=original, fast_load=True) as pe:
        hash_helper = helper_at(
            pe, "font_image_read_call", "cache_hash_wrapper", "cache_hash_helper"
        )
        reader = helper_at(pe, "font_file_read", "file_reader_wrapper", "file_reader_helper")
        # These operand offsets come from the independently reviewed native
        # instruction boundaries. They are not fetched from dependency metadata.
        table = int.from_bytes(pe.get_data(hash_helper + 831, 4), "little")
        tail = int.from_bytes(pe.get_data(hash_helper + 837, 4), "little")
        slot = int.from_bytes(pe.get_data(reader + 181, 4), "little")
        crc_table = tail + 20 + int.from_bytes(pe.get_data(tail + 16, 4), "little", signed=True)
        assert crc_table == table
        pe.parse_data_directories(directories=[1])
        imports = [
            i
            for d in pe.DIRECTORY_ENTRY_IMPORT
            for i in d.imports
            if i.address - pe.OPTIONAL_HEADER.ImageBase == slot
        ]
        assert len(imports) == 1 and imports[0].name == b"GetCurrentThreadId"
        name_rva = imports[0].hint_name_table_rva
        mutations = {}

        def flip(case, rva, mask=1):
            changed = bytearray(original)
            changed[pe.get_offset_from_rva(rva)] ^= mask
            mutations[case] = changed

        for case, rva in [
            ("hash helper register", hash_helper + 829),
            ("hash table operand", hash_helper + 831),
            ("hash callee operand", hash_helper + 837),
            ("hash helper allocation stride", hash_helper + 735),
            ("hash helper cache field", hash_helper + 861),
            ("hash helper branch", hash_helper + 756),
            ("crc table content", table + 37),
            ("crc callee register", tail + 3),
            ("crc callee table displacement", tail + 16),
            ("reader IAT operand", reader + 181),
            ("reader register", reader + 179),
            ("IAT symbol", name_rva + 2),
        ]:
            flip(case, rva)
        changed = bytearray(original)
        section = next(
            s
            for s in pe.sections
            if s.VirtualAddress <= table < s.VirtualAddress + s.Misc_VirtualSize
        )
        struct.pack_into(
            "<I",
            changed,
            section.get_field_absolute_offset("Characteristics"),
            section.Characteristics | 0x80000000,
        )
        mutations["CRC constant data made writable"] = changed
        # A prior exact helper must not revive unsafe address operands when
        # the rest of this image has the relocated reader variant.
        changed = bytearray(original)
        struct.pack_into("<I", changed, pe.get_offset_from_rva(hash_helper + 831), 0x7FFFFFF0)
        mutations["CRC table outside image"] = changed
        changed = bytearray(original)
        struct.pack_into("<I", changed, pe.get_offset_from_rva(hash_helper + 837), tail + 1)
        mutations["indirect callee interior entry"] = changed
        peer_table, peer_tail, peer_slot = (
            (0xA92640, 0x5B180, 0x8BA098) if table == 0xA93640 else (0xA93640, 0x5B3C0, 0x8BB098)
        )
        changed = bytearray(original)
        struct.pack_into("<I", changed, pe.get_offset_from_rva(hash_helper + 831), peer_table)
        struct.pack_into("<I", changed, pe.get_offset_from_rva(hash_helper + 837), peer_tail)
        mutations["exact peer helper cannot revive foreign CRC operands"] = changed
        changed = bytearray(original)
        struct.pack_into("<I", changed, pe.get_offset_from_rva(reader + 181), peer_slot)
        mutations["exact peer reader cannot revive foreign IAT operand"] = changed
        outcomes = []
        for case, changed in mutations.items():
            temporary.write_bytes(changed)
            try:
                native_report(temporary)
            except ExecutableCompatibilityError as error:
                outcomes.append(
                    {"case": case, "rejected": True, "reason": str(error), "details": error.details}
                )
            else:
                outcomes.append({"case": case, "rejected": False})
        assert all(r["rejected"] for r in outcomes), outcomes
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before, "input changed during replay"
    return {
        "file": str(path),
        "sha256": before,
        "native_points": len(report["native"]),
        "positive": True,
        "negative_results": outcomes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod", type=Path, required=True)
    parser.add_argument("--voice", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    temporary_root = root / "generated/comprehensive-1.0.0/test-temp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mod-font-contract-", dir=temporary_root) as tmp:
        assert Path(tmp).resolve().is_relative_to(root)
        results = [check(path, Path(tmp) / "sora_2nd.exe") for path in (args.mod, args.voice)]
    args.output.write_text(
        json.dumps(
            {"scope": "static production PE pipeline, no live game", "samples": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "samples": len(results),
                "positive": len(results),
                "negative_rejected": sum(len(r["negative_results"]) for r in results),
            }
        )
    )


if __name__ == "__main__":
    main()
