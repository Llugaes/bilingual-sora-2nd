import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from sora_bilingual.localization.model_wire import pack_model, prepare_wire, wire_ready


class WireTests(unittest.TestCase):
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
            target.write_bytes(original.replace(b"same", b"oops"))
            prepare_wire(source, model)
            self.assertEqual(target.read_bytes(), original)
            target.write_text("{", encoding="utf-8")
            self.assertFalse(wire_ready(source))
            prepare_wire(source, model)
            self.assertTrue(wire_ready(source))
            source.write_text('{"changed":true}', encoding="utf-8")
            self.assertFalse(wire_ready(source))
