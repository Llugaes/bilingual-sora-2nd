"""Load the complete text resolver in the shipped Frida V8, never in the game."""

from pathlib import Path
import subprocess
import sys

import frida


def main():
    source = (
        Path(__file__).resolve().parents[1] / "sora_bilingual/game/scripts/runtime_text.js"
    ).read_text("utf-8")
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(
            source
            + """
rpc.exports={run(){
    const pairs={'幻属性':['Mirage Element','幻屬性'],'属性值':['Value','屬性值']};
    const runtime=new RuntimeText({pairs,plain_pairs:pairs,
        numeric:[['×([0-9]+)',['x%d','×%d']]]});
    const input='幻属性【 属性值：<I42>×3<I45>×3 】';
    const expected='Mirage Element【 Value：<I42>×3<I45>×3 】';
    if(runtime.translate(input,'primary')!==expected)throw Error('quartz labels or payload changed');
    for(const value of ['×2',' ×３ ','+25%'])
        if(runtime.component(value,'annotation')!==value)throw Error('numeric payload changed');
    return {runtime:Script.runtime,game_attached:false,passed:true};
}};
""",
            runtime="v8",
        )
        script.load()
        print(script.exports_sync.run())
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
