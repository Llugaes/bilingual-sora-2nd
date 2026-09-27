"""Execute the verified S/s size arithmetic in a disposable local Frida host.

This is deliberately a metric regression, not a game hook.  It copies the
post-parse S/s arithmetic at ``sora_2nd.exe!0x5867de..0x58687e`` into a private
page, repoints its two RIP globals to fixture-owned table/font objects, then
lets the production native parser scale hook consume the resulting fields.
"""

from __future__ import annotations

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


ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "sora_bilingual/game/scripts/native_parser.js"
AGENT = ROOT / "sora_bilingual/game/scripts/native_agent.js"
PARSER_SOURCE = PARSER.read_text("utf-8")
PE_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"
START = 0x5867DE
END = 0x58687E


def game_bytes(exe: Path) -> bytes:
    """Read only the formula after S/s numeric parsing has succeeded."""
    assert exe.is_file(), f"missing game executable: {exe}"
    with exe.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    assert digest == PE_SHA256, f"unexpected executable sha256: {digest}"
    pe = pefile.PE(str(exe), fast_load=True)
    # The recorded native report uses module-relative addresses.  This PE is
    # image-base 0x140000000, so treating 0x5867de as a legacy VA would point
    # outside the image; it is the RVA used by the loader report.
    offset = pe.get_offset_from_rva(START)
    with exe.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(END - START)
    assert len(data) == END - START == 0xA0
    return data


def extracted_absolute_factor() -> str:
    """Return the current production method body without reproducing its formula."""
    source = AGENT.read_text("utf-8")
    marker = "    absoluteFactor(row,factor) {"
    start = source.index(marker)
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1].strip()
    raise AssertionError("unterminated rubyContextCallbacks.absoluteFactor")


def disassembly(data: bytes) -> list[dict[str, object]]:
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    rows = [
        {"address": f"0x{item.address:x}", "mnemonic": item.mnemonic, "op_str": item.op_str}
        for item in engine.disasm(data, START)
    ]
    expected = {
        "0x5867de": "movss xmm6, dword ptr [rbx + 0x158]",
        "0x5867e6": "divss xmm6, dword ptr [rbx + 0x15c]",
        "0x5867ee": "mov rsi, qword ptr [rip + 0x6da693]",
        "0x586828": "mov eax, dword ptr [rsi + rax*4 + 0x578]",
        "0x586837": "mov ecx, dword ptr [r15 + 0x300]",
        "0x58683e": "mov rax, qword ptr [rip + 0x6da68b]",
        "0x586853": "mov eax, dword ptr [rcx + 0x28]",
        "0x58686e": "movss dword ptr [rbx + 0x158], xmm1",
        "0x586876": "movss dword ptr [rbx + 0x15c], xmm2",
    }
    actual = {str(row["address"]): f"{row['mnemonic']} {row['op_str']}" for row in rows}
    for address, instruction in expected.items():
        assert actual.get(address) == instruction, (address, actual.get(address), instruction)
    return rows


