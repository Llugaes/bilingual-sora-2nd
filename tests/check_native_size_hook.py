"""Verify the absolute-size jump gateway in a self-created Frida host only."""

import json
from pathlib import Path
import subprocess
import sys

import frida


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "sora_bilingual/game/scripts/native_parser.js").read_text("utf-8")


def script_source():
    return (
        SOURCE
        + r"""
function check(value,message){if(!value)throw Error(message);}
function bytes(pointer,length){return Array.from(new Uint8Array(pointer.readByteArray(length))).map(v=>v.toString(16).padStart(2,'0')).join('');}
function productBits(value,factor){const slot=Memory.alloc(4);slot.writeFloat(Math.fround(Math.fround(value)*factor));return slot.readU32();}
function scales(pointer){return [pointer.add(0x158).readU32(),pointer.add(0x15c).readU32()];}
function assertScales(pointer,value,message){const expected=productBits(value,.3),actual=scales(pointer);check(actual[0]===expected&&actual[1]===expected,message+' '+actual+' != '+expected);}
function putRel32(out,offset,targetOffset,originOffset){
    const displacement=targetOffset-(originOffset+5);check(displacement>=-0x80000000&&displacement<=0x7fffffff,'fixture rel32 out of range');
    out[offset]=0xe9;new DataView(out.buffer).setInt32(offset+1,displacement,true);
}
function makeFixture(){
    const page=Memory.alloc(Process.pageSize),raw=new Uint8Array(0x100).fill(0x90);
    const start=page,open=page.add(0x40),close=page.add(0x80),common=page.add(0xc0),closeExit=common.add(9);
    // Exact relevant PE shape: S/s and C-open enter 0x587462. Successful
    // </C> enters 0x58746b, skipping the first nine common-exit bytes.
    const s=[0x53,0x48,0x89,0xcb,0xf3,0x0f,0x11,0x8b,0x58,0x01,0x00,0x00,
        0xf3,0x0f,0x11,0x93,0x5c,0x01,0x00,0x00];
    raw.set(s,0);putRel32(raw,s.length,0xc0,s.length);
    const copen=[0x53,0x48,0x89,0xcb,0xff,0x83,0x50,0x01,0x00,0x00];
    raw.set(copen,0x40);putRel32(raw,0x40+copen.length,0xc0,0x40+copen.length);
    const cclose=[0x53,0x48,0x89,0xcb,0xff,0x8b,0x50,0x01,0x00,0x00];
    raw.set(cclose,0x80);putRel32(raw,0x80+cclose.length,0xc9,0x80+cclose.length);
    // `41 b2 01; 41 bb 06 00 00 00` is the verified first nine bytes of
    // 0x587462. RBX stays live until after both possible entrances.
    raw.set([0x41,0xb2,0x01,0x41,0xbb,0x06,0x00,0x00,0x00,0x5b,...new Uint8Array(24).fill(0x90),0xc3],0xc0);
    Memory.patchCode(page,raw.length,writable=>writable.writeByteArray(raw.buffer));
    check(Memory.protect(page,Process.pageSize,'r-x'),'fixture code protection failed');
    return {page,start,open,close,common,closeExit,entry:start.add(s.length),
        send:new NativeFunction(start,'void',['pointer','float','float']),
        colorOpen:new NativeFunction(open,'void',['pointer']),colorClose:new NativeFunction(close,'void',['pointer'])};
}
function runSpans(fixture,listener,spans,nested=false){
    const parser=Memory.alloc(0x300);listener.trackScale(parser,.3);
    fixture.send(parser,1.5,1.5);assertScales(parser,1.5,'S5 scale');
    const before=scales(parser);
    const order=[];
    if(nested) {
        for(let i=0;i<spans;i++){fixture.colorOpen(parser);order.push('open');}
        for(let i=0;i<spans;i++){fixture.colorClose(parser);order.push('close');}
    } else for(let i=0;i<spans;i++) {
        fixture.colorOpen(parser);order.push('open');fixture.colorClose(parser);order.push('close');
    }
    return {parser,before,after:scales(parser),depth:parser.add(0x150).readU32(),order};
}
function verifyNormalSequence(fixture,listener,spans,nested=false){
    const caseResult=runSpans(fixture,listener,spans,nested),parser=caseResult.parser;
    check(caseResult.depth===0,'colour depth did not recover');
    assertScales(parser,1.5,'colour span changed S5 scale');
    fixture.send(parser,2,2);assertScales(parser,2,'amplified S scale');
    fixture.send(parser,.8,.8);assertScales(parser,.8,'recovery s scale');
    return caseResult;
}
function directAttachRed(){
    const contexts=new Map(),listener=createNativeParser(contexts,error=>{throw error;}),fixture=makeFixture();
    const original=bytes(fixture.entry,16),direct=Interceptor.attach(fixture.entry,{onEnter:listener.sizeOnEnter});
    Interceptor.flush();
    const zero=runSpans(fixture,listener,0),one=runSpans(fixture,listener,1),sequentialTwo=runSpans(fixture,listener,2),nestedTwo=runSpans(fixture,listener,2,true);
    // Direct attach follows the S/s tail JMP to 0x587462. Each C-open also
    // enters it; C-close starts nine bytes later, so it does not invoke this
    // listener. The real failure is therefore one factor per colour span.
    const once=Math.fround(Math.fround(1.5*.3)*.3);
    const twice=Math.fround(Math.fround(Math.fround(1.5*.3)*.3)*.3);
    check(zero.after[0]===zero.before[0]&&zero.after[1]===zero.before[1],'old direct hook changed zero-colour S5');
    check(one.after[0]===productBits(once,1)&&one.after[1]===productBits(once,1),'old direct hook did not multiply at C open: '+one.after+' expected '+productBits(once,1));
    for(const result of [sequentialTwo,nestedTwo])check(result.after[0]===productBits(twice,1)&&result.after[1]===productBits(twice,1),'old direct hook did not multiply per C open: '+result.after+' expected '+productBits(twice,1));
    const report={entry_before:original,entry_after:bytes(fixture.entry,16),common_after:bytes(fixture.common,8),
        close_exit:String(fixture.closeExit),zero,one,sequential_two:sequentialTwo,nested_two:nestedTwo,status:listener.status()};
    direct.detach();Interceptor.flush();
    return report;
}
function gatewayGreen(){
    const contexts=new Map(),listener=createNativeParser(contexts,error=>{throw error;}),fixture=makeFixture();
    const expected=bytes(fixture.entry,16),hook=listener.installSizeHook(fixture.entry,expected);
    check(hook.continuation.equals(fixture.common),'gateway continuation changed');
    // Interceptor patches the gate's NOP, while the original S/s five-byte
    // branch is the only game-shaped instruction redirected by this helper.
    check(fixture.entry.readU8()===0xe9&&!fixture.entry.equals(hook.gate),'gateway was not installed at the verified S/s branch');
    const destination=fixture.entry.add(5).add(fixture.entry.add(1).readS32());
    check(destination.equals(hook.gate),'S/s branch did not redirect to owned gate');
    check(bytes(fixture.common,9)==='41b20141bb06000000','shared C-open exit was patched');
    const spans=[0,1,2].map(count=>verifyNormalSequence(fixture,listener,count));
    const nestedTwo=verifyNormalSequence(fixture,listener,2,true);
    const plain=Memory.alloc(0x300);fixture.send(plain,1.5,1.5);
    check(scales(plain)[0]===productBits(1.5,1)&&scales(plain)[1]===productBits(1.5,1),'unowned S5 changed');
    fixture.colorOpen(plain);fixture.colorClose(plain);
    check(scales(plain)[0]===productBits(1.5,1)&&scales(plain)[1]===productBits(1.5,1),'unowned colour changed');
    const report={expected,entry_after:bytes(fixture.entry,16),gate:String(hook.gate),continuation:String(hook.continuation),
        close_exit:String(fixture.closeExit),spans,nested_two:nestedTwo,status:listener.status()};
    hook.listener.detach();Interceptor.flush();
    return report;
}
function fingerprintNegative(){
    const listener=createNativeParser(new Map(),error=>{throw error;}),fixture=makeFixture(),before=bytes(fixture.entry,16),common=bytes(fixture.common,16);
    let rejected=false;try{listener.installSizeHook(fixture.entry,'00'+before.slice(2));}catch(error){rejected=String(error).includes('Unvalidated native size branch');}
    check(rejected,'invalid size signature was accepted');
    check(bytes(fixture.entry,16)===before&&bytes(fixture.common,16)===common,'invalid size signature changed fixture memory');
    return {entry_before:before,entry_after:bytes(fixture.entry,16),common_before:common,common_after:bytes(fixture.common,16)};
}
rpc.exports={run(){return {all_passed:true,game_attached:false,host:'self-created-hidden-python',
    red:directAttachRed(),green:gatewayGreen(),negative:fingerprintNegative()};}};
"""
    )


def main():
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        agent = session.create_script(script_source(), runtime="v8")
        agent.load()
        report = agent.exports_sync.run()
        assert report["all_passed"]
        destination = ROOT / "generated/diagnostic-100-native-size-hook.json"
        destination.write_text(json.dumps(report, indent=2), "utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        # The host belongs exclusively to this test. Stop it before detaching:
        # Frida may otherwise wait for a listener whose target is a tail jump.
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


if __name__ == "__main__":
    main()
