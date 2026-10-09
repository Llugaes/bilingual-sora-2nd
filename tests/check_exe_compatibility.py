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


def check_image(exe, temporary):
    from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
    from sora_bilingual.game.native_runtime import native_report
    from sora_bilingual.game.native_contracts import resolve_native_contracts

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
    from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
    from sora_bilingual.game.native_runtime import native_report

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


def loader_continuations(pe):
    """Follow the reviewed references to the loader code this image actually uses."""
    functions = resolve_native_contracts(pe)["functions"]

    def follow(start, template, found):
        if not native_contracts._variant_matches(pe, start, template):
            return False
        for ref in template.get("continuations", []):
            target = native_contracts._reference_target(pe, start, ref)
            found[ref["name"]] = (target, ref["template"])
            if not follow(target, ref["template"], found):
                return False
        return True

    result = {}
    for name in ("font_image_read_call", "font_file_read"):
        matching = [
            (variant, found)
            for variant in CONTRACT["functions"][name]["variants"]
            for found in [{}]
            if follow(functions[name], variant, found)
        ]
        assert matching, name
        # The retained 1.0 pinned IAT and the relocated 045 form can both
        # describe the same already-verified code. Keep actual dependency
        # identity unambiguous instead of counting equivalent templates.
        assert (
            len(
                {
                    native_contracts._variant_semantics(pe, functions[name], variant)
                    for variant, _found in matching
                }
            )
            == 1
        ), name
        result.update(matching[0][1])
    return functions, result


def check_relinked_loader(exe, temporary):
    # A loader relinked for a new game build keeps its code and only moves
    # addresses. Each moved address must still name the reviewed object.
    raw = exe.read_bytes()
    with pefile.PE(data=raw, fast_load=True) as pe:
        functions, found = loader_continuations(pe)
        wrapper, wrapper_template = found["cache_hash_wrapper"]
        helper, helper_template = found["cache_hash_helper"]
        routine, _ = found["path_hash_update"]
        reader, reader_template = found["file_reader_helper"]

        def patched(rva, value=None, *, add=0):
            changed = bytearray(raw)
            at = pe.get_offset_from_rva(rva)
            current = struct.unpack_from("<i", changed, at)[0]
            struct.pack_into("<i", changed, at, current + add if value is None else value)
            return changed

        resume = wrapper_template["links"][0]
        assert "encoding" not in resume and resume["function"] == "font_image_read_call"
        callee = next(
            ref for ref in helper_template["continuations"] if ref["name"] == "path_hash_update"
        )
        table = helper_template["equal_targets"][0]["left"]
        slot = reader_template["imports"][0]
        rows = [
            (
                "hash resume skips into the following instruction",
                patched(wrapper + resume["displacement"][0], add=1),
            ),
            (
                "hash routine RVA names another function",
                patched(helper + callee["displacement"][0], functions["font_allocate"]),
            ),
            (
                "hash table is not the routine's own table",
                patched(helper + table["displacement"][0], add=4),
            ),
            ("hash routine body", patched(routine + 23, add=1)),
            (
                "thread id slot names the neighbouring import",
                patched(reader + slot["displacement"][0], add=8),
            ),
        ]
    result = []
    for name, changed in rows:
        temporary.write_bytes(changed)
        try:
            native_report(temporary)
        except ExecutableCompatibilityError as exc:
            result.append({"case": name, "accepted": False, "detail": str(exc)})
        else:
            raise AssertionError("Required loader reference mutation was accepted: " + name)
    return result