def agent_source(formula: bytes, absolute_factor: str) -> str:
    # The clone starts *after* the real parser's call to 0x589300.  Its parsed
    # command number is supplied in the same stack slot ([rsp+0x40]) that the
    # real arithmetic reads.  The parser itself never sees a fabricated final
    # scale; the copied instructions write both scale fields before the native
    # parser C module applies the registered factor.
    return (
        PARSER_SOURCE
        + "\nconst FORMULA="
        + json.dumps(list(formula))
        + "\nfunction productionRubyContextCallbacks(base){const REPORT={font_manager_global:0x188};return {"
        + absolute_factor
        + "};}\n"
        + r""";
function check(value,message){if(!value)throw Error(message);}
function close(a,b){return Math.abs(a-b)<=0.000002;}
function readScales(parser){return [parser.add(0x158).readFloat(),parser.add(0x15c).readFloat()];}
function writeScales(parser,value){parser.add(0x158).writeFloat(value);parser.add(0x15c).writeFloat(value);}
function patchRel32(bytes,offset,from,target){
    const delta=target.sub(from).toInt32();
    new DataView(bytes.buffer).setInt32(offset,delta,true);
}
function createFormula(withGate=false){
    // Formula code, its two RIP slots, and all fixture globals have one owner.
    const arena=Memory.alloc(Process.pageSize*4), tableSlot=arena.add(0x180), fontSlot=arena.add(0x188);
    const table=arena.add(0x400), fontManager=arena.add(0xd00), fontList=arena.add(0xe00);
    const face0=arena.add(0xf00), faceLabel=arena.add(0x1000), code=arena.add(Process.pageSize*2);
    tableSlot.writePointer(table); fontSlot.writePointer(fontManager);
    // This uses the same two real global shapes: C60E88 gives S/s rows at
    // +578 and the ruby pixel size at +6a8; C60ED0 gives label font records.
    table.add(0x6a8).writeU32(18);
    fontManager.add(8).writePointer(fontList); fontManager.add(0x10).writeU64(2);
    fontList.writePointer(face0); fontList.add(8).writePointer(faceLabel);
    const clone=new Uint8Array(FORMULA); const tableRip=0x10, fontRip=0x60;
    check(clone[tableRip]===0x48&&clone[tableRip+1]===0x8b&&clone[tableRip+2]===0x35,'table RIP instruction changed');
    check(clone[fontRip]===0x48&&clone[fontRip+1]===0x8b&&clone[fontRip+2]===0x05,'font RIP instruction changed');
    const formulaOffset=0x100, formulaAddress=code.add(formulaOffset);
    patchRel32(clone,tableRip+3,formulaAddress.add(tableRip+7),tableSlot);
    patchRel32(clone,fontRip+3,formulaAddress.add(fontRip+7),fontSlot);
    // The copied branch returns to an owned thunk instead of jumping to the
    // game's shared C/B/R command exit.  It therefore cannot exercise colour.
    const thunk=Uint8Array.from([0x53,0x56,0x41,0x57,0x48,0x83,0xec,0x50,0x48,0x89,0xcb,0x49,0x89,0xd7,
        0x44,0x89,0x44,0x24,0x38,0xe8,0,0,0,0,0x48,0x83,0xc4,0x50,0x41,0x5f,0x5e,0x5b,0xc3]);
    const callNext=code.add(24);
    patchRel32(thunk,20,callNext,formulaAddress);
    const formulaEnd=formulaOffset+clone.length,gateOffset=0x800,gate=code.add(gateOffset);
    const out=new Uint8Array(withGate?gateOffset+17:formulaEnd+1); out.set(thunk,0); out.set(clone,formulaOffset);
    if(withGate){
        out[formulaEnd]=0xe9;patchRel32(out,formulaEnd+1,code.add(formulaEnd+5),gate);
        out.fill(0x90,gateOffset,gateOffset+16);out[gateOffset+16]=0xc3;
    }else out[formulaEnd]=0xc3;
    Memory.patchCode(code,out.length,writable=>writable.writeByteArray(out.buffer));
    check(Memory.protect(code,Process.pageSize,'r-x'),'could not protect cloned formula');
    return {arena,table,face0,faceLabel,gate,run:new NativeFunction(code,'void',['pointer','pointer','uint'])};
}
function commandRow(formula,command,pixels){formula.table.add(0x578+command*4).writeU32(pixels);}
function labelNormal(labelPixels,font){
    const label=Memory.alloc(0x308); label.add(0x304).writeU32(labelPixels);
    return label.add(0x304).readU32()/font;
}
function nativeOnly(formula,font,labelPixels,command,normalSecondary){
    formula.face0.add(0x28).writeU32(font); formula.faceLabel.add(0x28).writeU32(font);
    const label=Memory.alloc(0x308); label.add(0x300).writeU32(1); label.add(0x304).writeU32(labelPixels);
    const parser=Memory.alloc(0x200); writeScales(parser,normalSecondary); formula.run(parser,label,command);
    return readScales(parser);
}
function scaled(formula,listener,font,labelPixels,command,normalSecondary,factor){
    formula.face0.add(0x28).writeU32(font); formula.faceLabel.add(0x28).writeU32(font);
    const label=Memory.alloc(0x308); label.add(0x300).writeU32(1); label.add(0x304).writeU32(labelPixels);
    const parser=Memory.alloc(0x200); writeScales(parser,normalSecondary); listener.trackScale(parser,factor);
    formula.run(parser,label,command); check(listener.applySize(parser),'native size tracker rejected bounded scales');
    return readScales(parser);
}
function productionScale(formula,label,factor){
    return productionRubyContextCallbacks(formula.arena).absoluteFactor({pointer:label},factor);
}
function candidateDirect(formula,listener,parser,font,labelPixels,command,normalSecondary){
    formula.face0.add(0x28).writeU32(font); formula.faceLabel.add(0x28).writeU32(font);
    const label=Memory.alloc(0x308); label.add(0x300).writeU32(1); label.add(0x304).writeU32(labelPixels);
    const sizeFactor=productionScale(formula,label,normalSecondary);
    writeScales(parser,normalSecondary); listener.set(parser,{factor:normalSecondary,sizeFactor,placement:false});
    formula.run(parser,label,command); check(listener.applySize(parser),'production direct size application rejected bounded scales');
    return {sizeFactor,scales:readScales(parser)};
}
function candidateGate(formula,listener,parser,font,labelPixels,command,normalSecondary){
    formula.face0.add(0x28).writeU32(font); formula.faceLabel.add(0x28).writeU32(font);
    const label=Memory.alloc(0x308); label.add(0x300).writeU32(1); label.add(0x304).writeU32(labelPixels);
    const sizeFactor=productionScale(formula,label,normalSecondary);
    writeScales(parser,normalSecondary); listener.set(parser,{factor:normalSecondary,sizeFactor,placement:false});
    formula.run(parser,label,command);
    return {sizeFactor,scales:readScales(parser)};
}
function resourceOnlyText(){
    // Proven separate from colour: this is an S/s post-parse slice; the
    // C-success branch at 0x5867a4..0x5867b7 and shared exit are not cloned.
    return {formula_start:'0x5867de',formula_end_exclusive:'0x58687e',colour_branch_excluded:true};
}
rpc.exports={run(){
    const formula=createFormula(),gateFormula=createFormula(true),oldListener=createNativeParser(new Map(),error=>{throw error;}),
        directListener=createNativeParser(new Map(),error=>{throw error;}),gateListener=createNativeParser(new Map(),error=>{throw error;});
    const gateHook=Interceptor.attach(gateFormula.gate,{onEnter:gateListener.sizeOnEnter});Interceptor.flush();
    const directParser=Memory.alloc(0x200),gateParser=Memory.alloc(0x200);
    const commands={0:16,3:32,5:48,6:64}; for(const [command,pixels] of Object.entries(commands)){commandRow(formula,Number(command),pixels);commandRow(gateFormula,Number(command),pixels);}
    const cases=[];
    for(const font of [32,48,64]) for(const labelPixels of [26,32]) for(const rubyScale of [.5,.8,.9,1])
        for(const [commandText,pixels] of Object.entries(commands)) {
            const command=Number(commandText), nativeNormal=18/font, primaryNormal=labelNormal(labelPixels,font);
            const secondaryNormal=Math.fround(nativeNormal*rubyScale), native= nativeOnly(formula,font,labelPixels,command,secondaryNormal)[0];
            const oldFactor=secondaryNormal;
            const old=scaled(formula,oldListener,font,labelPixels,command,secondaryNormal,oldFactor)[0];
            const direct=candidateDirect(formula,directListener,directParser,font,labelPixels,command,secondaryNormal);
            const gated=candidateGate(gateFormula,gateListener,gateParser,font,labelPixels,command,secondaryNormal);
            const expected=Math.fround(secondaryNormal*(pixels/labelPixels));
            check(close(native,pixels/font),'copied formula did not read fixture globals for S'+command+' font '+font);
            check(close(direct.sizeFactor,secondaryNormal/primaryNormal),'production absoluteFactor failed S'+command+' font '+font+' label '+labelPixels);
            check(close(direct.scales[0],expected),'production set/applySize failed S'+command+' font '+font+' label '+labelPixels);
            check(close(gated.scales[0],expected),'production set/sizeOnEnter gate failed S'+command+' font '+font+' label '+labelPixels);
            const oldMatches=close(old,expected);
            if(font!==labelPixels)check(!oldMatches,'old coordinate unexpectedly passed non-unit primary baseline');
            cases.push({font,label_pixels:labelPixels,ruby_scale:rubyScale,command,pixels,
                primary_normal:primaryNormal,secondary_normal:secondaryNormal,native_s:native,
                old_factor:oldFactor,size_factor:direct.sizeFactor,old_final:old,expected,direct:direct.scales[0],gated:gated.scales[0],
                old_matches_expected:oldMatches,old_red:!oldMatches});
        }
    const key=cases.find(row=>row.font===64&&row.label_pixels===32&&row.ruby_scale===.8&&row.command===5);
    check(key&&key.old_red&&close(key.old_final,.16875)&&close(key.expected,.3375),'documented font64/label32/S5 red case changed');
    const controls=cases.filter(row=>row.font===row.label_pixels); check(controls.length===16&&controls.every(row=>!row.old_red),'unit-primary controls changed');
    gateHook.detach();Interceptor.flush();
    return {all_passed:true,game_attached:false,host:'self-created-hidden-python',resourceOnly:resourceOnlyText(),
        fixture:{ruby_pixels:18,command_pixels:commands,global_shapes:{table:'+0x578 and +0x6a8',font_manager:'font list -> record +0x28',label_size:'label+0x304'}},
        cases,key_red:key,controls:controls.length,stats:{old:oldListener.status(),direct:directListener.status(),gate:gateListener.status()}};
}};
"""
    )


