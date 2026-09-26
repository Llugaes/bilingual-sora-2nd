"""Version-bound native label experiment; all UI mutations run on UI callbacks."""

from pathlib import Path
import json
import pefile
import frida
import threading
import uuid
from sora_bilingual.game.hooks import verify_target

from sora_bilingual.paths import ROOT

POINTS = {
    "set_text": 0x588A40,
    "reset_text": 0x585320,
    "measure_text": 0x588710,
    "copy_label_ready": 0x583E6A,
    "line_ruby_origin": 0x588570,
    "update": 0x584CA0,
    "layout_ready": 0x584CF4,
    "destroy": 0x5839F0,
    "ruby_context_init": 0x5830F0,
    "ruby_begin": 0x58678E,
    "ruby_place_return": 0x58714F,
    "text_lookup": 0x5E8550,
    "label_text_key_load": 0x584842,
    "node_name_lookup": 0x5814D8,
    "ruby_measure_return": 0x587084,
    "ruby_base_measure_return": 0x586E80,
    "newline_prepare": 0x587966,
    "ruby_base_measure_end": 0x586E9C,
    "ruby_compensate": 0x587253,
    "ruby_end": 0x587349,
    "parse_text": 0x5877A0,
    "icon_callback_clone": 0x58A7E0,
    "layout_create": 0x58FC80,
    "layout_release": 0x58FF50,
    "dialogue_popup": 0x4AE2A0,
    "dialogue_message": 0x4AE990,
    "dialogue_bubble": 0x4AEE20,
    "dialogue_builder": 0x4AD670,
    "quest_builder": 0x422780,
    "quest_paragraph_ready": 0x4229F5,
    "quest_line_return": 0x422C24,
    "log_measure": 0x362BD0,
    "log_measure_row": 0x362D7B,
    "log_measure_calculate": 0x362D9B,
    "log_measure_body": 0x362D8F,
    "log_measure_row_end": 0x362E40,
    "font_reset": 0x5BF8F0,
    "font_load": 0x5BF350,
}


def native_report(exe):
    report = verify_target(Path(exe))
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        report["native"] = {
            name: {"rva": rva, "bytes": pe.get_data(rva, 16).hex()} for name, rva in POINTS.items()
        }
        report["vtable"] = 0xB18490
        report["icon_callback_vtable"] = 0xB18458
        report["text_table_global"] = 0xC60E88
        report["node_names"] = True
        report["layout_manager_global"] = 0xC60E88
        report["font_manager_global"] = 0xC60ED0
    finally:
        pe.close()
    return report


def exact_dictionary(entries, primary, secondary, mode="bilingual"):
    """Only whole raw strings with an unambiguous complete pair are admitted."""
    candidates = {}
    for entry in entries:
        texts = entry["texts"]
        pair = (
            (texts[primary], texts[secondary]) if primary in texts and secondary in texts else None
        )
        for source in set(texts.values()):
            if source.strip():
                candidates.setdefault(source, set()).add(pair)
    result = {}
    for source, pairs in candidates.items():
        if len(pairs) != 1 or None in pairs:
            continue
        first, second = next(iter(pairs))
        if first and second and first != second:
            if mode == "annotation":
                # The game's own ruby syntax is <R>base</Rannotation>.
                # Nested controls/newlines need separate surface adaptation.
                if any(c in first + second for c in "<>\r\n"):
                    continue
                result[source] = "<R>" + first + "</R" + second + ">"
            elif mode == "primary":
                result[source] = first
            else:
                result[source] = second if mode == "secondary" else first + "\n" + second
    return result


