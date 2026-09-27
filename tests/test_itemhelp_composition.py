import json
from pathlib import Path
import subprocess
import unittest

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator, item_help_components

ROOT = Path(__file__).resolve().parents[1]


RANGE = "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:6a15f570d7d4b310463cc8eb627186cd7e4586d9ab2b87e663ebb1e538c2d090/label"
TARGET_RANGE = "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:2a2c762e0d6517c7db916fe291eb0c21a61dbb9804f6b0c338a115132e4962f9/label"
SELF_RANGE = "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:d3740e2d93482a970bdc5c805bb0e4ef863b2ca6ce6809551f3f17f1784c3783/label"
SINGLE_RANGE = "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:509cf18dbbd7f215a26834b18931cc516ddfdee2f17fa10fe1b40bf86a7cbed0/label"
RECOVERY = "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:cc311d9666993ad7471edb97a4292bd44de5cac259718aab39db45a6008a99a8/name"
DELAY = "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:93e17b497b0a5e2d8a6b21a7b66f0a4f5ccf0c6c214838a10ff8a55793b9898f/name"
DELAY_STAT = "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:46b4d17f931b2f1242e099ad5d07d954cfec23302060c5f3987becdd04474060/stat"
SKILL_DESCRIPTION = "table/t_skill.tbl/sha256:0cf6066def2b68bd8cb6a442eb6bdd445eb205b2e227be5c113186ce78812d2e/description"
ITEM_KIND_HELP = "table/t_itemhelp.tbl/ItemKindHelpData/sha256:5c004f435ac981d5e424d2d99d3d1567b9ef3d4bd95c8557e73dd37e9d364e10/description"
ITEM_KIND_MENU = "table/t_item.tbl/ItemKindParam2/sha256:5e9a5de4a59a7c3c9ba8846060ba77ab402e3088658aa705e1a64e796f6cd5cf/title"
ITEM_DESCRIPTION = "table/t_item.tbl/sha256:a22b50869a7d9f364a54d2e6ea31dba8ae856bf0ee73ac8a3ee9d1b0859adcfc/description"
STATUS_BASE = "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:f1fc46431c86d89b0a3ab89432142800d8796f82fd34f9ff58383ccbe440d139"
ARTS_ATTACK = "table/t_itemhelp.tbl/SkillTextArrayData/sha256:4db4027ea9ac75ab06eba4312285c6b4563d3330acdf0502223a3ee15bbcefc4/format"
FREEZE = "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:cd18d56d67c3b3cb664a1a37fd775a3f90ea5c2b4ae15bbe9db805d20ddf23e1/name"


