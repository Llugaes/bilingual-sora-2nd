# Dynamic notification omissions

`tests/check_notification_omissions.py` replays the reported notification
sources from the installed PAC/table catalog through production `RuntimeText`.
It creates all catalog/model files in a temporary directory and does not
attach to, start, or modify the game. Its JSON output is
`generated/notification-omissions.json`.

## Resource evidence and correction

The bamboo-fishing-rod notification is item ID `483`, from
`script/scena/talk_common.dat`, `TK_NORCHE_ITEM_GET`, called ID `20`.
The zh-Hans control stream calls `ITEM_ADD_MESSAGE2_TK(483, "拿到了",
"。")`; Japanese calls `ITEM_ADD_MESSAGE_TK(483, "を受け取った。")`.
The producer only accepted the `_EV` variants, so this complete `_TK` source
was absent from the producer catalog. Both `_TK` and `_EV` item-message
families are now compiled.

The recipe notification is `system.dat`, `UnLockRecipe`, called ID `2`, whose
opcode-17 value selects the item at runtime. Item ID `2130` is `丰熟咖喱饭`.
The captured source contains `<I10>`, while the former producer rendered every
recipe as `<I12>`. Item addition had the same fixed-icon defect (`<I110>`).
Both producer templates now use `<I%d>` and declare a numeric icon slot for
the existing producer-numeric compiler.

The quest source
`<C1>达成了委托【<C2>艾尔贝周游道的通缉魔兽<C1>】！` already has a complete
eight-language static catalog pair in `script/scena/system.dat`, `OnQuestEnd`,
called IDs `52` and `73`. These are separate physical calls with the same
complete text and must retain their independent identities. The partial
zh-Hant/ko code records at called IDs `78` and `120` do not license a
`t_quest.tbl` title-to-`OnQuestEnd` producer: the title row is ID `98` but the
`OnQuestEnd` calls use a different 1--83 value domain. A missing live quest
annotation therefore belongs to model delivery/runtime lookup validation, not
to a synthesized quest producer.

## Offline verification

Run from the repository root:

```powershell
python tests/check_notification_omissions.py --game-dir 'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter' --output generated/notification-omissions.json
python -m unittest tests.test_dynamic_producers
```

The first command checks the raw `OnQuestEnd` denominator per installed source
locale, producer denominators by family, and the exact complete source for
item `483`, recipe `2130`, and the quest. For both ja and en it requires exact
primary/secondary translations plus a non-plain, one-layer `render` result
whose visible payload equals the secondary translation. This is stronger than
a snapshot-only check.

The producer unit suite covers the `_TK` single and split call forms and the
runtime icon placeholder. It passed: `7 tests`.

The final full-catalog run passed ja and en for all three sources. Its raw
denominators were `159` `item_add_message` records, `157` `unlock_recipe`
records, `63` assembled `OnQuestEnd` calls in each of the eight locales, and
two complete records for the reported quest source. The final ja/en models
are retained as `generated/diagnostic-134-model-ja.json` and
`generated/diagnostic-134-model-en.json` for the history fallback audit.

## Remaining live validation

Offline results prove catalog construction and JavaScript rendering only. In a
new normal game process, trigger the bamboo item acquisition, the recipe
unlock, and the quest completion. Confirm each notification is one annotation
layer containing the whole sentence, then preserve the diagnostic/model
signature used for that process if any quest notification still resolves as
plain text.

## Full producer sweep and unresolved provenance

The final bulk command reuses the extracted catalog and final models. It does
not compile a model:

```powershell
python tests/check_notification_omissions.py --game-dir 'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter' --existing-catalog-dir generated --model-dir generated --all-producers --output generated/notification-omissions.json
```

All eight source locales have 159 valid static `ITEM_ADD_*` item-ID calls,
157 recipe item IDs (2100--2316), and one template each for BP gain, rest,
and recipe unlock. The catalog and each final ja/en model contain all 318
producer records/rules. The sweep probes every complete string, including
integer boundaries and opaque icon syntax. Japanese completes all 1,279
probes. English leaves eight failures: item ID 220 occurs at two independent
calls with the same zh-Hans source but `Received …` versus `Obtained …` full
English text. The current global fallback combines the Chinese template with
only `Wood Door Key`; this is recorded as a failure, never accepted as a full
translation.

