"""Load the complete text resolver in the shipped Frida V8, never in the game."""

from pathlib import Path
import subprocess
import sys
import tempfile

import frida

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sora_bilingual.localization.model_wire import indexed_model


def main():
    source = (
        Path(__file__).resolve().parents[1] / "sora_bilingual/game/scripts/runtime_text.js"
    ).read_text("utf-8")
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    temporary = tempfile.TemporaryDirectory()
    try:
        session = frida.attach(host.pid)
        script = session.create_script(
            source
            + """
rpc.exports={run(){
    const pairs={'幻属性':['Mirage Element','幻屬性'],'属性值':['Value','屬性值'],
        '冻结':['冻结','凍結'],'中毒':['中毒','毒'],'炎伤':['炎伤','炎傷'],'延迟':['延迟','遅延']};
    const runtime=new RuntimeText({pairs,plain_pairs:pairs,
        numeric:[['×([0-9]+)',['x%d','×%d']]]});
    const input='幻属性【 属性值：<I42>×3<I45>×3 】';
    const expected='Mirage Element【 Value：<I42>×3<I45>×3 】';
    if(runtime.translate(input,'primary')!==expected)throw Error('quartz labels or payload changed');
    for(const value of ['×2',' ×３ ','+25%'])
        if(runtime.component(value,'annotation')!==value)throw Error('numeric payload changed');
    const composite='<c698>「冻结·中毒·炎伤·延迟」</C>';
    if(runtime.translate(composite,'secondary')!=='<c698>「凍結·毒·炎傷·遅延」</C>')throw Error('compound labels omitted');
    if(runtime.render(composite).kind==='plain')throw Error('compound annotation omitted');
    return {runtime:Script.runtime,game_attached:false,passed:true};
},load(model){
    const tr=new RuntimeText(model);
    if(!Array.isArray(model.numeric)||model.numeric.length!==20)throw Error('lazy array contract');
    for(let i=0;i<100;i++)if(tr.translate('source'+i,'secondary')!=='訳'+i)throw Error('lazy key contract');
    if(tr.translate('costarring','secondary')!=='collision one'||tr.translate('liquid','secondary')!=='collision two')throw Error('hash collision');
    return {indexed:true,game_attached:false,passed:true};
}};
"""
            + (
                Path(__file__).resolve().parents[1]
                / "sora_bilingual/game/scripts/native_transport.js"
            ).read_text("utf-8"),
            runtime="v8",
        )
        script.load()
        print(script.exports_sync.run())
        pairs = {f"source{i}": [f"source{i}", f"訳{i}"] for i in range(100)}
        pairs.update(
            {"costarring": ["costarring", "collision one"], "liquid": ["liquid", "collision two"]}
        )
        fixture = Path(temporary.name) / "fixture.wire.bin"
        fixture.write_bytes(
            indexed_model(
                {
                    "pairs": pairs,
                    "plain_pairs": pairs,
                    "numeric": [[f"number{i}([0-9]+)", ["%d", "%d"]] for i in range(20)],
                }
            )
        )
        print(script.exports_sync.modelpackedfile(str(fixture)))
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)
        temporary.cleanup()


if __name__ == "__main__":
    main()
