"""Exit/reconnect proof using only our own hidden native host."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from sora_bilingual.game.agent_control import reconnect


def check():
    # venv launchers redirect to another PID; ask a direct host to report itself.
    host = subprocess.Popen(
        [sys.executable, "-c", "import os,sys;print(os.getpid(),flush=True);sys.stdin.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    pid = int(host.stdout.readline())
    code = r'''
import os,sys
from types import SimpleNamespace
from pathlib import Path
import frida
from sora_bilingual.game.agent_control import publish,reconnect
from sora_bilingual.game.native_runtime import NativeLabels
pid=int(sys.argv[1]);path=Path(sys.argv[2]);exe=Path(sys.executable)
if not path.exists():
 session=frida.attach(pid)
 disable=next(line.strip().removesuffix(',') for line in Path('sora_bilingual/game/scripts/native_agent.js').read_text('utf8').splitlines() if line.strip().startswith('disable()'))
 source="""
 let enabled=false,epoch=0;
 const fixture=new CModule('int display(void){return 1;}');
 const display=new NativeFunction(fixture.display,'int',[]);
 Interceptor.attach(fixture.display,{onLeave(value){if(enabled)value.replace(2);}});
 rpc.exports={status(){return {enabled,value:display()};},
 select(mode,active){enabled=active;return true;},
 __DISABLE__};
 """.replace('__DISABLE__',disable)+Path('sora_bilingual/game/scripts/native_control.js').read_text('utf8')
 script=session.create_script(source,runtime='v8');script.load()
 client=publish(script,pid,exe,path)
else:
 session=None;client=reconnect(pid,exe,path)
 assert client.status()=={'enabled':False,'value':1}
assert client.select('annotation',True)
assert client.status()=={'enabled':True,'value':2}
if sys.argv[3]=='normal':
 native=NativeLabels(lambda _:None)
 native.control=client;native.session=session;native.script=SimpleNamespace(exports_sync=client)
 assert native.park()
 assert native.control is None and native.session is None
else:
 os._exit(0)
# Abrupt process exit closes the socket without running any Python cleanup.
'''
    try:
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "agent.json"
            for mode in ("lost-client", "normal", "lost-client", "normal"):
                controller = subprocess.run(
                    [sys.executable, "-X", "utf8", "-c", code, str(pid), str(record), mode],
                    capture_output=True,
                    timeout=20,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                assert controller.returncode == 0, controller.stderr.decode(
                    "utf8", errors="replace"
                )
                assert host.poll() is None, "Tool exit terminated the host"
                # Disconnect cleanup is asynchronous in the host event loop.
                import time

                deadline = time.monotonic() + 3
                while True:
                    try:
                        client = reconnect(pid, sys.executable, record)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.02)
                try:
                    assert client.status() == {"enabled": False, "value": 1}
                    from sora_bilingual.game.agent_control import AgentClient

                    rejected = {**json.loads(record.read_text("utf8")), "token": "0" * 64}
                    try:
                        AgentClient(rejected)
                    except OSError:
                        pass
                    else:
                        raise AssertionError("An unauthenticated client was accepted")
                    assert client.status() == {"enabled": False, "value": 1}
                finally:
                    client.close()
            result = {
                "all_passed": True,
                "controller_processes_exited": 4,
                "host_survived": True,
                "effects_disabled": True,
                "game_started": False,
                "game_attached": False,
            }
            print(json.dumps(result))
    finally:
        host.stdin.close()
        host.wait(timeout=5)
        host.stdout.close()


if __name__ == "__main__":
    if os.name == "nt":
        check()
