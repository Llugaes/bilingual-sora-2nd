"""One external ReadProcessMemory snapshot; no attach, RPC or game input."""

import runpy
import sys
import datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from sora_bilingual.game.native_runtime import native_report

exe = Path(r"D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter\sora_2nd.exe")
report = native_report(exe)
module = runpy.run_path(str(root / "tools/read_native_layout.py"), run_name="readonly_collector")
settings = module["main"].__globals__
settings["LAYOUT_MANAGER_GLOBAL_RVA"] = report["layout_manager_global"]
settings["LABEL_VTABLE_RVA"] = report["vtable"]
sys.argv = [
    "read_native_layout",
    "--pid",
    "31480",
    "--exe",
    str(exe),
    "--max-nodes",
    "100000",
    "--max-glyphs-per-label",
    "0",
    "--include-node-inventory",
    "--out",
    str(
        root
        / "generated"
        / (
            "r19-readonly-layout-"
            + datetime.datetime.now(datetime.UTC).strftime("%H%M%S")
            + ".json"
        )
    ),
]
raise SystemExit(module["main"]())