RANGE_S = {
    "ja": "Ｓ",
    "en": "(S)",
    "zh-Hans": "S",
    "zh-Hant": "S",
    "ko": "S",
    "fr": "(S)",
    "de": "(K)",
    "es": "(S)",
}
RANGE_L = {
    "ja": "Ｌ",
    "en": "(L)",
    "zh-Hans": "L",
    "zh-Hant": "L",
    "ko": "L",
    "fr": "(L)",
    "de": "(G)",
    "es": "(L)",
}
RANGE_M = {
    "ja": "Ｍ",
    "en": "(M)",
    "zh-Hans": "M",
    "zh-Hant": "M",
    "ko": "M",
    "fr": "(M)",
    "de": "(M)",
    "es": "(M)",
}
RANGE_LL = {
    "ja": "ＬＬ",
    "en": "(LL)",
    "zh-Hans": "LL",
    "zh-Hant": "LL",
    "ko": "LL",
    "fr": "(XL)",
    "de": "(SG)",
    "es": "(XL)",
}
MIDDLE = {
    "ja": "中",
    "en": "(M)",
    "zh-Hans": "中",
    "zh-Hant": "中",
    "ko": "중",
    "fr": "(M)",
    "de": "(M)",
    "es": "(M)",
}
TARGET_RANGE_TEXT = {
    "ja": "地点･円",
    "en": "Target - Circle ",
    "zh-Hans": "地点·圆",
    "zh-Hant": "地點・圓",
    "ko": "지점・원",
    "fr": "Cible - Cercle ",
    "de": "Ziel – Kreis ",
    "es": "Objetivo, círculo ",
}
SELF_RANGE_TEXT = {
    "ja": "自分･円",
    "en": "Self - Circle ",
    "zh-Hans": "自身·圆",
    "zh-Hant": "自身・圓",
    "ko": "자신・원",
    "fr": "Soi-même - Cercle ",
    "de": "Selbst – Kreis ",
    "es": "Uno mismo, círculo ",
}
DELAY_TEXT = {
    "ja": "遅延%s",
    "en": "Delay %s",
    "zh-Hans": "延迟%s",
    "zh-Hant": "延遲%s",
    "ko": "지연 %s",
    "fr": "Retard %s",
    "de": "Verzögerung %s",
    "es": "Retraso %s",
}
DELAY_STAT_TEXT = {
    "ja": "遅延",
    "en": "Delay",
    "zh-Hans": "延迟",
    "zh-Hant": "延遲",
    "ko": "지연",
    "fr": "Retard",
    "de": "Verzögerung",
    "es": "Retraso",
}
SKILL_DESCRIPTION_TEXT = {
    "ja": "<C9>凍える風をまとった苛烈な連続攻撃。",
    "en": "<C9>Manipulate freezing winds for a fierce combo attack.",
    "zh-Hans": "<C9>缠绕着凛冽寒风的猛烈连续攻击。",
    "zh-Hant": "<C9>纏繞著凜冽寒風的猛烈連續攻擊。",
    "ko": "<C9>시린 바람을 두른 거센 연속 공격.",
    "fr": "<C9>Mobilise des vents polaires pour déchaîner un combo redoutable.",
    "de": "<C9>Manipuliere eiskalte Winde in einen verheerenden Komboangriff.",
    "es": "<C9>Emplea vientos gélidos en un ataque combinado sin piedad.",
}
ITEM_KIND_HELP_TEXT = {
    "ja": "強化",
    "en": "Enhance ",
    "zh-Hans": "强化",
    "zh-Hant": "強化",
    "ko": "강화",
    "fr": "Amélioration ",
    "de": "Verbessern ",
    "es": "Mejora ",
}
ITEM_KIND_MENU_TEXT = {
    "ja": "強化",
    "en": "Enhance",
    "zh-Hans": "强化",
    "zh-Hant": "強化",
    "ko": "강화",
    "fr": "Amélioration",
    "de": "Verbessern",
    "es": "Mejoras",
}
SINGLE_RANGE_TEXT = {
    "ja": "単体",
    "en": "Single",
    "zh-Hans": "单体",
    "zh-Hant": "單體",
    "ko": "개별",
    "fr": "Simple",
    "de": "Einzel",
    "es": "Objetivo único",
}
STATUS_TEXT = {
    "ja": "能力値アップ",
    "en": "STATUS UP",
    "zh-Hans": "能力值提升",
    "zh-Hant": "能力值提升",
    "ko": "능력치 상승",
    "fr": "STAT AMÉLIORÉ",
    "de": "STATUS ERHÖHT",
    "es": "AUMENTO DE ESTADÍSTICAS",
}
HP_FORMAT_TEXT = {
    "ja": "最大HP+%d",
    "en": "MAX HP+%d",
    "zh-Hans": "HP上限+%d",
    "zh-Hant": "HP上限+%d",
    "ko": "최대 HP +%d",
    "fr": "PV MAX +%d",
    "de": "MAX LP +%d",
    "es": "PV MÁX +%d",
}
ARTS_ATTACK_TEXT = {
    "ja": "魔法攻撃",
    "en": "Arts Attack",
    "zh-Hans": "魔法攻击",
    "zh-Hant": "魔法攻擊",
    "ko": "마법 공격",
    "fr": "Attaque d'art",
    "de": "Künste-Angriff",
    "es": "Ataque con artes",
}
FREEZE_TEXT = {
    "ja": "凍結%d％",
    "en": "Freeze %d%%",
    "zh-Hans": "冻结%d％",
    "zh-Hant": "凍結%d％",
    "ko": "동결 %d％",
    "fr": "Gel %d %%",
    "de": "Einfrieren %d%%",
    "es": "Congelación %d%%",
}
RECOVERY_TEXT = {
    "ja": "HP%s回復",
    "en": "Heal %s HP",
    "zh-Hans": "回复HP%s",
    "zh-Hant": "回復HP%s",
    "ko": "HP %s 회복",
    "fr": "Restaure %s PV",
    "de": "Heilt %s LP",
    "es": "Curación de %s PV",
}
RECOVERY_STAT = {
    "ja": "HP",
    "en": "HP",
    "zh-Hans": "HP",
    "zh-Hant": "HP",
    "ko": "HP",
    "fr": "PV",
    "de": "LP",
    "es": "PV",
}
MAGNITUDES = {
    "MOSTSMALL": {
        "ja": "極小",
        "en": "(XS)",
        "zh-Hans": "极小",
        "zh-Hant": "極小",
        "ko": "극소",
        "fr": "(XS)",
        "de": "(XS)",
        "es": "(XS)",
    },
    "SMALL": {
        "ja": "小",
        "en": "(S)",
        "zh-Hans": "小",
        "zh-Hant": "小",
        "ko": "소",
        "fr": "(S)",
        "de": "(K)",
        "es": "(S)",
    },
    "MIDDLE": MIDDLE,
    "LARGE": {
        "ja": "大",
        "en": "(L)",
        "zh-Hans": "大",
        "zh-Hant": "大",
        "ko": "대",
        "fr": "(L)",
        "de": "(G)",
        "es": "(L)",
    },
    "MOSTLARGE": {
        "ja": "極",
        "en": "(LL)",
        "zh-Hans": "极",
        "zh-Hant": "極",
        "ko": "극대",
        "fr": "(XL)",
        "de": "(SG)",
        "es": "(XL)",
    },
}
ITEM_DESCRIPTION_TEXT = {
    "ja": "使用者の潜在能力を高める、「命」を司る秘薬。",
    "en": "A secret medicine that enhances Life.",
    "zh-Hans": "可提升使用者的潜能，司掌“生命”的秘药。",
    "zh-Hant": "可提升使用者的潛能，司掌「生命」的祕藥。",
    "ko": "사용자의 잠재 능력을 올리는 「생명」을 관장하는 비약.",
    "fr": "Un remède secret qui renforce la vie.",
    "de": "Eine geheime Medizin, die das Leben verbessert.",
    "es": "Medicina secreta que potencia la vida.",
}


