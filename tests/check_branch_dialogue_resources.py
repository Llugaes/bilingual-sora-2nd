"""Replay the real inserted NPC branch through the complete shipped callbacks."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from check_remaining_dialogue import RUNNER
from sora_bilingual.localization.dynamic_identity import _function_code
from sora_bilingual.localization.resources import (
    FpacArchive,
    _logical_script_entries,
    assembled_dialogue,
    parse_scp,
)
from sora_bilingual.localization.runtime_identity import script_signature


REFUSAL = r"""
for(const row of input.refused)try {
 const data=Buffer.from(row.blob,'base64'),ids=new ScriptIdentities(model.script_identities);
 const identity=ids.capture(row.signature,n=>data.subarray(0,n),row.fn,row.token,row.site,row.source);
 assert.equal(identity ? ids.lookup(identity,row.source) : null,null,'absent official branch cannot borrow a later call');cases++;
 const r=makeRuntime(),label=r.label(0xa000,'');r.api.load(model,'annotation',true,1);
 r.dialogueSet(label,row.source,data,row.fn,row.token.split(',').map(Number),3,row.site);
 assert.equal(label.text(),row.source,'unpaired official source stays intact');cases++;
}catch(error){failures.push({key:row.key,reason:error.message,stack:error.stack});}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads((args.model_dir / "catalog.json").read_bytes())["entries"]
    path, name = "script/scena/mp4020_01.dat", "TK_GERVAIS"
    with FpacArchive(args.game_dir / "pac/steam/script_sc.pac") as archive:
        data = archive.read(_logical_script_entries(archive)[path])
    function = parse_scp(data).functions[name]
    positions, _ = _function_code(data, name)
    physical_calls = [
        i
        for i, op in enumerate(function.code_shape)
        if op[0] in ("local-call", "external-call", "system-call")
    ]
    assert len(physical_calls) == len(function.called)
    start, count = struct.unpack_from("<II", data, 4)
    function_at = next(
        start + i * 32
        for i in range(count)
        if data[
            (p := struct.unpack_from("<I", data, start + i * 32 + 28)[0] & 0x3FFFFFFF) : data.index(
                b"\0", p
            )
        ].decode()
        == name
    )
    calls = struct.unpack_from("<I", data, function_at + 20)[0]
    paired, refused = [], []
    for called in (17, 19, 21, 24, 26, 28):
        source = assembled_dialogue(function.called[called])
        records = [
            r
            for r in entries
            if r["key"].startswith(f"{path}/{name}/called/")
            and "/assembled_dialogue/" in r["key"]
            and r["texts"].get("zh-Hans") == source
            and r["texts"].get("ja")
        ]
        argc, args_at = struct.unpack_from("<HI", data, calls + called * 12 + 6)
        raw = [struct.unpack_from("<II", data, args_at + i * 8) for i in range(argc)]
        assert all(tag == 0 for _, tag in raw)
        row = {
            "key": f"{path}/{name}/called/{called}",
            "fn": name,
            "blob": base64.b64encode(data).decode(),
            "signature": script_signature(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "token": ",".join(str(value) for value, _ in raw[2:]),
            "site": {
                "pc": positions[physical_calls[called]] + 4,
                "group": 5,
                "command": raw[1][0] & 0x3FFFFFFF,
            },
            "source": source,
        }
        if called < 24:
            assert not records, (called, "wrong branch acquired Japanese")
            refused.append(row)
        else:
            assert len(records) == 1, (called, len(records))
            entry = records[0]
            assert entry["called_ids"]["ja"] == called - 7
            paired.append(
                {**row, "key": entry["key"].split("/alignment/")[0], "texts": entry["texts"]}
            )
    harness = (ROOT / "tests/test_native_agent.js").read_text("utf-8").split("\ntest(", 1)[0]
    runner = RUNNER.replace("process.stdout.write", REFUSAL + "\nprocess.stdout.write")
    script = args.model_dir / "branch-dialogue-callbacks.cjs"
    script.write_text(harness + runner, "utf-8")
    model = json.loads((args.model_dir / "full-model-builds.json").read_bytes())[0]["path"]
    result = subprocess.run(
        [
            "node",
            "--max-old-space-size=4096",
            "-e",
            "eval(require('node:fs').readFileSync(process.argv[1],'utf8'))",
            str(script.resolve()),
        ],
        cwd=ROOT / "tests",
        input=json.dumps({"model": model, "rows": paired, "refused": refused}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    (args.model_dir / "branch-dialogue-callbacks.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
