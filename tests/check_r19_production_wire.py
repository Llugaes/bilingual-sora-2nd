"""Replay the complete production indexed wire in V8 on an owned hidden host."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import frida

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = Path(os.environ.get("R19_PRODUCT_ROOT", ROOT)).resolve()
PREFIX = os.environ.get("DEV_VERIFICATION_PREFIX", "r19")
NATIVE = r"""
rpc.exports={load(model){globalThis.model=model;globalThis.runtime=new RuntimeText(model);
 return {runtime:Script.runtime,effect_units:model.details.detail_effect_units.length,
         parameter_units:model.details.detail_effect_units.filter(r=>r.parameter_kinds?.length).length};},
run(rows){const result=[];for(const row of rows){
 const tr=globalThis.runtime,source=row.source,key=row.key||'',scope=row.scope||'';
 const primary=tr.translate(source,'primary',key,scope),secondary=tr.translate(source,'secondary',key,scope),
       plan=tr.render(source,'annotation',key,scope);
 if(primary!==row.primary||secondary!==row.secondary||JSON.stringify(plan)!==JSON.stringify(row.plan))
   throw Error('V8 final render differs: '+row.name);
 result.push({name:row.name,level:row.level,roles:plan.layers.filter(l=>l.semantic_ids?.length).length});
}
 const source=rows[0].source,plain=source.replace(/<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g,''),
       conflict=new RuntimeText({...globalThis.model,ambiguous_display:[...globalThis.model.ambiguous_display,source,plain]});
 if(conflict.effectDetailPlan(source)!==null||conflict.render(source).text!==source||conflict.render(source).layers.length)
   throw Error('whole conflict admitted');
 for(const value of ['2147483648','-2147483649','9'.repeat(100)]){
   const original=source.replace('Blind 30%','Blind '+value+'%');
   if(globalThis.runtime.details.effectUnit('Blind '+value+'%')||globalThis.runtime.render(original).text!==original)
     throw Error('native integer overflow admitted');
 }
 for(const value of ['2147483648','-2147483649','9'.repeat(100)])for(const wrapped of [false,true]){
   const original=(wrapped?'<c698>':'')+'Damage dealt to enemies with Seal +'+value+'%'+(wrapped?'</C>':'');
   for(const order of [['primary','secondary','annotation'],['annotation','secondary','primary']]){
     const fresh=new RuntimeText(globalThis.model);
     for(const mode of order){
       const plan=fresh.render(original,mode);
       if(fresh.translate(original,mode)!==original||plan.text!==original||plan.layers.length)
         throw Error('type17 final formatter overflow admitted');
     }
   }
 }
 return {passed:true,rows:result,whole_conflict_rejected:true,i32_overflow_rejected:true,
   type17_final_overflow_rejected:true,game_attached:false};
}};
"""


def main():
    receipt = json.loads((ROOT / f"generated/{PREFIX}-production-receipt.json").read_text("utf-8"))
    replay = json.loads((ROOT / f"generated/{PREFIX}-complete-production.json").read_text("utf-8"))
    wire = (
        Path(receipt["wire_path"])
        if PRODUCT == ROOT
        else PRODUCT
        / "generated"
        / json.loads((PRODUCT / "candidate-cache.json").read_text("utf-8"))["wire_name"]
    )
    digest = hashlib.sha256(wire.read_bytes()).hexdigest()
    if digest != receipt["wire_sha256"] or digest != replay["wire_sha256"]:
        raise RuntimeError("Wire identity changed")
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        if host.pid == 31480:
            raise RuntimeError("Refusing game process")
        session = frida.attach(host.pid)
        script = session.create_script(
            (PRODUCT / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf-8")
            + NATIVE
            + (PRODUCT / "sora_bilingual/game/scripts/native_transport.js").read_text("utf-8"),
            runtime="v8",
        )
        script.load()
        loaded = script.exports_sync.modelpackedfile(str(wire))
        checked = script.exports_sync.run(replay["rows"])
        result = {
            "wire_sha256": digest,
            "wire_bytes": wire.stat().st_size,
            "runtime_text_sha256": hashlib.sha256(
                (PRODUCT / "sora_bilingual/game/scripts/runtime_text.js").read_bytes()
            ).hexdigest(),
            "loaded": loaded,
            "checked": checked,
            "host_kind": "self-created hidden Python",
            "game_attached": False,
            "candidate_live_verified": False,
        }
        result["product_root"] = str(PRODUCT)
        result["frida_module"] = frida.__file__
        output = (
            f"{PREFIX}-production-frida.json"
            if PRODUCT == ROOT
            else f"{PREFIX}-production-frida-package.json"
        )
        (ROOT / "generated" / output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
    finally:
        if session is not None:
            session.detach()
        host.stdin.close()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