class NativeLabels:
    def __init__(self, callback):
        self.callback = callback
        self.session = None
        self.script = None
        self.exited = threading.Event()

    def attach(
        self,
        pid,
        exe,
        dictionary=None,
        *,
        model=None,
        config=None,
        mode="annotation",
        cache_path=None,
        report=None,
    ):
        if self.session is not None:
            raise RuntimeError("Native experiment is already attached")
        # source_language may already have produced this version-verified
        # report during the short, hook-free startup probe.
        report = native_report(exe) if report is None else dict(report)
        report["diagnostics"] = bool((config or {}).get("diagnostics", False))
        source = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "sora_bilingual/game/scripts/runtime_text.js",
                "sora_bilingual/game/scripts/runtime_paragraph.js",
                "sora_bilingual/game/scripts/runtime_identity.js",
                "sora_bilingual/game/scripts/native_hash.js",
                "sora_bilingual/game/scripts/native_geometry.js",
                "sora_bilingual/game/scripts/native_parser.js",
                "sora_bilingual/game/scripts/native_measure.js",
                "sora_bilingual/game/scripts/native_agent.js",
                "sora_bilingual/game/scripts/native_transport.js",
            )
        )
        self.session = frida.attach(pid)

        def detached(reason, *args):
            try:
                self.callback({"type": "detached", "reason": reason})
            finally:
                self.exited.set()

        self.session.on("detached", detached)
        try:
            # A game discovered at process creation has not loaded its text
            # manager yet. This read-only probe installs no hooks and is safe
            # to unload; the resident hooked script below is never unloaded.
            if report.get("text_table_global"):
                probe = self.session.create_script(
                    """rpc.exports={ready(){try{
                  const base=Process.getModuleByName('sora_2nd.exe').base;
                  const manager=base.add("""
                    + str(report["text_table_global"])
                    + """).readPointer();
                  if(manager.isNull())return false;
                  const table=manager.add(0x6b8).readPointer();if(table.isNull())return false;
                  const count=table.add(0x30).readU32();
                  return count>0&&count<=20000&&!table.add(0x10).readPointer().isNull()
                    &&!table.add(0x20).readPointer().isNull()&&!table.add(0x28).readPointer().isNull();
                }catch(e){return false;}}};"""
                )
                probe.load()
                while not probe.exports_sync.ready():
                    if self.exited.wait(0.25):
                        raise RuntimeError("游戏在初始化期间退出")
                probe.unload()
            self.script = self.session.create_script(
                "const REPORT=" + json.dumps(report) + ";\n" + source, runtime="v8"
            )
            startup_errors = []

            def on_message(message, _):
                value = message.get(
                    "payload",
                    {"type": "error", "message": message.get("description", str(message))},
                )
                if value.get("type") == "error":
                    startup_errors.append(value["message"])
                self.callback(value)

            self.script.on("message", on_message)
            self.script.load()
            if startup_errors:
                raise RuntimeError(startup_errors[0])
            if model is not None:
                self.load(model, config, mode, cache_path=cache_path)
            else:
                self.script.exports_sync.configure(dictionary or {}, False, 1)
        except Exception:
            # The caller keeps this session alive, disabled, until process exit.
            # Even startup failure must not hot-unload installed trampolines.
            try:
                self.disable()
            except Exception:
                pass
            raise

    def configure(self, dictionary, enabled, annotation_scale=0.9):
        return self.script.exports_sync.configure(dictionary, enabled, annotation_scale)

    def load(self, model, config, mode, *, cache_path=None):
        rpc = self.script.exports_sync
        if cache_path is not None:
            from sora_bilingual.localization.model_wire import prepare_wire

            try:
                path = prepare_wire(cache_path, model).resolve()
                return rpc.modelpackedfile(
                    str(path),
                    mode,
                    bool(config["enabled"]),
                    config.get("annotation_scale", 0.9),
                    {
                        k: config[k]
                        for k in (
                            "ruby_scale",
                            "ruby_gap",
                            "ruby_offset_x",
                            "line_gap",
                            "secondary_color",
                            "secondary_opacity",
                            "bilingual_offset_y",
                        )
                        if k in config
                    },
                )
            except frida.RPCException, OSError, ValueError:
                # Corrupt/unsupported cache keeps the active model intact.
                # The existing bounded transfer is the compatibility fallback.
                if model is None:
                    raise
        token = uuid.uuid4().hex
        rpc.modelbegin(token)
        try:
            # ASCII keeps both Python and JS length/index accounting identical.
            # Frida escapes non-ASCII RPC args, which previously made one model
            # exceed the transport's single-message capacity and destroy script.
            text = json.dumps(model, separators=(",", ":"), ensure_ascii=True)
            size = 256 * 1024
            count = 0
            for at in range(0, len(text), size):
                rpc.modelpart(token, count, text[at : at + size])
                count += 1
            return rpc.modelcommit(
                token,
                count,
                len(text),
                mode,
                bool(config["enabled"]),
                config.get("annotation_scale", 0.9),
                {
                    k: config[k]
                    for k in (
                        "ruby_scale",
                        "ruby_gap",
                        "ruby_offset_x",
                        "line_gap",
                        "secondary_color",
                        "secondary_opacity",
                        "bilingual_offset_y",
                    )
                    if k in config
                },
            )
        except Exception:
            try:
                rpc.modelabort(token)
            except Exception:
                pass
            raise

    def select(self, mode, enabled):
        return self.script.exports_sync.select(mode, enabled)

    def reload_logic(self):
        source = "\n".join(
            (ROOT / name).read_text("utf-8")
            for name in (
                "sora_bilingual/game/scripts/runtime_text.js",
                "sora_bilingual/game/scripts/runtime_paragraph.js",
                "sora_bilingual/game/scripts/runtime_identity.js",
            )
        )
        return self.script.exports_sync.reloadlogic(source)

    def style(self, config):
        return self.script.exports_sync.style(
            config.get("annotation_scale", 0.9),
            {
                k: config[k]
                for k in (
                    "ruby_scale",
                    "ruby_gap",
                    "ruby_offset_x",
                    "line_gap",
                    "secondary_color",
                    "secondary_opacity",
                    "bilingual_offset_y",
                )
                if k in config
            },
        )

    def status(self):
        return self.script.exports_sync.status()

    def snapshot(self):
        return self.script.exports_sync.snapshot()

    def disable(self):
        return self.script.exports_sync.disable()

    def replay(self):
        return self.script.exports_sync.replay()

    def detach_if_restored(self):
        # A zero label count did not make Frida hot unloading safe: WER linked
        # the 2026-09-24 fail-fast to frida-agent.dll at detach time. Keep the
        # instrumentation resident, disabled, until the game process exits.
        return self.exited.is_set()
