import json
import base64
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import zlib
from unittest.mock import patch
from sora_bilingual.localization.model_wire import (
    indexed_model,
    pack_model,
    prepare_wire,
    publish_indexed,
    wire_ready,
)


# Frozen from model_wire.py at 70e00b4cdb74ad8295d4215641b3d2c85c6125fd,
# before splitting the indexed encoder. zlib only keeps the literal fixture small.
_EMPTY_WIRE = {
    1: "eJyrVipOzkjNTVSyMtRRKsrPL1GyMtJRystPSS1WsopWKkjMLCpW0ok2jNWJNtQx0DGMja0FAJ3sD3o=",
    2: "eJwL9g9y9PV3MWJiYGBgYWBgYGZgYFBgYGBIYGBg2ADlszJAABcSmwdKg+QFoXwlqDzILAOoOQUMiQyZDEUMxVB2EUMiQzqYLGDIYIhnKGbIZyhlKGJIZkgFqwEBRqgZIDrt/qxEkNgU1U17QHwAzCIR4Q==",
}
_COMPLETE_WIRE = {
    1: (
        "eJx1ULFu2zAU/Jc3XwLykbIl/0QCZJQEgZCZWqhCKiQFxwg6d8mcqUO9FB2CLh36R4az5RMKOmmADlkeDu8d7t3dPcV+Y28MrSQo"
        "eJ9opQuQ82sbaVXTZIYQCfT84/G4f2hC4w5P++P+gUDXQ4ipaZyzd4lQC0hw+85859UCDN2CDo9fD9+eXr7/+tPMQghBoOjn0FsC"
        "HX/+PjGXKFvUEhIKjAILVC1oGs3gun9WTAhmR3DzOCKF2ULi2ozRQuBMnAuI87IAvTpSkBqygFxALiFLyAr84b4Ffba7/EMRFIgJ"
        "DJIEyma7bgo++a57lc6Reu9iCnOffCDQ2iRDoI2JF1t3GfxkQ9oRyG8dgZK/SmFwnzI8NUa9j8mEt13vx3GIg3dn3uVGxuF2Htb/"
        "HdLWUy6HFViDC/ACvMwxuMwxuIISUBKKoRSUhiqgFlBLqBKqgs4J7c2UXdUZx40Jdn0SFZACUp4mgyWYoSU0Qytojaptv/wFTBan"
        "Uw=="
    ),
    2: (
        "eJyNlEloVEEQhr83kzGjjvsW933fTdQIihrmIBIZUQ8e1DAkYzIkzjzfTNDgQT2IIScPIhoQPQiKC4IIelDxEEEhgmiEHARFPCiCiCcFD1Ld1b6XwYMNb6n+q/7urvq79mb2bN+VSa+LAeuBOmAO4MehphriQAI7RmDtYUBKH7FHAjXAZKAKEK41QJIwvl7jHZ6uwBsr+PdH+D2gReNcfJvGJ9TH1zXdfq7qfhz/Q+V3o0+/nj7OjkXwpGIy+ivwfsWdPVBhv4ucT8Yn/brzfIqcZzzwGdihuMyt8cJ48a/3rL/j31yBpyvwHRX4bsWdvS9iD5d8e3YfVYp3ePbf5dP3wnzKfHeEfzRwzoMZastz27N1lH/xu+/B2Eh8XyRe6tLvwUS1RwEfPJgW0cNvL9SD4MmYxRMavyBma+7q3RcL9SbjlSbG8Ynt+MZJvWIwT23jGrexLh9Vajv+ZDzkF3yi4gmNr4nbeyR2tdQvbjXqkyVPQAm4cKmxexQjmNve2H1YZ8scoECBHMcpK3dMfa1nqJuzuRWtDYMP3st2SxTpJKCZHLU9dk2nX3emhJ5d6t3wpSQl58Rr/4JgXV8yb4THp8PssEDTkL1mCQjI0vX3Bn3fytBxqtaMr1sZtDUSXYzB1l1yLPqaILkCJvF/Pu3k6KJE7d9lktvWhWtuW6v3vsnsN6BImaKxLHczRQomrwGdNBs0MP0kS5ksbWQpkeEYBXabeJ8cAWW6KJpZTMxewyB5aaWs1RFuYba5sZjMddBBnhJ5s/ZK887JnSLPUTrJ0/JPvzLHKGovnYrV93TsvZIczdQczQJma5+ei9XtfLkDwEJgEbAYWAIsBZ5tejpZ9DDjeqpOan33Rmq9aKLhZmqDJPHtrdRG0cLzFxc3iz4u39x1SLQjX9HK4/ajZ0RvmSsHf4iGchzBNxkS3UkGA3K0GL2IRlrN26eNpiG6dJqXtUK9W22u1jpKPaW+2wdPSwvjZO9B1zrNfZNeJF+5u9KPpgDLgOXACmCl6nsVGM18e3K9RvZ++H1vVjgW3dnfI+sNpH9ek7OcX3jvkZx5S/rjW1nvZXLnL+nZfwDoZrAT"
    ),
}


