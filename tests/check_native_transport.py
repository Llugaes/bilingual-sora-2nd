import os

"""Exercise the production model RPC in a disposable process, never the game."""
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import frida
from sora_bilingual.localization.native_catalog import ready_model
from sora_bilingual.config.native_config import read_config, ActionPolicy
from sora_bilingual.platform.inputs import InputManager, vk_for_key
from sora_bilingual.game.native_runtime import NativeLabels

ROOT = Path(__file__).resolve().parents[1]


def main():
    model, _, _ = ready_model(Path(os.environ["SORA_GAME_DIR"]), read_config())
    print(
        json.dumps(
            {
                "compact_utf8_bytes": len(
                    json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode()
                ),
                "rpc_json_bytes": len(json.dumps(model).encode()),
            }
        ),
        flush=True,
    )
    source = "\n".join(
        (ROOT / name).read_text("utf-8")
        for name in (
            "sora_bilingual/game/scripts/runtime_text.js",
            "sora_bilingual/game/scripts/runtime_identity.js",
        )
    )
    source += """\nrpc.exports={load(model,mode,active,scale,layout){
      globalThis.tr=new RuntimeText(model);
      globalThis.ids=new ScriptIdentities(model.script_identities);
      globalThis.tables=new TableIdentities(model.table_identities);
      globalThis.mode=mode;
      return true;
    },select(mode,active){globalThis.mode=mode;return true;},
      sample(text){return tr.translate(text,globalThis.mode);}};"""
    transport = ROOT / "sora_bilingual/game/scripts/native_transport.js"
    if transport.exists():
        source += "\n" + transport.read_text("utf-8")
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        session.on("detached", lambda *a: print("detached:", a, flush=True))
        script = session.create_script(source)
        script.on("destroyed", lambda: print("script destroyed", flush=True))
        script.load()
        native = NativeLabels(lambda _: None)
        native.script = script
        start = time.perf_counter()
        assert native.load(model, read_config(), "annotation")
        source, pair = next(
            (s, p)
            for s, p in model["pairs"].items()
            if p[0] != p[1] and all("<" not in t and "\n" not in t for t in (s, *p))
        )
        native.select("secondary", True)
        assert script.exports_sync.sample(source) == pair[1]
        physical = set()
        keys = read_config()["switch_binding"]["keyboard"]
        for interaction in ("language_hold", "language_toggle"):
            policy = ActionPolicy(interaction)
            inputs = InputManager(
                {"hotkey": {"keyboard": keys}},
                key_state=lambda vk: vk in physical,
                joystick_provider=lambda: [],
            )

            def sample():
                native.select(policy.advance(inputs.poll_state(True)), True)
                return script.exports_sync.sample(source)

            assert sample() == pair[0]
            physical.update(vk_for_key(k) for k in keys)
            assert sample() == pair[1]
            for _ in range(10):
                assert sample() == pair[1]
            physical.clear()
            assert sample() == pair[0 if interaction == "language_hold" else 1]
            if interaction == "language_toggle":
                physical.update(vk_for_key(k) for k in keys)
                assert sample() == pair[0]
                physical.clear()
        result = {
            "model_loaded": True,
            "seconds": round(time.perf_counter() - start, 3),
            "game_attached": False,
            "hold_and_toggle_verified": True,
        }
        print(json.dumps(result), flush=True)
        (ROOT / "generated/native-transport-check.json").write_text(
            json.dumps(result, indent=2), "utf-8"
        )
    finally:
        if session is not None:
            try:
                session.detach()
            except frida.InvalidOperationError:
                pass
        host.communicate(timeout=5)


if __name__ == "__main__":
    main()
