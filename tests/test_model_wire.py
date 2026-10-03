import json
import base64
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from sora_bilingual.localization.model_wire import (
    indexed_model,
    pack_model,
    prepare_wire,
    wire_ready,
)


class WireTests(unittest.TestCase):
    def test_legacy_and_indexed_cache_stamps_do_not_invalidate_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "model.json"
            source.write_text("{}", encoding="utf-8")
            model = {"pairs": {"a": ["a", "訳"]}}
            indexed = prepare_wire(source, model)
            legacy = prepare_wire(source, model, schema=1)
            self.assertNotEqual(indexed, legacy)
            self.assertTrue(wire_ready(source))
            with patch(
                "sora_bilingual.localization.model_wire.pack_model",
                side_effect=AssertionError("rebuilt"),
            ):
                self.assertEqual(prepare_wire(source, model), indexed)
                self.assertEqual(prepare_wire(source, model, schema=1), legacy)

    def decode_indexed(self, content, action="JSON.stringify(model)"):
        root = Path(__file__).resolve().parents[1]
        code = """const fs=require('fs'),vm=require('vm'),bytes=Buffer.from(fs.readFileSync(0,'utf8'),'base64');
const context={rpc:{exports:{}},File:{readAllBytes:()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)}};
vm.createContext(context);vm.runInContext(fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8'),context);
context.rpc.exports.load=m=>{context.model=m;return true;};
context.rpc.exports.modelpackedfile('fixture.wire.bin');
process.stdout.write(vm.runInContext(ACTION,context));""".replace("ACTION", json.dumps(action))
        return subprocess.run(
            ["node", "-e", code],
            input=base64.b64encode(content).decode(),
            text=True,
            capture_output=True,
            cwd=root,
        )

    def test_indexed_model_preserves_all_values_after_working_set_eviction(self):
        pairs = {f"文本{index}𠮷\x00": [f"source{index}", f"訳{index}"] for index in range(6200)}
        pairs.update(
            {
                "首行\r\n次行": ["首行\r\n次行", "first\\nnext"],
                "first\\nnext": ["first\\nnext", "首行\n次行"],
            }
        )
        model = {
            "pairs": pairs,
            "plain_pairs": pairs,
            "array": [None, True, 1, False, 0, 0.85, "", "\ud800"] * 100,
            "keys": {
                **{str(i): i for i in reversed(range(20))},
                "__proto__": [True],
                "constructor": "data",
                "hasOwnProperty": "own",
                "toString": "text",
                "costarring": "collision-one",
                "liquid": "collision-two",
            },
        }
        result = self.decode_indexed(indexed_model(model))
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = json.loads(result.stdout)
        self.assertEqual(
            decoded.pop("paragraph_sources"), {"首行": ["首行\r\n次行"], "first": ["first\\nnext"]}
        )
        self.assertEqual(decoded, model)
        result = self.decode_indexed(
            indexed_model(model),
            """JSON.stringify([
            Object.hasOwn(model.keys,'__proto__'),Object.hasOwn(model.keys,'missing'),
            Array.isArray(model.array),model.array.slice(0,8),Object.keys(model.keys).slice(0,20),
            model.keys.costarring,model.keys.liquid,
            Object.keys(model.pairs).length,model.pairs['文本0𠮷\\u0000']])""",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                True,
                False,
                True,
                model["array"][:8],
                list(map(str, range(20))),
                "collision-one",
                "collision-two",
                len(pairs),
                pairs["文本0𠮷\x00"],
            ],
        )

    def test_indexed_model_rejects_bad_header_bounds_and_references(self):
        import struct

        content = indexed_model({"pairs": {"source": ["source", "訳"]}})
        for offset, value in [(8, 99), (16, 4000000), (24, 0), (28, 0), (32, 99)]:
            broken = bytearray(content)
            struct.pack_into("<I", broken, offset, value)
            result = self.decode_indexed(broken)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid indexed model", result.stderr)
        result = self.decode_indexed(content[:-1])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid indexed model", result.stderr)
        count = struct.unpack_from("<I", content, 12)[0]
        data = struct.unpack_from("<I", content, 24)[0]
        corruptions = []
        for node in range(count):
            kind, length, offset, _ = struct.unpack_from("<4I", content, 32 + node * 16)
            start = data + offset
            if kind == 4 and length:
                corruptions.append((start, node))  # A reference to itself, not a child.
            if kind == 5 and length:
                corruptions.append((start, node))  # Invalid key reference.
                corruptions.append((start + length * 8, 0))  # Wrong indexed key hash.
                corruptions.append((start + length * 8 + 4, length))  # Out-of-range entry.
        for offset, value in corruptions:
            broken = bytearray(content)
            struct.pack_into("<I", broken, offset, value)
            result = self.decode_indexed(broken)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid indexed model", result.stderr)

    def test_python_packer_roundtrips_through_production_javascript_decoder(self):
        model = {
            "pairs": {"a": ["hello", "日本語"], "b": ["hello", "日本語"]},
            "__proto__": {"constructor": [True, 1, False, 0, None, 0.85]},
            "empty": [],
        }
        packed = pack_model(model)
        self.assertEqual(packed["nodes"].count("日本語"), 1)
        root = Path(__file__).resolve().parents[1]
        code = """const fs=require('fs'),vm=require('vm'),data=JSON.parse(fs.readFileSync(0,'utf8'));
const rpc={exports:{load:m=>process.stdout.write(JSON.stringify(m))}};
vm.runInNewContext(fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8'),{rpc,File:{readAllText:()=>JSON.stringify(data)}});
rpc.exports.modelpackedfile('unused');"""
        result = subprocess.run(
            ["node", "-e", code],
            input=json.dumps(packed),
            text=True,
            capture_output=True,
            cwd=root,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), model)

    def test_cache_reused_and_invalidated_by_source_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "model.json"
            source.write_text("{}", encoding="utf-8")
            model = {"x": ["same", "same"]}
            self.assertFalse(wire_ready(source))
            target = prepare_wire(source, model)
            self.assertTrue(wire_ready(source))
            with patch(
                "sora_bilingual.localization.model_wire.pack_model",
                side_effect=AssertionError("rebuilt"),
            ):
                self.assertEqual(prepare_wire(source, model), target)
            original = target.read_bytes()
            target.write_bytes(
                original.replace("same".encode("utf-16-le"), "oops".encode("utf-16-le"))
            )
            prepare_wire(source, model)
            self.assertEqual(target.read_bytes(), original)
            target.write_text("{", encoding="utf-8")
            self.assertFalse(wire_ready(source))
            prepare_wire(source, model)
            self.assertTrue(wire_ready(source))
            source.write_text('{"changed":true}', encoding="utf-8")
            self.assertFalse(wire_ready(source))
