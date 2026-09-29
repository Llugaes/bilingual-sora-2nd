"""Run the game's material rebind method with fixture-owned resources, never the game."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import capstone
import frida
import pefile

from check_native_refresh import script_source

ROOT = Path(__file__).resolve().parents[1]
START, END = 0x588B40, 0x588CFE
EXE_SHA = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"


def fixture(exe):
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == EXE_SHA
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        data = pe.get_data(START, END - START)
        # Label's virtual material refresh slot, also invoked by its constructor.
        assert (
            int.from_bytes(pe.get_data(0xB184B8, 8), "little")
            == pe.OPTIONAL_HEADER.ImageBase + START
        )
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        decoder.detail = True
        fixes = []
        for ins in decoder.disasm(data, START):
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    fixes.append(
                        [
                            ins.address - START + ins.disp_offset,
                            ins.address - START + ins.size,
                            ins.address + ins.size + op.mem.disp,
                            "global",
                        ]
                    )
            if ins.mnemonic == "call":
                fixes.append(
                    [
                        ins.address - START + ins.imm_offset,
                        ins.address - START + ins.size,
                        ins.operands[0].imm,
                        "call",
                    ]
                )
        return {"bytes": list(data), "fixes": fixes}
    finally:
        pe.close()


def check(exe):
    data = fixture(exe)
    source = (ROOT / "sora_bilingual/game/scripts/native_fonts.js").read_text("utf-8")
    source += "\nconst MATERIAL_FIXTURE=" + json.dumps(data) + ";\n" + script_source()
    source += r"""
