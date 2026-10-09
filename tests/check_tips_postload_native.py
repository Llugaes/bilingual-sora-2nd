"""Owned-host Win64 loader and list producer -> complete wire -> final renderer."""

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = Path(os.environ.get("R19_PRODUCT_ROOT", ROOT)).resolve()
sys.path.insert(0, str(PRODUCT))
import capstone
import frida
import pefile
from sora_bilingual.game.native_contracts import resolve_native_contracts


def code(pe, md, span, role, functions):
    start, end = span
    instructions = list(md.disasm(pe.get_data(start, end - start), start))
    patches = []
    strings = {}
    for ins in instructions:
        if ins.mnemonic == "call" and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            target = ins.operands[0].imm
            if role == "loader":
                kind = "diagnostic" if target == functions["diagnostic_report"] else "compare"
            else:
                kind = "setter" if target == functions["set_text"] else "lookup"
            patches.append(
                {
                    "offset": ins.address - start + ins.imm_offset,
                    "next": ins.address - start + ins.size,
                    "target": kind,
                    "call": True,
                }
            )
        for operand in ins.operands:
            if (
                operand.type != capstone.x86.X86_OP_MEM
                or operand.mem.base != capstone.x86.X86_REG_RIP
            ):
                continue
            target = ins.address + ins.size + operand.mem.disp
            value = pe.get_data(target, 256).split(b"\0")[0]
            if ins.op_str.startswith("rax,"):
                kind, width = "vtable", 48
            elif role == "item" and ins.op_str.startswith("rcx,"):
                kind, width = "manager", 8
            else:
                if role == "item":
                    assert value == b"text"
                    kind = "name"
                elif value == b"TipsTableData":
                    kind = "descriptor"
                elif value.startswith(b"d:\\"):
                    kind = "file"
                else:
                    kind = "message"
                width = len(value) + 1
                strings[kind] = value.decode("utf-8")
            patches.append(
                {
                    "offset": ins.address - start + ins.disp_offset,
                    "next": ins.address - start + ins.size,
                    "target": kind,
                    "width": width,
                }
            )
    return {"body": list(pe.get_data(start, end - start)), "patches": patches}, strings


def sample(row):
    path = Path(row["path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    pe = pefile.PE(data=raw)
    resolved = resolve_native_contracts(pe)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    entries = pe.get_data(directory.VirtualAddress, directory.Size)
    spans = [struct.unpack_from("<III", entries, i)[:2] for i in range(0, len(entries), 12)]
    item = []
    for start, end in spans:
        if end - start != 525:
            continue
        instructions = list(md.disasm(pe.get_data(start, end - start), start))
        if any(
            i.mnemonic == "mov" and i.op_str == "byte ptr [rcx + 0x1c], r9b" for i in instructions
        ):
            item.append((start, end))
    assert len(item) == 1
    loader, strings = code(pe, md, row["span"], "loader", resolved["functions"])
    producer, _ = code(pe, md, item[0], "item", resolved["functions"])
    compare_start = next(
        i.operands[0].imm
        for i in md.disasm(pe.get_data(row["span"][0], 426), row["span"][0])
        if i.mnemonic == "call"
    )
    compare_span = next(s for s in spans if s[0] == compare_start)
    compare, _ = code(pe, md, compare_span, "compare", resolved["functions"])
    assert len(compare["body"]) == 103 and not compare["patches"]
    assert sorted(p["target"] for p in loader["patches"] if p.get("call")) == [
        "compare",
        "diagnostic",
    ]
    assert sorted(p["target"] for p in producer["patches"] if p.get("call")) == [
        "lookup",
        "setter",
        "setter",
    ]
    return {
        "sha256": row["sha256"],
        "loader": loader,
        "item": producer,
        "compare": compare,
        "message": strings["message"],
        "file": strings["file"],
        "producer_span": item[0],
    }


def main():
    rows = json.loads((ROOT / "generated/r19-tips-load-three-samples.json").read_text("utf-8"))
    samples = [sample(row) for row in rows]
    prefix = os.environ.get("DEV_VERIFICATION_PREFIX", "r19")
    receipt = json.loads((ROOT / f"generated/{prefix}-production-receipt.json").read_text("utf-8"))
    wire = (
        Path(receipt["wire_path"])
        if PRODUCT == ROOT
        else PRODUCT
        / "generated"
        / json.loads((PRODUCT / "candidate-cache.json").read_text("utf-8"))["wire_name"]
    )
    assert hashlib.sha256(wire.read_bytes()).hexdigest() == receipt["wire_sha256"]
    capture = json.loads(
        (ROOT / "generated/r19-tips-existing-owner-snapshot-0449.json").read_text("utf-8")
    )
    sources = {"Tactical Bonus", "Stealing AT Bonuses", "Changing Battle Difficulty", "Overdrive"}
    captured = [
        row
        for row in capture["all_rows"]
        if row["scope"] == "note_help_title" and row["original"] in sources
    ]
    assert len(captured) == 4
    from sora_bilingual.localization.resources import FpacArchive
    from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables

    game = Path(r"D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter")
    with FpacArchive(game / "pac/steam" / _TABLE_ARCHIVES["en"]) as archive:
        names = _logical_tables(archive)
        tips = archive.read(names["table/t_tips.tbl"])
        help_ = archive.read(names["table/t_help.tbl"])
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        if host.pid == 31480:
            raise RuntimeError("Refusing game process")
        session = frida.attach(host.pid)
        source = "\n".join(
            ((ROOT if path.startswith("tests/") else PRODUCT) / path).read_text("utf-8")
            for path in (
                "sora_bilingual/game/scripts/runtime_text.js",
                "sora_bilingual/game/scripts/runtime_identity.js",
                "tests/tips_postload_native.js",
                "sora_bilingual/game/scripts/native_transport.js",
            )
        )
        script = session.create_script(source, runtime="v8")
        script.load()
        loaded = script.exports_sync.modelpackedfile(str(wire))
        checked = script.exports_sync.run(samples, list(tips), list(help_), captured)
        result = {
            "wire_sha256": receipt["wire_sha256"],
            "loaded": loaded,
            "checked": checked,
            "host_kind": "self-created hidden Python",
            "current_game_attached": False,
            "native_dependencies": "private ABI stubs for lookup/init/setter/diagnostic; full original loader and list constructor arithmetic/control flow executed",
            "candidate_live_verified": False,
        }
        result.update(product_root=str(PRODUCT), frida_module=frida.__file__)
        output = (
            f"{prefix}-tips-native-path.json"
            if PRODUCT == ROOT
            else f"{prefix}-tips-native-path-package.json"
        )
        (ROOT / "generated" / output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
        )
        print(
            json.dumps(
                {
                    "samples": len(checked["samples"]),
                    "records": sum(s["converted_records"] for s in checked["samples"]),
                    "producer_cases": sum(len(s["cases"]) for s in checked["samples"]),
                    "native_arithmetic_limits": sum(len(s["limits"]) for s in checked["samples"]),
                    "wire_sha256": receipt["wire_sha256"],
                    "game_attached": False,
                }
            )
        )
    finally:
        if session is not None:
            session.detach()
        host.stdin.close()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
