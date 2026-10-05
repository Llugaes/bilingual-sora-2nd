"""Read-only real-PE regression: only native dependencies may reject a candidate."""

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
from sora_bilingual.game.native_contracts import resolve_native_contracts


def check_image(exe, temporary):
    raw = exe.read_bytes()
    baseline = native_report(exe)
    allowed, rejected = {}, {}

    def mutate(offset):
        changed = bytearray(raw)
        changed[offset] ^= 0x40
        return changed

    with pefile.PE(data=raw, fast_load=True) as pe:
        for field in ("TimeDateStamp",):
            allowed[field] = mutate(pe.FILE_HEADER.get_field_absolute_offset(field))
        for field in ("CheckSum", "AddressOfEntryPoint", "DllCharacteristics"):
            allowed[field] = mutate(pe.OPTIONAL_HEADER.get_field_absolute_offset(field))
        allowed["DOS stub"] = mutate(0x40)
        allowed["overlay"] = raw + b"unrelated publisher metadata"
        for section in pe.sections:
            name = section.Name.rstrip(b"\0").decode()
            if name in (".text", ".rdata", ".rsrc"):
                allowed["unrelated " + name] = mutate(section.PointerToRawData + 64)
        # A change beyond the hook entry must still invalidate its real function.
        rva = baseline["native"]["set_text"]["rva"]
        rejected["used function body beyond entry"] = mutate(pe.get_offset_from_rva(rva + 0x30))
        changed = bytearray(raw)
        struct.pack_into("<H", changed, pe.FILE_HEADER.get_field_absolute_offset("Machine"), 0x14C)
        rejected["wrong architecture"] = changed
        resolved = resolve_native_contracts(pe)
        # Reviewed source-line immediates, relative to the independently
        # resolved PDATA functions. The surrounding instructions and target
        # diagnostic ABI remain mandatory, including in CHAININFO fragments.
        for name, offsets in (
            ("log_write_commit", (729,)),
            ("log_record_bind", (809, 1582)),
            ("log_rows_build", (1281,)),
        ):
            start = resolved["functions"][name]
            for index, offset in enumerate(offsets):
                assert pe.get_data(start + offset - 2, 2) == b"\x41\xb8"
                allowed[f"diagnostic source line {name}:{index}"] = mutate(
                    pe.get_offset_from_rva(start + offset)
                )
        start = resolved["functions"]["log_write_commit"]
        rejected["log record stride"] = mutate(pe.get_offset_from_rva(start + 0x196))
        changed = bytearray(raw)
        # The newly masked source line must not allow a different callee.
        call = start + 0x2E9
        assert pe.get_data(call, 1) == b"\xe8"
        struct.pack_into("<i", changed, pe.get_offset_from_rva(call + 1), rva - call - 5)
        rejected["source line call to wrong function"] = changed
        diagnostic = resolved["functions"]["diagnostic_report"]
        rejected["diagnostic handler body"] = mutate(pe.get_offset_from_rva(diagnostic + 2))
        rejected["internal log branch"] = mutate(pe.get_offset_from_rva(start + 0x21F))
        rejected["diagnostic severity"] = mutate(pe.get_offset_from_rva(start + 0x2E5))
        changed = bytearray(raw)
        changed[pe.get_offset_from_rva(start + 0x2D8)] = 0xB9
        rejected["diagnostic line argument changed to R9D"] = changed
    results = []
    for expected, variants in ((True, allowed), (False, rejected)):
        for name, contents in variants.items():
            temporary.write_bytes(contents)
            assert hashlib.sha256(contents).hexdigest() != baseline["sha256"]
            try:
                report = native_report(temporary)
            except ExecutableCompatibilityError as exc:
                assert not expected, (name, str(exc))
                results.append({"case": name, "accepted": False, "detail": str(exc)})
            else:
                assert expected, name
                assert report["compatibility"] == "native_contract", name
                assert report["native"] == baseline["native"], name
                results.append({"case": name, "accepted": True})
    return {
        "sha256": baseline["sha256"],
        "native_points": len(baseline["native"]),
        "results": results,
    }


def check_reviewed_detours(exe, temporary):
    # The public sample is a negative/positive fixture, never an identity gate.
    raw = exe.read_bytes()
    with pefile.PE(data=raw, fast_load=True) as pe:
        rows = []
        for name, instruction, target in (
            ("post-call jump to wrong exit", 0x5C5DB8, 0x5C5DC0),
            ("reader entry jump to RET", 0x6542B0, 0xCEF399),
        ):
            assert pe.get_data(instruction, 1) == b"\xe9"
            changed = bytearray(raw)
            struct.pack_into(
                "<i", changed, pe.get_offset_from_rva(instruction + 1), target - instruction - 5
            )
            rows.append((name, changed))
        changed = bytearray(raw)
        assert pe.get_data(0x3895B, 4).hex() == "11cb24b2"
        changed[pe.get_offset_from_rva(0x3895B) : pe.get_offset_from_rva(0x3895B) + 4] = bytes(4)
        rows.append(("chained acquire body constant", changed))
        changed = bytearray(raw)
        fragment = bytearray(pe.get_data(0x3890C, 0x85))
        struct.pack_into("<i", fragment, 90, 0x5C5AA0 - 0xCF1000 - 94)
        at = pe.get_offset_from_rva(0xCF1000)
        changed[at : at + len(fragment)] = fragment
        pe.parse_data_directories(directories=[3])
        entry = next(
            row.struct for row in pe.DIRECTORY_ENTRY_EXCEPTION if row.struct.BeginAddress == 0x3890C
        )
        struct.pack_into("<II", changed, entry.get_file_offset(), 0xCF1000, 0xCF1085)
        at = pe.get_offset_from_rva(0x3895B)
        changed[at : at + 4] = bytes(4)
        rows.append(("unexecuted chained clone cannot hide corrupt fallthrough", changed))
    result = []
    for name, changed in rows:
        temporary.write_bytes(changed)
        try:
            native_report(temporary)
        except ExecutableCompatibilityError as exc:
            result.append({"case": name, "accepted": False, "detail": str(exc)})
        else:
            raise AssertionError("Required font contract mutation was accepted: " + name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--voice-exe", type=Path)
    parser.add_argument("--old-exe", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sora-exe-contract-") as tmp:
        temporary = Path(tmp) / "sora_2nd.exe"
        result = {"baseline": check_image(args.exe, temporary)}
        if args.old_exe:
            result["old_official"] = check_image(args.old_exe, temporary)
        if args.voice_exe:
            result["voice_sample"] = check_image(args.voice_exe, temporary)
            result["font_counterexamples"] = check_reviewed_detours(args.voice_exe, temporary)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
