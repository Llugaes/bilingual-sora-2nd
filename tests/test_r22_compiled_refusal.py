"""Independent compiler veto must survive compound partitioning and final render."""

import json
from pathlib import Path
import subprocess
import unittest

from sora_bilingual.localization.menu_text import MenuTranslator


class CompiledEffectRefusalTests(unittest.TestCase):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/r22-compiled-conflict-source.json").read_text("utf8")
    )

    def translator(self):
        return MenuTranslator(self.fixture["entries"], "ja", "zh-Hans", "en")

    def test_real_compiler_veto_is_preserved_by_python_final_modes(self):
        model = self.translator().runtime_model()
        self.assertIn(
            self.fixture["blocked_pattern"], model["details"]["detail_effect_blocked_numeric"]
        )
        for order in [
            ("annotation", "primary", "secondary"),
            ("primary", "secondary", "annotation"),
        ]:
            tr = self.translator()
            for mode in order:
                with self.subTest(order=order, mode=mode):
                    plan = tr.render(self.fixture["source"], mode)
                    self.assertEqual(plan["text"], self.fixture["source"])
                    self.assertFalse(plan["layers"])
                    self.assertEqual(
                        tr.translate(self.fixture["source"], mode), self.fixture["source"]
                    )

    def test_real_compiler_veto_is_preserved_by_production_js_final_modes(self):
        script = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const d=JSON.parse(fs.readFileSync(0,'utf8')),rows=[];
for(const order of [['annotation','primary','secondary'],['primary','secondary','annotation']]){
 const t=new RuntimeText(d.model);
 for(const mode of order){const plan=t.render(d.source,mode);rows.push({mode,plan,translated:t.translate(d.source,mode)});}
}
process.stdout.write(JSON.stringify(rows));
"""
        replay = subprocess.run(
            ["node", "-e", script],
            input=json.dumps(
                {"model": self.translator().runtime_model(), "source": self.fixture["source"]}
            ),
            text=True,
            encoding="utf8",
            capture_output=True,
            check=True,
        )
        for row in json.loads(replay.stdout):
            with self.subTest(mode=row["mode"]):
                self.assertEqual(row["plan"]["text"], self.fixture["source"])
                self.assertFalse(row["plan"]["layers"])
                self.assertEqual(row["translated"], self.fixture["source"])


if __name__ == "__main__":
    unittest.main()
