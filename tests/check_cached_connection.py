"""Offline connection-path benchmark: attach only to our own hidden Python helper."""

import argparse
import gc
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import frida
from sora_bilingual.game.agent_control import publish
from sora_bilingual.config.native_config import read_config
from sora_bilingual.game.native_runtime import NativeLabels, native_report
from sora_bilingual.localization.native_catalog import ready_model, model_path
from sora_bilingual.localization.model_wire import prepare_wire
from sora_bilingual.paths import SCRIPTS


def check(game, output, config_path):
    config = read_config(config_path)
    start = time.perf_counter()
    model, signature, _ = ready_model(game, config, output)
    cache = model_path(signature, config, output)
    wire = prepare_wire(cache, model)
    preparation = time.perf_counter() - start
    del model
    gc.collect()
    # Production resolver constructors and production transport decoder. There
    # are no game hooks, native memory writes or references to game processes.
    source = "\n".join(
        (SCRIPTS / n).read_text("utf-8")
        for n in ("runtime_text.js", "runtime_identity.js", "runtime_paragraph.js")
    )
    source += """\nlet current=null;
rpc.exports={load(model){
    const r=new RuntimeText(model),s=new ScriptIdentities(model.script_identities),t=new TableIdentities(model.table_identities);
    const p=new RuntimeParagraphs(model,RuntimeText);
    current={model,r,s,t,p};return true;
},disable(){return true;},status(){return {pairs:Object.keys(current.model.pairs).length, names:current.r.translate('　·艾丝蒂尔　　　Lv.39\\n　·克萝赛　　　Lv.38\\n　·雪拉扎德　　　Lv.39\\n　·奥利维尔　　　Lv.39','annotation')};}};
"""
    source += (SCRIPTS / "native_transport.js").read_text("utf-8")
    source += (SCRIPTS / "native_control.js").read_text("utf-8")
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        model, _, entries = ready_model(game, config, output)
        assert entries is None
        loaded = time.perf_counter()
        native_report(game / "sora_2nd.exe")
        verified = time.perf_counter()
        helper = subprocess.Popen(
            [sys.executable, "-c", "import os,sys;print(os.getpid(),flush=True);sys.stdin.read()"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        pid = int(helper.stdout.readline())
        session = None
        native = None
        try:
            session = frida.attach(pid)
            script = session.create_script(source, runtime="v8")
            script.load()
            attached = time.perf_counter()
            native = NativeLabels(lambda _: None)
            native.session = session
            native.control = publish(script, pid, sys.executable, output / "benchmark-agent.json")
            native.script = SimpleNamespace(exports_sync=native.control)
            native.load(model, config, "annotation", cache_path=cache)
            end = time.perf_counter()
            proof = native.status()
            assert proof["pairs"] == len(model["pairs"])
            assert all(
                name in proof["names"]
                for name in ("エステル", "クローゼ", "シェラザード", "オリビエ")
            )
            runs.append(
                {
                    "model_seconds": round(loaded - start, 3),
                    "verify_seconds": round(verified - loaded, 3),
                    "helper_attach_seconds": round(attached - verified, 3),
                    "load_seconds": round(end - attached, 3),
                    "total_seconds": round(end - start, 3),
                    "pairs": proof["pairs"],
                    "save_names_verified": True,
                }
            )
        finally:
            if native is not None and native.control is not None:
                native.park()
            elif session is not None:
                session.detach()
            helper.stdin.close()
            helper.wait(timeout=5)
            helper.stdout.close()
            (output / "benchmark-agent.json").unlink(missing_ok=True)
        del model
        gc.collect()
    report = {
        "cache_preparation_seconds": round(preparation, 3),
        "model_bytes": cache.stat().st_size,
        "wire_bytes": wire.stat().st_size,
        "game_started": False,
        "game_attached": False,
        "runs": runs,
    }
    (output / "cached-connection-performance.json").write_text(
        json.dumps(report, indent=2), "utf-8"
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "output", "config"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    check(args.game, args.output, args.config)