def wire_fixture(schema):
    pairs = {
        "首行\r\n次行": ["首行\r\n次行", "first\\nnext"],
        "first\\nnext": ["first\\nnext", "首行\n次行"],
        "文本𠮷\x00": ["source", "訳"],
    }
    values = [None, True, 1, False, 0, -0.0, 0.85, ""]
    if schema == 2:
        values.append("\ud800")
    return {
        "pairs": pairs,
        "plain_pairs": pairs,
        "array": values * 2,
        "keys": {
            **{str(i): i for i in reversed(range(4))},
            "__proto__": [True],
            "constructor": "data",
            "hasOwnProperty": "own",
            "toString": "text",
            "costarring": "collision-one",
            "liquid": "collision-two",
        },
        "empty": [],
        "shared": ("source", "訳"),
    }


class WireTests(unittest.TestCase):
    def test_completed_packers_do_not_retain_inputs_until_cyclic_gc(self):
        import gc
        import weakref

        class Text(str):
            pass

        enabled = gc.isenabled()
        gc.disable()
        try:
            for packer in (pack_model, indexed_model):
                with self.subTest(packer=packer.__name__):
                    source = Text("Unique owned source")
                    reference = weakref.ref(source)
                    model = {"pairs": {source: ["primary", "secondary"]}}
                    packed = packer(model)
                    del packed, model, source
                    self.assertIsNone(reference(), "completed packer retained its input graph")
        finally:
            if enabled:
                gc.enable()

    def test_wire_bytes_match_frozen_baseline_for_both_schemas(self):
        for schema in (1, 2):
            for model, frozen in (
                ({"pairs": {}}, _EMPTY_WIRE),
                (wire_fixture(schema), _COMPLETE_WIRE),
            ):
                with (
                    self.subTest(schema=schema, empty=model == {"pairs": {}}),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    expected = zlib.decompress(base64.b64decode(frozen[schema]))
                    source = Path(tmp) / "model.json"
                    source.write_text("{}", "utf-8")
                    target = prepare_wire(source, model, schema=schema)
                    self.assertEqual(target.read_bytes(), expected)
                    if schema == 2:
                        self.assertEqual(indexed_model(model), expected)
                    else:
                        self.assertEqual(pack_model(model), json.loads(expected))

    def test_production_indexed_publication_avoids_compatibility_byte_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "model.wire.bin"
            with patch(
                "sora_bilingual.localization.model_wire.indexed_model",
                side_effect=AssertionError("materialized compatibility bytes"),
            ):
                publish_indexed(target, {"pairs": {}})
            self.assertEqual(target.read_bytes(), zlib.decompress(base64.b64decode(_EMPTY_WIRE[2])))

    def test_published_wire_digest_streams_the_actual_file(self):
        for schema in (1, 2):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "model.json"
                source.write_text("{}", "utf-8")
                with (
                    patch.object(Path, "read_bytes", side_effect=AssertionError("whole-file copy")),
                    patch(
                        "sora_bilingual.localization.model_wire.hashlib.file_digest",
                        wraps=hashlib.file_digest,
                    ) as digest,
                ):
                    target = prepare_wire(source, {"pairs": {}}, schema=schema)
                self.assertEqual(
                    [Path(call.args[0].name) for call in digest.call_args_list],
                    [source, target, source],
                )
                self.assertTrue(all(call.args[1] == "sha256" for call in digest.call_args_list))
                stamp = (
                    target.with_name(target.name + ".stamp.json")
                    if schema == 2
                    else target.with_suffix(".stamp.json")
                )
                self.assertEqual(
                    json.loads(stamp.read_text("utf-8"))["sha256"],
                    hashlib.sha256(target.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    json.loads(stamp.read_text("utf-8"))["source_sha256"],
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                )

    def test_post_publication_payload_denial_never_writes_a_stamp(self):
        for schema in (1, 2):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "model.json"
                source.write_text("{}", "utf-8")
                original = Path.open

                def denied_payload(path, mode="r", *args, **kwargs):
                    if path.name.endswith((".wire.bin", ".wire.json")) and mode == "rb":
                        raise PermissionError("published payload denied")
                    return original(path, mode, *args, **kwargs)

                with patch.object(Path, "open", denied_payload):
                    with self.assertRaisesRegex(PermissionError, "published payload denied"):
                        prepare_wire(source, {"pairs": {}}, schema=schema)
                self.assertEqual(list(Path(tmp).glob("*.stamp.json")), [])
                self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
                self.assertEqual(len(list(Path(tmp).glob("*.wire.*"))), 1)

    def test_failed_indexed_writes_preserve_previous_payload_and_stamp(self):
        from sora_bilingual.localization import model_wire

        for stage in (1, 2, 3, "replace"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "model.json"
                source.write_text("{}", "utf-8")
                target = prepare_wire(source, {"pairs": {}})
                stamp = target.with_name(target.name + ".stamp.json")
                previous, previous_stamp = target.read_bytes(), stamp.read_bytes()
                source.write_text('{"changed":true}', "utf-8")
                original = model_wire.tempfile.NamedTemporaryFile

                class FailingWriter:
                    def __init__(self, *args, **kwargs):
                        self.stream = original(*args, **kwargs)
                        self.writes = 0

                    def __enter__(self):
                        self.stream.__enter__()
                        return self

                    def __exit__(self, *args):
                        return self.stream.__exit__(*args)

                    def __getattr__(self, name):
                        return getattr(self.stream, name)

                    def write(self, content):
                        self.writes += 1
                        if self.writes == stage:
                            self.stream.write(content[:1])
                            raise OSError("interrupted indexed write")
                        return self.stream.write(content)

                with (
                    patch.object(model_wire.tempfile, "NamedTemporaryFile", FailingWriter),
                    patch.object(model_wire, "replace_file", side_effect=OSError("replace denied"))
                    if stage == "replace"
                    else patch.object(model_wire, "replace_file", wraps=model_wire.replace_file),
                ):
                    with self.assertRaisesRegex(
                        OSError,
                        "replace denied" if stage == "replace" else "interrupted indexed write",
                    ):
                        prepare_wire(source, {"pairs": {"new": ["new", "訳"]}})
                self.assertEqual(target.read_bytes(), previous)
                self.assertEqual(stamp.read_bytes(), previous_stamp)
                self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_wire_ready_permission_is_not_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "model.json"
            source.write_text("{}", encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=PermissionError("stamp denied")):
                with self.assertRaisesRegex(PermissionError, "stamp denied"):
                    wire_ready(source)

    def test_wire_preparation_permission_errors_never_rebuild(self):
        for schema in (1, 2):
            for stage in ("stamp", "payload"):
                with self.subTest(schema=schema, stage=stage), tempfile.TemporaryDirectory() as tmp:
                    source = Path(tmp) / "model.json"
                    source.write_text("{}", encoding="utf-8")
                    model = {"pairs": {"source": ["日本語", "中文"]}}
                    target = prepare_wire(source, model, schema=schema)
                    original_open = Path.open

                    def denied_open(path, *args, **kwargs):
                        if (
                            stage == "payload"
                            and path == target
                            or stage == "stamp"
                            and path.name.endswith(".stamp.json")
                        ):
                            raise PermissionError("owned fixture denied")
                        return original_open(path, *args, **kwargs)

                    with (
                        patch.object(Path, "open", new=denied_open),
                        patch("sora_bilingual.localization.model_wire.publish_indexed") as indexed,
                        patch("sora_bilingual.localization.model_wire.publish_json") as legacy,
                    ):
                        with self.assertRaisesRegex(PermissionError, "owned fixture denied"):
                            prepare_wire(source, model, schema=schema)
                        indexed.assert_not_called()
                        legacy.assert_not_called()

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
