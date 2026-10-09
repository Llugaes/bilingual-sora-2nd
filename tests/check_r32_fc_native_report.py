"""Read-only real CAB62 gate proof and isolated optional FC negative cases."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pefile
from sora_bilingual.game import native_runtime

ROOT = Path(__file__).resolve().parents[1]
EXE = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter/sora_2nd.exe")
START, END = 0x3F7BD0, 0x3F8217
EXPECTED = "09cee620b2ebc7615b9fb56a34585a7c0f76e1e6e70fc8a996973d728e117c14"
raw = EXE.read_bytes()
pe = pefile.PE(data=raw, fast_load=True)
actual = native_runtime.native_report(EXE)
fc_names = ["fc_quest_builder", "fc_quest_paragraph_ready", "fc_quest_line_return"]
assert hashlib.sha256(pe.get_data(START, END - START)).hexdigest() == EXPECTED
assert [actual["native"][key]["rva"] for key in fc_names] == [START, 0x3F7E26, 0x3F8044]
assert actual["native"]["set_text"]["rva"] == 0x5892C0
base_report = deepcopy(actual)
for key in fc_names:
    base_report["native"].pop(key)


class FakePE:
    def __init__(self, mutation):
        self.mutation = mutation

    def get_data(self, rva, size):
        data = pe.get_data(rva, size)
        if self.mutation == "whole_byte" and (rva, size) == (START, END - START):
            return bytes([data[0] ^ 1]) + data[1:]
        if self.mutation == "truncated" and (rva, size) == (START, END - START):
            return data[:-1]
        if self.mutation == "ready_boundary" and (rva, size) == (0x3F7E26, 7):
            return bytes([data[0] ^ 1]) + data[1:]
        if self.mutation == "call_opcode" and (rva, size) == (0x3F803F, 5):
            return b"\x90" + data[1:]
        if self.mutation == "call_target" and (rva, size) == (0x3F803F, 5):
            return data[:1] + (int.from_bytes(data[1:], "little", signed=True) + 1).to_bytes(
                4, "little", signed=True
            )
        return data


results = []
for mutation in [
    "unchanged",
    "whole_byte",
    "truncated",
    "ready_boundary",
    "call_opcode",
    "call_target",
    "resolved_set_text",
]:
    fake_report = deepcopy(base_report)
    if mutation == "resolved_set_text":
        fake_report["native"]["set_text"]["rva"] += 1

    @contextmanager
    def fake_verified(_path):
        yield FakePE(mutation), fake_report

    with patch.object(native_runtime, "verified_target_image", fake_verified):
        result = native_runtime.native_report(EXE)
    admitted = all(key in result["native"] for key in fc_names)
    assert admitted == (mutation == "unchanged"), mutation
    for key, value in fake_report["native"].items():
        if key not in fc_names:
            assert result["native"][key] == value
    results.append(
        {
            "case": mutation,
            "optional_FC_admitted": admitted,
            "existing_contract_points_preserved": True,
        }
    )

old = json.loads((ROOT / "generated/r32-local7-matrix-integrity.json").read_text("utf8"))
contract_path = "sora_bilingual/game/native_contract_data.py"
contract_hash = hashlib.sha256((ROOT / contract_path).read_bytes()).hexdigest()
assert contract_hash == old["source_files"][contract_path]
freeze = json.loads((ROOT / "generated/r32-coverage-source-freeze.json").read_text("utf8"))
receipt = {
    "source_snapshot_sha256": freeze["snapshot_sha256"],
    "native_runtime_sha256": hashlib.sha256(
        (ROOT / "sora_bilingual/game/native_runtime.py").read_bytes()
    ).hexdigest(),
    "native_contract_data_sha256": contract_hash,
    "contract_bytes_unchanged_vs_local7": True,
    "exe_sha256": hashlib.sha256(raw).hexdigest(),
    "whole_fc_function_sha256": EXPECTED,
    "actual_set_text_rva": "0x5892c0",
    "actual_FC_descriptors": {key: actual["native"][key] for key in fc_names},
    "cases": results,
    "failure_count": 0,
    "scope": "Real PE positive and isolated FakePE negative function/call/ready conditions; no EXE or production writes, no game attach.",
    "game_attached": False,
    "build_run": False,
}
output = ROOT / "generated/r32-local8-fc-native-report-negative.json"
output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", "utf8")
print(
    json.dumps(
        {
            "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "cases": len(results),
            "failure_count": 0,
        }
    )
)