`system.dat/RegisterBook/called/2` is the sole unverified dynamic notification
operation. Its opcode-17 parameter is a VM string, not a stable table ID.
The only SCP caller, `OnBooksNoteClose/called/5`, forwards another VM slot.
Although `t_books.tbl` contains title pairs, no raw SCP relation proves that
this slot selects a particular title row, so the audit retains it as unknown
instead of producing a title cartesian product.

## ID 220 provenance contract

The eight English failures are two distinct physical producers, not an
ambiguous catalog row that may select a canonical translation.  Their outer
calls in zh-Hans `script/scena/mp3000_ev.dat` are:

| outer call ID | item token | prefix token / raw offset | suffix token / raw offset | outer next PC |
| --- | --- | --- | --- | --- |
| `EV_02_28_00/called/488` | `0x400000dc` (220) | `0xc016ae3a` / `0x16ae3a` | `0xc016ae36` / `0x16ae36` | `0xdef37` |
| `EV_02_28_00_END/called/0` | `0x400000dc` (220) | `0xc016b3d8` / `0x16b3d8` | `0xc016b3d4` / `0x16b3d4` | `0xe04ba` |

Both offsets decode to the same displayed Chinese prefix and suffix, but the
encoded arguments are different resource identities.  The first has the full
English producer `Received <C0><I%d></C><C5>Wood Door Key</C>.`; the second
has `Obtained <C0><I%d></C><C5>Wood Door Key</C>.`.

Both outer calls enter `ITEM_ADD_MESSAGE2_EV`, whose code forwards its item,
prefix, and suffix slots to command 8 / opcode 17.  At the dynamic builder,
the VM therefore names the helper and its inner command PC, not either outer
PC above.  Existing fields are sufficient to observe the helper (`vm+0x88`),
its PC (`vm+0x10`), and raw stack words (`stack=vm+0x58`, signed top at
`vm+0x64`, argc at `vm+0x70`), but no verified VM parent-frame offset exists.
Do not derive an outer ID from the current helper PC.

The safe implementation contract is a compiled, per-script identity map:
`script blob SHA-256 + helper name + forwarded raw argument tokens -> outer
producer call ID`.  It must retain every raw outer call record and resolve
the exact local producer rule before translation.  The raw string-pointer
tokens above supply the tie-breaker for ID 220 without selecting a global
same-string candidate.  The native hook must then carry that bounded
short-lived identity from the builder output to the notification label; the
output buffer is a concatenated heap string and cannot subsequently be
reverse-mapped with `pointerSelect`.

`tests/check_native_dynamic_identity.py --exe <sora_2nd.exe>` is an offline
contract check. It decodes the installed executable, derives the two actual
command-8 streams from the installed SCP bytes, then passes those same streams
through a self-created hidden Python/Frida process. No game process is
attached. The fixture proves bounded reverse stack reads and that the exact
builder output pointer reaches the label setter; the SCP/EXE inspection proves
how those specific raw streams are formed.

The static wrapper handoff covered by that check is:

| wrapper | builder call | builder output | label setter call |
| --- | --- | --- | --- |
| `dialogue_popup` | `0x4ae4db` | `[rbp-0x60]` | `0x4ae574` |
| `dialogue_message` | `0x4aec2a` | `[rbp-0x20]` | `0x4aecaf` |

In both paths the same local output address is loaded into `rdx` for the
builder and later for `SetText`, while `rcx` is the label at `[rdi+0xc8]`.
A new game process must still prove that live category-2 notifications use one
of these wrappers.

## Dynamic identity compiler sweep

The identity compiler is intentionally narrower than the renderer. It audits
all 159 cataloged `item_add_message` producer records in the source archive,
but emits only the 117 records whose raw outer frame and helper forwarding
program satisfy the proven contract. The remaining 42 are all
`ITEM_ADD_MESSAGE2_TK` calls with a three-value outer frame
`string, string, int`; their helper has `slot(2,3)`, `slot(2,2)`, and
`slot(2,5)`, but no verified local-default/frame rule explains those offsets.
They are counted as `rejected_outer_frame` and omitted. This does not block
ordinary dynamic rendering; it prevents an unproven native call identity.

Run the source-identity sweep with the retained catalog:

```powershell
$env:PYTHONUTF8=1
python -c "import json; from sora_bilingual.localization.dynamic_identity import compile_dynamic_identities; e=json.load(open(r'C:\Users\WINDOWS\AppData\Local\Temp\sora-notification-check-xziv5hgw\catalog.json', encoding='utf-8'))['entries']; print(compile_dynamic_identities(r'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter', e, 'zh-Hans', 'en', 'zh-Hans')['stats'])"
```

The offline result is `catalog_records=159`, `resolved_candidates=117`,
`emitted=117`, `rejected_outer_frame=42`, and `conflicting_tokens=0`. Each
emitted row is keyed as `scripts[sha256][helper][argumentsToken]`; each record
also retains one single-producer model per available source locale. The
capture-side source pattern comes from that producer model and is fully
anchored, so changing the visible output alone cannot pass the identity check.

For ID 220, the audit uses the production identity classes rather than merely
instantiating a selected row. It reads `mp3000_ev.dat`, supplies its actual
SHA-256 blob, helper name, raw command-8 token stream and PC to
`ScriptIdentities.capture`, commits the returned identity through
`LogIdentities`, looks it up again, and only then renders with `RuntimeText`.
Both physical calls pass this chain at icon values `5`, `10`, `110`, and
`2147483647` for Japanese and English: 16 passing capture-to-render probes.
The ordinary global resolver remains separately reported as ambiguous for the
two English full-sentence alternatives; that failure is expected and does not
count as successful identity resolution.

The local-variable resolver is now proven offline.  Opcode 2 at EXE RVA
`0x5e653f` reads `vm+0x64` (top), applies the signed encoded slot offset,
copies from `vm+0x58 + top + offset`, then increases top by four.  This makes
`slot(2,3)`, `slot(2,2)`, and the later `slot(2,5)` relative to the changing
stack, rather than fixed parameter fields.  Applying that verified operation
to each outer frame produces the exact builder streams:

```text
EV_02_28_00:     [0x4000ffff, 0x40000010, 0xc016ae3a, 0x40000011, 0x400000dc, 0xc016ae36]
EV_02_28_00_END: [0x4000ffff, 0x40000010, 0xc016b3d8, 0x40000011, 0x400000dc, 0xc016b3d4]
```

Opcode 36 writes group, command, argc and the post-operand PC into
`vm+0x68`, `+0x6c`, `+0x70`, and `+0x10` before dispatch.  For this helper the
PC is `0xaee59`, group `5`, command `8`, argc `6`.  `dynamic_identity.py`
therefore compiles only an exact `{script SHA-256, helper name, six raw
arguments}` key to its physical outer record.  If one key claims multiple
outer record keys it is omitted and counted as a conflict.  It never chooses a
same-string fallback.

The bridge may carry `{source, identity}` under the output pointer only for
the active wrapper frame, consume it only for the same pointer and source, and
delete it when the frame returns.  A new game process still has to prove that
this notification reaches a verified wrapper.


## Final retained-model replay

The final replay used the status-built production models directly, without a
model compilation:

```powershell
python tests/check_notification_omissions.py --game-dir 'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter' --existing-catalog-dir generated --model-path ja=generated/runtime-9c50bec0e2c35f837c32.json --model-path en=generated/runtime-bf83a770b526f155d191.json --all-producers --output generated/notification-omissions-final.json
```

The raw denominator is identical in all eight source locales: 159 static item
calls, 157 recipe IDs, and four command-8 dynamic operations. Three operations
are verified templates (BP, rest, recipe); the fourth is the eight-locale
`RegisterBook/called/2` unknown described above. The item identity compiler
reports 117 emitted EV identities, 42 rejected TK outer frames, and zero token
conflicts for both ja and en.

Japanese passed all 1,279 global producer and reported-notification probes.
English passed 1,271 of 1,279 global probes; the eight failures are precisely
the two ID220 physical calls at four icon values. Their global result is kept
as a failure because a source-only resolver cannot choose `Received` versus
`Obtained`. The real identity path passed all eight English probes (and all
eight Japanese probes) through the persisted model's actual manifest,
`ScriptIdentities.capture`, `LogIdentities`, and `RuntimeText`.

The report's strict `all_passed` remains false for two recorded reasons: the
eight `RegisterBook` raw operations lack a proven ID relation, and source-only
English lookup deliberately rejects the ID220 ambiguity. These are offline
classification results. A live game process must still verify category-2
routing through the native wrapper and identity capture.