def check_loader_data_and_imports(exe, temporary):
    """Both voice shapes must enforce the same data/import safety boundary."""
    raw = exe.read_bytes()
    with pefile.PE(data=raw, fast_load=True) as pe:
        functions, found = loader_continuations(pe)
        helper, helper_template = found["cache_hash_helper"]
        routine, routine_template = found["path_hash_update"]
        reader, reader_template = found["file_reader_helper"]
        wrapper, wrapper_template = found["cache_hash_wrapper"]
        table_ref = helper_template["data_refs"][0]
        table = native_contracts._reference_target(pe, helper, table_ref)
        slot_ref = reader_template["imports"][0]
        slot = native_contracts._reference_target(pe, reader, slot_ref)
        resume = wrapper_template["links"][0]
        callee = next(
            ref for ref in helper_template["continuations"] if ref["name"] == "path_hash_update"
        )
        routine_table = helper_template["equal_targets"][0]["right"]

        def mutate(rva):
            changed = bytearray(raw)
            changed[pe.get_offset_from_rva(rva)] ^= 1
            return changed

        def write(changed, rva, value):
            struct.pack_into("<I", changed, pe.get_offset_from_rva(rva), value & 0xFFFFFFFF)

        corrupt = mutate(table + 4)
        both_bad = bytearray(raw)
        target = pe.OPTIONAL_HEADER.SizeOfImage + 0x1000
        write(both_bad, helper + table_ref["displacement"][0], target)
        write(both_bad, routine + routine_table["displacement"][0], target - routine - 20)
        wrong_call = bytearray(raw)
        write(wrong_call, helper + callee["displacement"][0], routine + 1)
        bad_resume = mutate(wrapper + resume["displacement"][0])
        neighbour = bytearray(raw)
        write(neighbour, reader + slot_ref["displacement"][0], slot + 8)
        pe.parse_data_directories(directories=[1])
        imported = next(
            row
            for descriptor in pe.DIRECTORY_ENTRY_IMPORT
            for row in descriptor.imports
            if row.address - pe.OPTIONAL_HEADER.ImageBase == slot
        )
        # pefile exposes the name's file offset, independent of import ordering.
        import_name = bytearray(raw)
        import_name[imported.name_offset + len(imported.name) - 1] ^= 1
        rows = [
            ("CRC table contents corrupted (independent issue counterexample)", corrupt),
            ("both hash readers use the same unmapped table", both_bad),
            ("hash call enters a function body", wrong_call),
            ("hash resume target rewritten", bad_resume),
            ("required IAT symbol renamed (independent old voice counterexample)", import_name),
            ("required IAT slot points at neighbouring import", neighbour),
            ("path hash routine instruction rewritten", mutate(routine + 23)),
            ("hash helper field stride rewritten", mutate(helper + 852)),
            ("hash wrapper TEST register rewritten", mutate(wrapper + 63)),
            ("hash wrapper stack adjustment rewritten", mutate(wrapper + 3)),
        ]
        # Move only the reviewed data and leaf, keeping their exact instruction
        # bodies and relationship. These altered PEs are static fixtures only.
        rootio = wrapper - 0xF0  # Reviewed fixture layout; section names are irrelevant.
        moved = bytearray(raw)
        moved_routine = rootio + 0x1B00
        # The retained 1.0 contract requires constant data to be read-only.
        # The original 045 fixture placed its table in writable loader code;
        # use mapped zero padding in a read-only data section instead.
        moved_table = None
        for section in pe.sections:
            if section.Characteristics & (0x80000000 | 0x20000000):
                continue
            size = min(section.Misc_VirtualSize, section.SizeOfRawData)
            gap = pe.get_data(section.VirtualAddress, size).find(bytes(1027))
            if gap >= 0:
                moved_table = (section.VirtualAddress + gap + 3) & ~3
                break
        assert moved_table is not None, "fixture needs mapped read-only CRC padding"
        for target_rva, source_rva, size in (
            (moved_table, table, 1024),
            (moved_routine, routine, routine_template["size"]),
        ):
            at = pe.get_offset_from_rva(target_rva)
            moved[at : at + size] = pe.get_data(source_rva, size)
        write(moved, helper + table_ref["displacement"][0], moved_table)
        write(moved, helper + callee["displacement"][0], moved_routine)
        write(moved, moved_routine + 16, moved_table - moved_routine - 20)
    result = []
    for name, changed in rows:
        temporary.write_bytes(changed)
        try:
            native_report(temporary)
        except ExecutableCompatibilityError as exc:
            result.append({"case": name, "accepted": False, "detail": str(exc)})
        else:
            raise AssertionError("Required loader dependency mutation was accepted: " + name)
    temporary.write_bytes(moved)
    report = native_report(temporary)
    assert report["native"] == native_report(exe)["native"]
    result.append({"case": "CRC table and leaf routine relocate together", "accepted": True})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--voice-exe", type=Path)
    parser.add_argument("--old-exe", type=Path)
    parser.add_argument("--relinked-voice-exe", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--package", type=Path, help="Use this final candidate's production native resolver"
    )
    args = parser.parse_args()
    if args.package:
        sys.path.insert(0, str(args.package.resolve()))
    global \
        ExecutableCompatibilityError, \
        native_report, \
        native_contracts, \
        CONTRACT, \
        resolve_native_contracts
    from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
    from sora_bilingual.game.native_runtime import native_report
    from sora_bilingual.game import native_contracts
    from sora_bilingual.game.native_contract_data import CONTRACT
    from sora_bilingual.game.native_contracts import resolve_native_contracts
    from sora_bilingual.game import native_runtime

    if args.package:
        assert Path(native_runtime.__file__).resolve().is_relative_to(args.package.resolve())
    with tempfile.TemporaryDirectory(prefix="sora-exe-contract-") as tmp:
        temporary = Path(tmp) / "sora_2nd.exe"
        result = {"baseline": check_image(args.exe, temporary)}
        if args.old_exe:
            result["old_official"] = check_image(args.old_exe, temporary)
        if args.voice_exe:
            result["voice_sample"] = check_image(args.voice_exe, temporary)
            result["font_counterexamples"] = check_reviewed_detours(args.voice_exe, temporary)
            result["old_voice_data_import_counterexamples"] = check_loader_data_and_imports(
                args.voice_exe, temporary
            )
        if args.relinked_voice_exe:
            result["relinked_voice_sample"] = check_image(args.relinked_voice_exe, temporary)
            result["relinked_loader_counterexamples"] = check_relinked_loader(
                args.relinked_voice_exe, temporary
            )
            result["issue_voice_data_import_counterexamples"] = check_loader_data_and_imports(
                args.relinked_voice_exe, temporary
            )
    result["production_native_runtime"] = str(Path(native_runtime.__file__).resolve())
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
