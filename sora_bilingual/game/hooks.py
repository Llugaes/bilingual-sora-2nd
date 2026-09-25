"""Version-bound Frida capture. Source signatures: 0xDC00/scripts, Tomrock645, MIT."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import pefile

TARGET_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"
BUILD_ID = "25386012"
HOOKS = [
    ("dialogue", "e8 ?? ?? ?? ?? ?? 01 be", 0),
    ("pokerDialogue1", "e8 ?? ?? ?? ?? ?? 8d 8d 80 07 00 00 ba 08 00 00 00 0f 1f 00", 0),
    ("pokerDialogue2", "e8 ?? ?? ?? ?? ?? 8d 8d 80 07 00 00 ba 08 00 00 00 66 66 0f 1f 84", 0),
    (
        "blackJackDialogue1",
        "e8 ?? ?? ?? ?? ?? 8d 8d 80 07 00 00 ba 08 00 00 00 66 90 0f 10 00 0f",
        0,
    ),
    ("blackJackDialogue2", "e8 ?? ?? ?? ?? ?? 8d 8d 80 07 00 00 ba 08 00 00 00 90 0f 10", 0),
    ("rouletteDialogue", "e8 ?? ?? ?? ?? ?? 8d 8d 70 03 00 00 ?? b8 08", 0),
]


def signature_matches(data: bytes, pattern: str):
    regex = b"".join(b"." if v == "??" else re.escape(bytes.fromhex(v)) for v in pattern.split())
    # Search can use the literal-prefix accelerator. Advancing by one still
    # counts overlapping matches, so ambiguous signatures continue to fail.
    compiled = re.compile(regex, re.DOTALL)
    matches = []
    start = 0
    while start <= len(data) and (match := compiled.search(data, start)):
        matches.append(match.start())
        start = match.start() + 1
    return matches


def verify_target(exe: Path):
    raw = exe.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != TARGET_SHA256:
        raise ValueError("游戏 EXE 版本未验证，停止连接。需要为新版本重新适配。")
    # Header/sections are sufficient. Import and unwind directories are not
    # used by version/signature verification and are expensive to decode.
    pe = pefile.PE(data=raw, fast_load=True)
    if pe.FILE_HEADER.Machine != 0x8664:
        raise ValueError("需要 64 位 sora_2nd.exe")
    hooks = []
    for name, pattern, offset in HOOKS:
        addresses = []
        for section in pe.sections:
            if section.Characteristics & 0x20000000:
                addresses += [
                    section.VirtualAddress + n + offset
                    for n in signature_matches(section.get_data(), pattern)
                ]
        if len(addresses) != 1:
            raise ValueError(f"{name} 签名匹配 {len(addresses)} 处，停止连接")
        rva = addresses[0]
        hooks.append({"name": name, "rva": rva, "bytes": pe.get_data(rva, 16).hex()})
    pe.close()
    return {"sha256": digest, "build": BUILD_ID, "hooks": hooks}


def script_source(report):
    # No remote services, clipboard writes, input injection or game-file writes.
    # Read at the verified call site while the pointer is valid; never defer a
    # read from a caller-owned temporary pointer as the original script does.
    return (
        """
'use strict';
const hooks = """
        + json.dumps(report["hooks"])
        + """;
const module = Process.getModuleByName('sora_2nd.exe');
const listeners = [];
try {
    for (const hook of hooks) {
        const address = module.base.add(hook.rva);
        const current = Array.from(new Uint8Array(address.readByteArray(16)))
          .map(x => x.toString(16).padStart(2, '0')).join('');
        if (current !== hook.bytes) throw new Error('Runtime bytes changed: ' + hook.name);
    }
    for (const hook of hooks) {
        listeners.push(Interceptor.attach(module.base.add(hook.rva), {
            onEnter() {
                try {
                    const p = this.context.rdx;
                    if (p.isNull()) { send({type:'text', text:'', hook:hook.name}); return; }
                    const text = p.readUtf8String();
                    if (text !== null && text.length <= 16384)
                        send({type:'text', text, hook:hook.name});
                } catch (e) { send({type:'read_error', message:String(e)}); }
            }
        }));
    }
    send({type:'ready', count:listeners.length});
} catch(e) {
    for (const listener of listeners) listener.detach();
    throw e;
}
"""
    )


class Capture:
    def __init__(self, on_event):
        self.on_event = on_event
        self.session = None
        self.script = None

    def attach(self, pid: int, exe: Path):
        import frida

        report = verify_target(exe)
        self.close()
        self.session = frida.attach(pid)
        self.session.on("detached", lambda *args: self.on_event({"type": "detached"}))
        try:
            self.script = self.session.create_script(script_source(report))
            self.script.on("message", self._message)
            self.script.load()
        except Exception:
            self.close()
            raise

    def _message(self, message, data):
        if message.get("type") == "send":
            self.on_event(message["payload"])
        elif message.get("type") == "error":
            self.on_event({"type": "error", "message": message.get("description", str(message))})

    def close(self):
        if self.session is not None:
            session, self.session = self.session, None
            self.script = None
            try:
                session.detach()
            except Exception:
                pass  # Already-exited process is also fully detached.