rpc.exports.materials=()=>{
    const owners=[],keep=p=>(owners.push(p),p),alloc=n=>keep(Memory.alloc(n));
    const arena=alloc(0x4000),code=arena.add(0x2000),face=alloc(48),fonts=alloc(32),vector=alloc(8);
    fonts.add(8).writePointer(vector);fonts.add(16).writeU64(1);vector.writePointer(face);
    const originalImage=alloc(64),candidateImage=alloc(64),layout=alloc(0x2000),manager=alloc(0x48);
    const batch=alloc(48),primitives=alloc(16),glyphA=alloc(48),glyphB=alloc(48);
    const oldMaterial=alloc(0x38),oldShadow=alloc(0x38),shadowBatch=alloc(48);
    let acquired=0,released=0,deleted=0;
    function material(image){const p=alloc(0x38);p.add(0x30).writePointer(image);return p;}
    oldMaterial.add(0x30).writePointer(originalImage);oldShadow.add(0x30).writePointer(originalImage);
    const acquire=keep(new NativeCallback((owner,descriptor)=>{
        check(owner.equals(layout),'wrong layout manager');acquired++;
        return material(descriptor.add(0x18).readPointer());
    },'pointer',['pointer','pointer']));
    const release=keep(new NativeCallback((owner,p)=>{check(!p.isNull(),'null material released');released++;},'void',['pointer','pointer']));
    const destroy=keep(new NativeCallback((owner,p)=>{check(p.equals(shadowBatch),'wrong cached batch freed');deleted++;},'void',['pointer','pointer']));
    const parentClip=keep(new NativeCallback(()=>0,'int',['pointer']));
    const security=keep(new NativeCallback(()=>{},'void',['pointer']));
    const globals={0xBF2040:arena.add(0x800),0xC60ED0:arena.add(0x808),0xC60E88:arena.add(0x810),0xC60EA0:arena.add(0x818)};
    globals[0xC60ED0].writePointer(fonts);globals[0xC60E88].writePointer(layout);globals[0xC60EA0].writePointer(layout);
    const targets={0x581470:parentClip,0x590520:acquire,0x590990:release,0x5B0270:destroy,0x7C9370:security};
    const bytes=new Uint8Array(MATERIAL_FIXTURE.bytes),view=new DataView(bytes.buffer),thunks=new Map();
    let offset=0x800;
    for(const [at,next,target,kind] of MATERIAL_FIXTURE.fixes){
        let destination=globals[target];
        if(kind==='call'){
            check(!!targets[target],'unknown engine dependency');
            if(!thunks.has(target)){
                const thunk=code.add(offset);thunk.writeByteArray([0xff,0x25,0,0,0,0]);thunk.add(6).writePointer(targets[target]);
                thunks.set(target,thunk);offset+=16;
            }
            destination=thunks.get(target);
        }
        check(!!destination,'unknown RIP global '+target.toString(16));
        view.setInt32(at,destination.sub(code.add(next)).toInt32(),true);
    }
    code.writeByteArray(bytes);Memory.protect(code,0x2000,'r-x');
    const report={font_manager_global:0x808,native:{font_rebind:{rva:code.sub(arena).toString()}}};
    const refresh=typeof createFontMaterialRefresh==='function'?createFontMaterialRefresh(arena,report):()=>false;
    function bindInitial(){
        label.add(0x300).writeU32(0);label.add(0x650).writePointer(oldMaterial);label.add(0x658).writePointer(oldShadow);
        label.add(0x680).writePointer(manager);manager.add(0x38).writePointer(batch);manager.add(0x40).writePointer(shadowBatch);
        batch.add(0x18).writePointer(primitives);batch.add(0x20).writeU64(2);
        primitives.writePointer(glyphA);primitives.add(8).writePointer(glyphB);
        glyphA.add(0x20).writePointer(oldMaterial);glyphB.add(0x20).writePointer(oldMaterial);
    }
    const row=prepare({current:'HUD text',wanted:'HUD text',fontChange:true});bindInitial();
    face.add(0x20).writePointer(candidateImage);runtimeFonts.refreshLabel=refresh;
    update(label);
    check(label.add(0x650).readPointer().add(0x30).readPointer().equals(candidateImage),'HUD uses old atlas after font publication');
    check(glyphA.add(0x20).readPointer().equals(label.add(0x650).readPointer())&&glyphB.add(0x20).readPointer().equals(label.add(0x650).readPointer()),'existing glyph primitives keep old material');
    check(manager.add(0x40).readPointer().isNull()&&label.add(0x658).readPointer().isNull(),'shadow material not retired');
    check(acquired===1&&released===2&&deleted===1,'native resource references not balanced');
    update(label);check(acquired===1,'next frame rebound unchanged atlas');
    // A regular setter may overwrite epoch metadata after publication. It
    // must not mark the old atlas as refreshed and mask the following Update.
    face.add(0x20).writePointer(originalImage);fontGeneration++;epoch++;
    row.epoch=epoch;captureMetadata(row);update(label);
    check(label.add(0x650).readPointer().add(0x30).readPointer().equals(originalImage),'setter masked restored font generation');
    check(acquired===2&&released===3&&deleted===1,'restore repeated stale shadow release');
    // Newly constructed controls are already bound to the current atlas.
    row.fontGeneration=undefined;row.epoch=-1;update(label);check(acquired===2,'new control rebuilt a current material');
    // A copied normal material must not hide an old shadow atlas.
    label.add(0x658).writePointer(material(candidateImage));manager.add(0x40).writePointer(shadowBatch);
    row.fontGeneration=undefined;update(label);
    check(acquired===3&&released===5&&deleted===2&&label.add(0x658).readPointer().isNull(),'mixed-generation shadow was retained');
    // Match the real method's index>=count branch: no font is a null image.
    label.add(0x300).writeU32(0xffffffff);label.add(0x650).writePointer(material(ptr(0)));
    row.fontGeneration=undefined;update(label);check(acquired===3,'unbound font index should remain unbound');
    check(!errors.length,JSON.stringify(errors));
    return {passed:true,game_started:false,game_attached:false,engine_bytes_executed:[START,END],acquired,released,deleted,gpu_rendered:false};
};
""".replace("[START,END]", f"[{START},{END}]")
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(source, runtime="v8")
        script.load()
        return script.exports_sync.materials()
    finally:
        if session:
            session.detach()
        host.communicate(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path)
    exe = parser.parse_args().exe or os.environ.get("SORA_GAME_EXE")
    print(
        json.dumps(
            check(Path(exe))
            if exe
            else {"skipped": True, "reason": "pass --exe or set SORA_GAME_EXE"},
            ensure_ascii=False,
        )
    )