def row(key, zh=None, en=None, ja=None, texts=None):
    return {"key": key, "texts": texts or {"zh-Hans": zh, "en": en, "ja": ja}}


def entries():
    return [
        row(RANGE, "我方·圆", "Ally - Circle ", "味方･円"),
        row("table/t_text.tbl/TXT_ITEM_HELP_RANGE_L", "L", "(L)", "Ｌ"),
        row(RECOVERY, "回复HP%s", "Heal %s HP", "HP%s回復"),
        row(RECOVERY.removesuffix("/name") + "/stat", "HP", "HP", "HP"),
        row("table/t_text.tbl/TXT_ITEM_HELP_SMALL", "小", "(S)", "小"),
        row(
            "table/t_itemhelp.tbl/SkillEffectHelpData/other/name", "回复%s", "Restore %s", "%s回復"
        ),
        row("table/t_skill.tbl/skill/description", "<C9>说明。", "<C9>Description.", "<C9>説明。"),
    ]


def full_entries():
    return [
        row(TARGET_RANGE, texts=TARGET_RANGE_TEXT),
        row(SELF_RANGE, texts=SELF_RANGE_TEXT),
        row(SINGLE_RANGE, texts=SINGLE_RANGE_TEXT),
        row("table/t_text.tbl/TXT_ITEM_HELP_RANGE_S", texts=RANGE_S),
        row("table/t_text.tbl/TXT_ITEM_HELP_RANGE_L", texts=RANGE_L),
        row("table/t_text.tbl/TXT_ITEM_HELP_MIDDLE", texts=MIDDLE),
        row(DELAY, texts=DELAY_TEXT),
        row(DELAY_STAT, texts=DELAY_STAT_TEXT),
        row(SKILL_DESCRIPTION, texts=SKILL_DESCRIPTION_TEXT),
        row(ITEM_KIND_HELP, texts=ITEM_KIND_HELP_TEXT),
        row(ITEM_KIND_MENU, texts=ITEM_KIND_MENU_TEXT),
        row(
            "table/t_skill.tbl/sha256:aabe562e332f5c1d8f766c0f7751af405beca56330da5a683c208ee680644dfd/name",
            texts={
                "ja": "<C9>単体",
                "en": "<C9>Single",
                "zh-Hans": "<C9>单体",
                "zh-Hant": "<C9>單體",
                "ko": "<C9>개별",
                "fr": "<C9>Simple",
                "de": "<C9>Einzel",
                "es": "<C9>Solo",
            },
        ),
        row(STATUS_BASE + "/stat", texts=STATUS_TEXT),
        row(STATUS_BASE + "/format", texts=HP_FORMAT_TEXT),
        row(ARTS_ATTACK, texts=ARTS_ATTACK_TEXT),
        row(FREEZE, texts=FREEZE_TEXT),
        row(ITEM_DESCRIPTION, texts=ITEM_DESCRIPTION_TEXT),
    ]


