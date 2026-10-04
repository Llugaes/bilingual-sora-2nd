"""Validate the real build and modified disposable copies, without executing them."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pefile
from sora_bilingual.game.exe_compatibility import TARGET_SHA256, ExecutableCompatibilityError
from sora_bilingual.game.native_runtime import native_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.exe.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TARGET_SHA256, "requires reviewed baseline"
    baseline = native_report(args.exe)
    pe = pefile.PE(data=raw, fast_load=True)
    allowed = {}
    rejected = {}

    def mutate(offset):
        changed = bytearray(raw)
        changed[offset] ^= 0x40
        return changed

    allowed["timestamp"] = mutate(pe.FILE_HEADER.get_field_absolute_offset("TimeDateStamp"))
    allowed["checksum"] = mutate(pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum"))
    allowed["header padding"] = mutate(pe.OPTIONAL_HEADER.SizeOfHeaders - 1)
    pe.parse_data_directories(directories=[6])
    codeview = next(
        entry.struct
        for entry in pe.DIRECTORY_ENTRY_DEBUG
        if entry.struct.Type == 2 and pe.get_data(entry.struct.AddressOfRawData, 4) == b"RSDS"
    )
    for name, offset in (("PDB GUID", 4), ("PDB age", 20), ("PDB path", 24)):
        allowed[name] = mutate(codeview.PointerToRawData + offset)
    rejected["CodeView signature"] = mutate(codeview.PointerToRawData)
    rejected["CodeView neighboring data"] = mutate(codeview.PointerToRawData + codeview.SizeOfData)
    rejected["CodeView extent"] = mutate(codeview.get_field_absolute_offset("SizeOfData"))
    allowed["overlay"] = raw + b"test publisher metadata"
    certificate = bytearray(raw + bytes(16))
    struct.pack_into(
        "<II", certificate, pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].get_file_offset(), len(raw), 16
    )
    allowed["certificate"] = certificate
    for section in pe.sections:
        name = section.Name.rstrip(b"\0").decode()
        changed = mutate(section.PointerToRawData + 64)
        (allowed if name == ".rsrc" else rejected)[name] = changed
        if section.SizeOfRawData > section.Misc_VirtualSize:
            allowed[name + " padding"] = mutate(section.PointerToRawData + section.Misc_VirtualSize)
    rejected["parser body after entry"] = mutate(pe.get_offset_from_rva(0x5877A0 + 0x80))
    rejected["entrypoint"] = mutate(
        pe.OPTIONAL_HEADER.get_field_absolute_offset("AddressOfEntryPoint")
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="sora-exe-compat-") as tmp:
        target = Path(tmp) / "sora_2nd.exe"
        for expected, variants in ((True, allowed), (False, rejected)):
            for name, contents in variants.items():
                target.write_bytes(contents)
                # Negative control: the previous release rejects every altered copy.
                assert hashlib.sha256(contents).hexdigest() != TARGET_SHA256
                try:
                    report = native_report(target)
                except ExecutableCompatibilityError as exc:
                    assert not expected, (name, str(exc))
                    results.append({"case": name, "accepted": False, "detail": str(exc)})
                else:
                    assert expected, name
                    assert report["compatibility"] == "compatible_image", name
                    assert report["native"] == baseline["native"], name
                    assert report["hooks"] == baseline["hooks"], name
                    results.append({"case": name, "accepted": True})
    pe.close()
    result = {
        "baseline": TARGET_SHA256,
        "native_points": len(baseline["native"]),
        "legacy_rejects_allowed": len(allowed),
        "results": results,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
