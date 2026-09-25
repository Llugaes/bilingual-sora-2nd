"""Resident native backend. Mode changes never unload or restart Frida."""

from pathlib import Path
import argparse
import json
import signal
import time
import traceback
import sys
import frida
from sora_bilingual.game.native_runtime import NativeLabels
from sora_bilingual.localization.native_catalog import load_entries, load_model, ready_model
from sora_bilingual.config.native_config import (
    ROOT,
    CONTROL,
    read_config,
    write_config,
    ActionPolicy,
    BackendLock,
)
from sora_bilingual.platform.inputs import InputManager
from sora_bilingual.game.native_loading import ModelPreparation, ConnectionHeartbeat, prepare_fresh
from sora_bilingual.updates.tool_updates import ReleaseWatch
from sora_bilingual.platform.win32 import process_path, foreground_rect


def write_telemetry(value, path):
    """Diagnostics must never stall input for 250 ms or tear down live hooks."""
    try:
        write_config(value, path)
        return True
    except OSError:
        return False


def model_identity(config):
    return tuple(
        json.dumps(config.get(k), sort_keys=True)
        for k in ("primary", "secondary", "game_language", "scope", "sources")
    )


def run(game=None, duration=0):
    connection_started = time.monotonic()
    lock = BackendLock()
    native = None
    heartbeat = None
    try:
        processes = [
            p
            for p in frida.get_local_device().enumerate_processes()
            if p.name.lower() == "sora_2nd.exe"
        ]
        if len(processes) != 1:
            raise RuntimeError("请先自行运行游戏，再启动双语工具。工具不会启动游戏。")
        pid = processes[0].pid
        exe = process_path(pid)
        game = exe.parent if game is None else Path(game)
        if exe.resolve() != (game / "sora_2nd.exe").resolve():
            raise RuntimeError("运行中的游戏路径与配置不符")
        heartbeat = ConnectionHeartbeat(
            write_telemetry,
            ROOT / "generated" / "native-live.json",
            ROOT / "generated" / "native-status.json",
            pid,
        )
        config = read_config()
        config.update(stop=False, replay=False)
        config.pop("capture_controller", None)
        write_config(config)
        initial_raw = CONTROL.read_text(encoding="utf-8")
        with (ROOT / "generated" / "native-probe.jsonl").open("a", encoding="utf-8") as startup_log:
            startup_log.write(
                json.dumps(
                    {
                        "time": time.time(),
                        "type": "connection_start",
                        "pid": pid,
                        "primary": config["primary"],
                        "secondary": config["secondary"],
                    }
                )
                + "\n"
            )
        model_started = time.monotonic()
        model, signature, entries = ready_model(game, config)
        model_seconds = time.monotonic() - model_started
        applied_config = dict(config)
        # A cached locale needs no catalog load. Keep all preparation, including
        # first-time catalog compilation, away from the input/status loop.
        preparation = ModelPreparation(lambda c: prepare_fresh(game, c), model_identity)
        releases = ReleaseWatch()
        last_release_check = 0
        update_notice = None
        entries = None
        inputs = {"switch": InputManager({"hotkey": config["switch_binding"]})}
        # Share one physical SDL snapshot per input tick across all bindings.
        controller = InputManager()
        pad_states = []
        for item in inputs.values():
            item._joystick_provider = lambda: pad_states
        policy = ActionPolicy(config["interaction"])
        mode = policy.base
        if config["interaction"] is None:
            policy.base = config.get("mode", "primary")
            mode = policy.base
        capture_request = None
        capture_action = None
        raw = initial_raw
        last_status = 0
        last_devices = 0
        stopping = False
        error = None
        configuration_error = None
        last_live = 0
        live_key = None
        stop_requested = False

        def request_stop(*_):
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        with (ROOT / "generated" / "native-probe.jsonl").open("a", encoding="utf-8") as out:

            def log(value):
                out.write(json.dumps({"time": time.time(), **value}, ensure_ascii=False) + "\n")
                out.flush()

            native = NativeLabels(log)
            log({"type": "run_start", "pid": pid, "exact_sources": len(model["pairs"])})
            native.attach(pid, exe, model=model, config=config, mode=mode)
            log(
                {
                    "type": "connection_ready",
                    "model_seconds": round(model_seconds, 3),
                    "total_seconds": round(time.monotonic() - connection_started, 3),
                }
            )
            heartbeat.loading("ready")
            print("双语已连接；关闭双语后保留连接，游戏退出时自动结束。", flush=True)
            start = time.monotonic()
            while not native.exited.is_set():
                try:
                    now = time.monotonic()
                    if now - last_release_check >= 1:
                        last_release_check = now
                        changes = releases.poll()
                        if "resident" in changes:
                            update_notice = "底层更新将在游戏下次启动时自动应用；当前连接保持运行"
                        if "logic" in changes:
                            try:
                                native.reload_logic()
                                log(
                                    {
                                        "type": "logic_updated",
                                        "version": releases.current["version"],
                                    }
                                )
                            except frida.RPCException as exc:
                                update_notice = "文本逻辑更新未成功，继续使用当前版本：" + str(exc)
                        if "catalog" in changes:
                            preparation.request(config)
                            heartbeat.loading("preparing")
                            log({"type": "catalog_update", "version": releases.current["version"]})
                    try:
                        text = CONTROL.read_text(encoding="utf-8")
                    except OSError:
                        text = raw
                    next_config = None
                    if text != raw:
                        try:
                            next_config = read_config()
                            configuration_error = None
                        except (ValueError, OSError) as exc:
                            configuration_error = "配置未应用，继续使用上次有效设置：" + str(exc)
                            log({"type": "config_error", "message": str(exc)})
                            raw = text
                    if next_config is not None:
                        stopping = bool(next_config.get("stop"))
                        if next_config["switch_binding"] != config["switch_binding"]:
                            inputs["switch"].update_config(
                                {"hotkey": next_config["switch_binding"]}
                            )
                        if next_config["interaction"] != config["interaction"] or next_config.get(
                            "mode_request"
                        ) != config.get("mode_request"):
                            policy = ActionPolicy(next_config["interaction"])
                            mode = policy.base
                        if next_config["interaction"] is None:
                            policy.base = next_config.get("mode", "primary")
                            mode = policy.base
                        reload = model_identity(next_config) != model_identity(config) or (
                            model_identity(next_config) != model_identity(applied_config)
                            and next_config.get("mode_request") != config.get("mode_request")
                        )
                        layout_changed = any(
                            next_config.get(k) != config.get(k)
                            for k in (
                                "annotation_scale",
                                "ruby_scale",
                                "ruby_gap",
                                "ruby_offset_x",
                                "line_gap",
                            )
                        )
                        if reload:
                            preparation.request(next_config)
                            heartbeat.loading("preparing")
                            log(
                                {
                                    "type": "locale_prepare",
                                    "primary": next_config["primary"],
                                    "secondary": next_config["secondary"],
                                    "game_language": next_config["game_language"],
                                }
                            )
                        if layout_changed:
                            native.style(next_config)
                        native.select(mode, next_config["enabled"] and not stopping and not error)
                        request = next_config.get("capture_controller")
                        if request and request != capture_request:
                            capture_request = request
                            capture_action = next_config.get(
                                "capture_action", next_config["interaction"]
                            )
                            if capture_action != "switch":
                                raise ValueError("未知手柄快捷键模式")
                            controller.begin_controller_capture(30)
                        config = next_config
                        raw = text
                    prepared = preparation.poll()
                    if prepared:
                        prepared_config, new_model, prepare_error = prepared
                        if prepare_error:
                            heartbeat.loading(
                                "ready", "语言索引准备失败，保留当前语言：" + str(prepare_error)
                            )
                            log(
                                {
                                    "type": "locale_error",
                                    "stage": "prepare",
                                    "message": str(prepare_error),
                                }
                            )
                        else:
                            heartbeat.loading("applying")
                            load_start = time.monotonic()
                            try:
                                native.load(
                                    new_model,
                                    {
                                        **config,
                                        "enabled": config["enabled"] and not stopping and not error,
                                    },
                                    mode,
                                )
                            except frida.RPCException as exc:
                                heartbeat.loading(
                                    "ready", "语言切换未成功，保留当前语言：" + str(exc)
                                )
                                log({"type": "locale_error", "stage": "apply", "message": str(exc)})
                            else:
                                model = new_model
                                applied_config = dict(config)
                                heartbeat.loading("ready")
                                log(
                                    {
                                        "type": "locale_applied",
                                        "primary": config["primary"],
                                        "secondary": config["secondary"],
                                        "apply_seconds": round(time.monotonic() - load_start, 3),
                                    }
                                )
                    if stop_requested or (duration and now - start > duration):
                        stopping = True
                        stop_requested = False
                        duration = 0
                        native.disable()
                    pads_bound = any(
                        b.get("gamepad", {}).get("buttons") or b.get("gamepad", {}).get("axes")
                        for b in (config["switch_binding"],)
                    )
                    if (
                        pads_bound
                        or controller.capture_status in ("recording", "release_to_save")
                        or now - last_devices >= 1
                    ):
                        pad_states = controller.devices()
                        last_devices = now
                    active = bool(foreground_rect(pid)) and not stopping and not error
                    states = {a: i.poll_state(active) for a, i in inputs.items()}
                    desired = policy.advance(states["switch"])
                    if desired != mode:
                        mode = desired
                        native.select(mode, config["enabled"] and not stopping and not error)
                    binding = controller.poll_capture()
                    if binding and capture_action:
                        latest = read_config()
                        latest["switch_binding"]["gamepad"] = binding["gamepad"]
                        latest.pop("capture_controller", None)
                        write_config(latest)
                    # Lightweight UI telemetry: input edges immediately, heartbeat
                    # four times/second. No extra RPC or native pointer reads.
                    next_live = (
                        mode,
                        policy.base,
                        config["interaction"] == "language_hold" and states["switch"].held,
                        config["enabled"] and not stopping and not error,
                        policy.interaction,
                        error,
                    )
                    if next_live != live_key or now - last_live >= 0.25:
                        heartbeat.update(
                            0,
                            {
                                "running": True,
                                "pid": pid,
                                "updated_at": time.time(),
                                "render_mode": mode,
                                "base_mode": policy.base,
                                "hold_active": next_live[2],
                                "enabled": bool(next_live[3]),
                                "interaction": policy.interaction,
                                "primary": applied_config["primary"],
                                "secondary": applied_config["secondary"],
                                "game_language": applied_config["game_language"],
                                "mode_request": config.get("mode_request"),
                                "error": error,
                            },
                        )
                        last_live = now
                        live_key = next_live
                    if now - last_status >= 1:
                        state = native.status()
                        if state["failed"]:
                            error = (
                                "原生处理已停用："
                                + str(state.get("failureReason") or "未知异常")
                                + "；请退出游戏后重新启动工具。"
                            )
                            native.disable()
                        heartbeat.update(
                            1,
                            {
                                **state,
                                "running": True,
                                "pid": pid,
                                "updated_at": time.time(),
                                "coverage": model.get("coverage", {}),
                                "configuration_error": configuration_error,
                                "update_notice": update_notice,
                                "render_mode": mode,
                                "stopping": stopping,
                                "error": error,
                                "capture_status": controller.capture_status,
                                "devices": [d.name for d in pad_states],
                                "binding": config["hotkeys"],
                                "resident": True,
                            },
                        )
                        # JS-owned snapshots only; no background pointer reads.
                        if config.get("diagnostics", False):
                            write_telemetry(
                                native.snapshot(), ROOT / "generated" / "native-labels.json"
                            )
                        last_status = now
                    time.sleep(0.008)
                except frida.InvalidOperationError:
                    if native.exited.wait(0.2):
                        break
                    raise
                except (ValueError, OSError) as exc:
                    log({"type": "config_error", "message": str(exc)})
                    time.sleep(0.25)
    finally:
        if heartbeat is not None:
            heartbeat.close()
        if native is not None and native.session is not None and not native.exited.is_set():
            failure = traceback.format_exc() if sys.exc_info()[0] else "后端停止，等待游戏退出"
            try:
                (ROOT / "generated" / "native-error.log").write_text(failure, encoding="utf-8")
            except OSError:
                pass
            try:
                native.disable()
            except Exception:
                pass
            # No detach while callbacks may still be on the game's stack.
            # Hidden labels restore on their next native update, never by RPC.
            while not native.exited.wait(0.5):
                write_telemetry(
                    {
                        "running": True,
                        "enabled": False,
                        "error": "处理已暂停，请退出游戏后重新启动工具。",
                        "resident": True,
                        "pid": pid,
                        "updated_at": time.time(),
                    },
                    ROOT / "generated" / "native-status.json",
                )
        write_telemetry(
            {"running": False, "updated_at": time.time()}, ROOT / "generated" / "native-status.json"
        )
        write_telemetry(
            {"running": False, "updated_at": time.time()}, ROOT / "generated" / "native-live.json"
        )
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-dir",
        type=Path,
        help="optional override; normally use the running game executable directory",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="disable after N seconds; stay resident until game exit",
    )
    parser.add_argument(
        "--prepare", action="store_true", help="build caches only; never attach/start game"
    )
    args = parser.parse_args()
    if args.prepare:
        if args.game_dir is None:
            parser.error("--prepare 需要用 --game-dir 指定离线游戏目录")
        entries, signature = load_entries(args.game_dir)
        load_model(entries, signature, read_config(), game=args.game_dir)
        print("离线索引准备完成：", len(entries))
        return
    try:
        run(args.game_dir, args.duration)
    except Exception as exc:
        path = ROOT / "generated" / "native-error.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(traceback.format_exc(), encoding="utf-8")
        print(str(exc), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