class ItemHelpCompositionTests(unittest.TestCase):
    def test_adjacent_range_and_formatted_effect_use_each_target_locale(self):
        tr = MenuTranslator(entries(), "en", "ja", "zh-Hans")
        source = "<I299><C3>我方·圆L</C><c698>回复HP小</C>\n<C0><C9>说明。"
        self.assertEqual(
            tr.translate(source, "primary"),
            "<I299><C3>Ally - Circle (L)</C><c698>Heal (S) HP</C>\n<C0><C9>Description.",
        )
        self.assertEqual(
            tr.translate(source, "secondary"),
            "<I299><C3>味方･円Ｌ</C><c698>HP小回復</C>\n<C0><C9>説明。",
        )

    def test_real_coloured_delay_detail_translates_all_source_and_target_languages(self):
        for source_language in LANGUAGES:
            source = f"<I295><C3>{TARGET_RANGE_TEXT[source_language]}{RANGE_S[source_language]}</C><c698>{DELAY_TEXT[source_language].removesuffix('%s')}<c698>{MIDDLE[source_language]}</C></C>\n<C0>{SKILL_DESCRIPTION_TEXT[source_language]}"
            for primary in LANGUAGES:
                for secondary in LANGUAGES:
                    with self.subTest(source=source_language, primary=primary, secondary=secondary):
                        tr = MenuTranslator(full_entries(), primary, secondary, source_language)
                        for mode, target in (("primary", primary), ("secondary", secondary)):
                            expected = f"<I295><C3>{TARGET_RANGE_TEXT[target]}{RANGE_S[target]}</C><c698>{DELAY_TEXT[target].removesuffix('%s')}<c698>{MIDDLE[target]}</C></C>\n<C0>{SKILL_DESCRIPTION_TEXT[target]}"
                            self.assertEqual(tr.translate(source, mode), expected)

    def test_exact_reported_skill_input_translates_every_dynamic_slot(self):
        source = (
            "<C3></C>【魔法攻击<I278>／<I295><C3>地点·圆S</C>】"
            "<c698>延迟<c698>中</C></C><c698>／</C><c698>冻结40％</C>\n"
            "<C0><C9>缠绕着凛冽寒风的猛烈连续攻击。"
        )
        for target in LANGUAGES:
            with self.subTest(target=target):
                tr = MenuTranslator(full_entries(), target, "ja", "zh-Hans")
                expected = (
                    f"<C3></C>【{ARTS_ATTACK_TEXT[target]}<I278>／<I295><C3>"
                    f"{TARGET_RANGE_TEXT[target]}{RANGE_S[target]}</C>】<c698>"
                    f"{DELAY_TEXT[target].removesuffix('%s')}<c698>{MIDDLE[target]}</C></C>"
                    f"<c698>／</C><c698>{FREEZE_TEXT[target].replace('%d', '40').replace('%%', '%')}</C>\n"
                    f"<C0>{SKILL_DESCRIPTION_TEXT[target]}"
                )
                self.assertEqual(tr.translate(source, "primary"), expected)

    def test_exact_reported_details_runtime_model_matches_python_for_all_targets(self):
        skill_source = (
            "<C3></C>【魔法攻击<I278>／<I295><C3>地点·圆S</C>】"
            "<c698>延迟<c698>中</C></C><c698>／</C><c698>冻结40％</C>\n"
            "<C0><C9>缠绕着凛冽寒风的猛烈连续攻击。"
        )
        item_source = f"{ITEM_KIND_HELP_TEXT['zh-Hans']}【<I299>{SINGLE_RANGE_TEXT['zh-Hans']}：<c698>{STATUS_TEXT['zh-Hans']}</C> - <I378><c698>{HP_FORMAT_TEXT['zh-Hans'] % 20}</C>】\n{ITEM_DESCRIPTION_TEXT['zh-Hans']}"
        batches = []
        for target in LANGUAGES:
            translator = MenuTranslator(full_entries(), target, "ja", "zh-Hans")
            batches.append(
                {
                    "model": translator.runtime_model(),
                    "cases": [
                        {
                            "source": source,
                            "mode": mode,
                            "expected": translator.translate(source, mode),
                        }
                        for source in (skill_source, item_source)
                        for mode in ("primary", "secondary")
                    ],
                }
            )
        runner = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');const batches=JSON.parse(fs.readFileSync(0,'utf8'));for(const batch of batches){const runtime=new RuntimeText(batch.model);for(const c of batch.cases)assert.strictEqual(runtime.translate(c.source,c.mode),c.expected);}"""
        result = subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(batches),
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_printf_escapes_do_not_consume_numeric_arguments(self):
        entry = {
            "key": "table/t_itemhelp.tbl/test/escaped-percent/format",
            "texts": {
                "zh-Hans": "数值%d",
                "en": "literal %%s / %%d / %d%%%%",
                "ja": "値%d%%",
            },
        }
        batches = []
        for source_language, primary, secondary, source in (
            ("zh-Hans", "en", "ja", "数值7"),
            ("en", "zh-Hans", "ja", "literal %s / %d / 7%%"),
        ):
            translator = MenuTranslator([entry], primary, secondary, source_language)
            cases = [
                {"mode": mode, "expected": translator.translate(source, mode)}
                for mode in ("primary", "secondary")
            ]
            batches.append({"model": translator.runtime_model(), "source": source, "cases": cases})
        self.assertEqual(batches[0]["cases"][0]["expected"], "literal %s / %d / 7%%")
        self.assertEqual(batches[0]["cases"][1]["expected"], "値7%")
        self.assertEqual(batches[1]["cases"][0]["expected"], "数值7")
        runner = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');const data=JSON.parse(fs.readFileSync(0,'utf8'));for(const batch of data){const runtime=new RuntimeText(batch.model);for(const c of batch.cases)assert.strictEqual(runtime.translate(batch.source,c.mode),c.expected);}"""
        result = subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(batches),
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_audited_sized_ranges_cross_all_four_native_size_rows(self):
        hashes = (
            "13a1faa6d4288b2afaeb29863719e1929285152bee56b5943ea806442b6fff7b",
            "19510ff635267619528cd597284f4a27a4051bb07c1a9ed8a0b320811e6b310b",
            "27305a59b8f293e11d3712075fef8ced814a6acd60f6a8d4b81c5a7a9d963dca",
            "2a2c762e0d6517c7db916fe291eb0c21a61dbb9804f6b0c338a115132e4962f9",
            "2f8d4eacb3b590c7e88136642ff0cf2812b5b296dec70f6533e462527cd441f5",
            "5b40935541146eb96f3ddffaf699e2fe36b1489a9fe9b1691fabdbe19b699e70",
            "69edb917c527c1cd62e5da007c513cc9a9247ac40194c275e1fc333e6d059dce",
            "6a15f570d7d4b310463cc8eb627186cd7e4586d9ab2b87e663ebb1e538c2d090",
            "d3740e2d93482a970bdc5c805bb0e4ef863b2ca6ce6809551f3f17f1784c3783",
        )
        values = []
        bases = {}
        for number, digest in enumerate(hashes):
            key = f"table/t_itemhelp.tbl/SkillRangeHelpData/sha256:{digest}/label"
            bases[key] = {language: f"range-{number}-{language}-" for language in LANGUAGES}
            values.append(row(key, texts=bases[key]))
        sizes = {"S": RANGE_S, "M": RANGE_M, "L": RANGE_L, "LL": RANGE_LL}
        values.extend(
            row(f"table/t_text.tbl/TXT_ITEM_HELP_RANGE_{name}", texts=texts)
            for name, texts in sizes.items()
        )
        generated = {entry["key"]: entry["texts"] for entry in item_help_components(values)}
        self.assertEqual(len(generated), len(hashes) * len(sizes))
        for key, texts in bases.items():
            for size, modifiers in sizes.items():
                self.assertEqual(
                    generated[key + "/composed/TXT_ITEM_HELP_RANGE_" + size],
                    {language: texts[language] + modifiers[language] for language in LANGUAGES},
                )

    def test_stat_typed_grade_name_crosses_all_five_magnitudes_in_all_languages(self):
        values = [
            row(RECOVERY, texts=RECOVERY_TEXT),
            row(RECOVERY.removesuffix("/name") + "/stat", texts=RECOVERY_STAT),
        ]
        values.extend(
            row("table/t_text.tbl/TXT_ITEM_HELP_" + name, texts=texts)
            for name, texts in MAGNITUDES.items()
        )
        generated = {entry["key"]: entry["texts"] for entry in item_help_components(values)}
        self.assertEqual(len(generated), len(MAGNITUDES))
        for name, modifiers in MAGNITUDES.items():
            self.assertEqual(
                generated[RECOVERY + "/composed/TXT_ITEM_HELP_" + name],
                {
                    language: RECOVERY_TEXT[language].replace("%s", modifiers[language])
                    for language in LANGUAGES
                },
            )

    def test_real_self_circle_and_item_header_translate_all_target_languages(self):
        source_skill = f"<C3>{SELF_RANGE_TEXT['zh-Hans']}{RANGE_L['zh-Hans']}</C>\n<C0>{SKILL_DESCRIPTION_TEXT['zh-Hans']}"
        source_item = f"{ITEM_KIND_HELP_TEXT['zh-Hans']}【<I299>{SINGLE_RANGE_TEXT['zh-Hans']}：<c698>{STATUS_TEXT['zh-Hans']}</C> - <I378><c698>{HP_FORMAT_TEXT['zh-Hans'] % 20}</C>】\n{ITEM_DESCRIPTION_TEXT['zh-Hans']}"
        for target_language in LANGUAGES:
            with self.subTest(target=target_language):
                tr = MenuTranslator(full_entries(), target_language, "ja", "zh-Hans")
                self.assertEqual(
                    tr.translate(source_skill, "primary"),
                    f"<C3>{SELF_RANGE_TEXT[target_language]}{RANGE_L[target_language]}</C>\n<C0>{SKILL_DESCRIPTION_TEXT[target_language]}",
                )
                expected_item = f"{ITEM_KIND_HELP_TEXT[target_language]}【<I299>{SINGLE_RANGE_TEXT[target_language]}：<c698>{STATUS_TEXT[target_language]}</C> - <I378><c698>{HP_FORMAT_TEXT[target_language] % 20}</C>】\n{ITEM_DESCRIPTION_TEXT[target_language]}"
                self.assertEqual(tr.translate(source_item, "primary"), expected_item)

    def test_generated_components_do_not_split_unknown_adjacent_text(self):
        tr = MenuTranslator(entries(), "en", "ja", "zh-Hans")
        self.assertEqual(tr.translate("我方·圆自定义", "primary"), "我方·圆自定义")
        self.assertEqual(tr.translate("自定义我方·圆L", "primary"), "自定义我方·圆L")

    def test_missing_or_conflicting_range_locale_remains_untranslated(self):
        values = entries()
        del values[1]["texts"]["ja"]
        self.assertEqual(MenuTranslator(values, "en", "ja").translate("我方·圆L"), "我方·圆L")
        values = entries()
        values.append(row("table/t_itemhelp.tbl/other/name", "我方·圆L", "Conflict", "別Ｌ"))
        self.assertEqual(MenuTranslator(values, "en", "ja").translate("我方·圆L"), "我方·圆L")

    def test_unverified_range_kinds_are_not_guessed_from_text(self):
        values = entries()
        values[0] = {**values[0], "key": "table/t_itemhelp.tbl/SkillRangeHelpData/unknown/label"}
        values.append(
            row(
                "table/t_itemhelp.tbl/SkillRangeHelpData/unknown/short_label", "全体", "All", "全体"
            )
        )
        tr = MenuTranslator(values, "en", "ja", "zh-Hans")
        self.assertEqual(tr.translate("我方·圆L", "primary"), "我方·圆L")
        self.assertEqual(tr.translate("全体L", "primary"), "全体L")

    def test_attribute_numeric_and_format_slots_do_not_create_grade_pairs(self):
        values = [
            row("table/t_text.tbl/TXT_ITEM_HELP_SMALL", "小", "(S)", "小"),
            row("table/t_text.tbl/TXT_ITEM_HELP_RANGE_L", "L", "(L)", "Ｌ"),
            row(RECOVERY.removesuffix("/name") + "/format", "回复%s", "Recover %s ", "%s回復"),
            row(
                "table/t_itemhelp.tbl/SkillEffectHelpData/attribute/name",
                "%s属性追击",
                "%s Arts Attribute Attack",
                "%s属性追撃",
            ),
            row("table/t_itemhelp.tbl/SkillEffectHelpData/stat/format", "%s", "%s", "%s"),
            row(
                "table/t_itemhelp.tbl/SkillRangeHelpData/all/short_label",
                "全体（非战斗时）",
                "All (outside combat)",
                "全体（非戦闘時）",
            ),
        ]
        self.assertEqual(item_help_components(values), [])


if __name__ == "__main__":
    unittest.main()