def markdown(report: dict[str, object]) -> str:
    key = report["key_red"]
    rows = report["cases"]
    red = sum(1 for row in rows if row["old_red"])
    return f"""# 131：S/s 字号坐标诊断

离线隐藏宿主执行了磁盘 `sora_2nd.exe` 的真实 S/s 后置算术，范围
`0x5867de..0x58687e`（`0xa0` 字节，SHA-256 `{PE_SHA256}`）。该范围从
成功解析 S/s 数字后的 `[rsp+0x40]` 开始，读取 `parser+0x158/+0x15c`、
`C60E88+0x578` 的字号表、`label+0x300` 指向的字体记录 `+0x28`，再写回两个
parser 字段。相对主文的普通比例从同一 label 的实际字号字段 `+0x304` 读取。隐藏宿主
只把两个 RIP 指针改指向自己的等形状 table/font globals；
没有附加、注入或读取游戏进程。

测试命令号为 0/3/5/6；字号行 16/32/48/64 是宿主注入的表值，用来验证真实取表和
除字体基准的指令链，并不声称
这是离线磁盘中全局指针运行时所指表的生产值。

在 font=64、label=32、ruby=0.8、S5=48 的真实算术回放中：普通副文
`{key["secondary_normal"]:.5f}`，S 后的原生绝对比例 `{key["native_s"]:.5f}`；旧登记
`factor=普通副文` 得到 `{key["old_final"]:.5f}`，小于普通副文。相对主文的期望是
`{key["expected"]:.5f}`，当前生产 `absoluteFactor` 经 `set`/`applySize` 得到
`{key["direct"]:.5f}`，经实际 `sizeOnEnter` gate 得到 `{key["gated"]:.5f}`。这是旧坐标混用的红例。

共执行 {len(rows)} 个有界组合（font 32/48/64、label 26/32、ruby 0.5/0.8/0.9/1、
S 0/3/5/6）；其中旧坐标在 {red} 个非单位主文基准组合失败，font=label 的
{report["controls"]} 个对照按预期相等。普通无 S/s 路径没有执行该克隆，颜色成功分支
`0x5867a4..0x5867b7` 与公共出口未包含在复制范围，故本诊断不会改变或模拟颜色／嵌套
原生 R 的既有行为。

当前候选为 S/s 后置写回登记相对主文倍率：
`secondaryNativeAfterRubyScale / primaryNormalScale`；保留现有 `factor` 用于普通
注音及嵌套 R 的实际递归比例。候选的游戏画面仍需要新游戏进程实机验证。
"""


