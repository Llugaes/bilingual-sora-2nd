"""Exhaustively compare every decoded value in a local compiled model, offline."""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.model_wire import prepare_wire


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    wire = prepare_wire(args.model)
    code = r"""
const fs=require('fs'),vm=require('vm'),crypto=require('crypto');
const [source,path]=process.argv.slice(1),expected=JSON.parse(fs.readFileSync(source,'utf8'));
const bytes=fs.readFileSync(path),context={rpc:{exports:{}},File:{readAllBytes:()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)}};
vm.createContext(context);vm.runInContext(fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8'),context);
context.rpc.exports.load=model=>{context.model=model;return true;};
context.rpc.exports.modelpackedfile(path);
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const fields=[];
// One root field at a time bounds transient serialization memory; every nested
// property, array member, number and string still participates in the digest.
for(const key of Object.keys(expected)) {
    const before=digest(expected[key]),after=digest(context.model[key]);
    if(before!==after)throw Error('Model field changed: '+key);
    fields.push({field:key,sha256:before});
}
const paragraphs=Object.create(null);
for(const source of Object.keys(expected.pairs)) {
    const parts=source.split(/\r\n|\n|\\n/);
    if(parts.length>1)(paragraphs[parts[0]]??=[]).push(source);
}
if(digest(paragraphs)!==digest(context.model.paragraph_sources))throw Error('Paragraph candidate coverage');
console.log(JSON.stringify({fields,pairs:Object.keys(expected.pairs).length,paragraph_buckets:Object.keys(paragraphs).length,passed:true}));
"""
    subprocess.run(
        [
            "node",
            "--max-old-space-size=4096",
            "-e",
            code,
            str(args.model.resolve()),
            str(wire.resolve()),
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