def main(exe: Path | None = None) -> None:
    environment = os.environ.get("SORA_GAME_EXE")
    exe = exe or (Path(environment) if environment else None)
    if exe is None:
        print(
            json.dumps(
                {
                    "skipped": True,
                    "reason": "pass --exe or set SORA_GAME_EXE to the verified sora_2nd.exe",
                    "game_started": False,
                    "game_attached": False,
                },
                indent=2,
            )
        )
        return
    formula = game_bytes(exe)
    instructions = disassembly(formula)
    absolute_factor = extracted_absolute_factor()
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(agent_source(formula, absolute_factor), runtime="v8")
        script.load()
        report = script.exports_sync.run()
        assert report["all_passed"]
    finally:
        if host.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(host.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        if session is not None:
            try:
                session.detach()
            except frida.InvalidOperationError:
                pass
        host.wait(timeout=5)
    report["disk"] = {
        "exe": str(exe),
        "sha256": PE_SHA256,
        "copied_range": {
            "start": f"0x{START:x}",
            "end_exclusive": f"0x{END:x}",
            "bytes": len(formula),
        },
        "instructions": instructions,
    }
    report["production"] = {
        "native_agent_sha256": hashlib.sha256(AGENT.read_bytes()).hexdigest(),
        "absolute_factor_sha256": hashlib.sha256(absolute_factor.encode()).hexdigest(),
        "absolute_factor_source": absolute_factor,
    }
    (ROOT / "generated/diagnostic-131-size-metrics.json").write_text(
        json.dumps(report, indent=2), "utf-8"
    )
    (ROOT / "generated/diagnostic-131-size-metrics.md").write_text(markdown(report), "utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "key_red": report["key_red"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=Path,
        help="verified sora_2nd.exe; defaults to SORA_GAME_EXE when set",
    )
    args = parser.parse_args()
    main(args.exe)
