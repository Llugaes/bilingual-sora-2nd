# r22 candidate evidence and open acceptance gates

The deployed r21-rev3 failed this feedback batch. This isolated candidate is
based on clean source `341d51cef882d146d32b8058572dce3d51f2c065`. Older DEV roots
remain intact. No game launch, restart, resident replacement or additional game
attachment was performed for these changes. The user normally closed the game.

## Inputs and evidence levels

| Reported case | Available evidence | Candidate status |
|---|---|---|
| General's Mantle X: duplicated EN Resist Stat Debuff/Sleep 100% | Complete actual setter source, null key/scope, captured resident snapshot | Three fresh final modes pass offline; pixels pending |
| CP skill STR strength/duration | Screenshot plus raw resource/native-constructor fixtures, including no-space I270 and strength2 I271 | Known roles and separate effect lanes pass; full actual setter source and pixels pending |
| Gaia Shield reflect count and Shield (M) | Screenshot plus raw Gaia Shield fields/body and controlled header | Three final modes pass resource replay; actual setter source and pixels pending |
| La Curia Recover 30% HP | Screenshot plus raw La Curia fields/body and controlled header | Three final modes pass resource replay; actual setter source and pixels pending |
| First-line sinking/body crowding | Screenshot, previous static lane classification, production callback harness | Body now owns the same lane protocol as its header; actual glyph bounds/measurement/draw and pixels pending |

The actual source is in `tests/fixtures/r22-actual-cloak-source.json`, copied
verbatim from `generated/r21-existing-owner-snapshot-20261006T121156434111Z.json`
(SHA256 `ecc1e3d8cbc8a62b25dddfe1aff95a199c10f8169d28f380dc3bfa088f57fffb`).
Its key/scope remain null. Snapshot displayed text was collected after normal
translation disable; it is not presented as screenshot-time output. The wire
path matched the deployed root, but the snapshot explicitly records
`content_hash_verified=false`; disk hashing does not prove resident bytes.

## Concrete changes

- Preserve each admitted resource role and opaque styled fragment as a separate
  unit. The old fallback merged their IDs/parameters and EN text into one large
  annotation. Use the same effect planner for all three final modes.
- Compile complete type1 numeric names, bounded type13 magnitude constants,
  single type4 percent recovery, and SkillConnectListData kind1 resistance
  groups. Existing chance_single identities remain unchanged. The actual cloak
  is ItemTableData1547 with effects1111/1103 and equal value100; it is not an
  effect98 ConditionInfo mask or a newly added Sleep alias.
- Admit exact native kind4 icon/turn constructor variants. The verified d8b2911d
  EXE sample selects I270/I271/I272 by strength1/2/3; the no-space Western path
  concatenates stat+icon+turns. This proves a fixture constructor, not the
  screenshot's icon ID or its uncaptured full setter string.
- Prefer an already-proved atomic revive/compound constructor over a lower
  priority partition; equal-priority conflicting targets still refuse.
- Appended translated bodies use empty-anchor owned lanes when the header is
  layered. Native agent code is unchanged. No fixed y adjustment was added.
  Existing native ruby and other header domains retain their existing parser.

Unknown controls, invalid/overflow arguments and whole/role target conflicts
remain hard refusals. There is no general comma/slash split, token whitelist,
global alias or injected owner/key/scope.

## Validation and limitations

- `generated/r22-reported-final-render.json`: four reported cases, each final
  mode rendered first with a fresh resolver; actual cloak source unchanged.
- `generated/r22-family-oracle-final.json`: 326 independently derived raw PAC
  constructor rows, all three modes, zero failures. These reuse immutable model
  indexes but clear plans/refusals before each input; the four-case and independent
  gates instantiate fresh resolvers.
- `generated/r22-production-frida.json` and packaged companion: complete indexed
  production wire in V8 on a self-created hidden host; fresh final modes, original
  r20 captured-success inputs, hard whole conflicts and integer overflow.
- `generated/r22-final-node.log`: 167 tests pass, including owned header/body
  lanes, repeated measurement/draw callbacks and user line gap. Callback/pointer
  fixtures are not actual scene glyph positions.
- `generated/r22-final-python.log`: 70 tests, 69 pass and one pre-existing failure.
  `generated/r22-preexisting-test-comparison.json` reproduces the same assertion
  on baseline341d51c using its original Python compiler/renderer and JS renderer:
  an external ambiguous CP role next to existing native ruby remains EN. This
  unresolved case is explicitly preserved; the suite is not declared green.
- `generated/r22-native-initializer-proof.json`: initializer/newline bytes and
  production callbacks exercised on a hidden host against the verified d8b2911d
  sample. It does not prove current game label bounds or visual spacing.
- `generated/r22-independent/audit-r21-feedback/unified-gate-result.json`: exact
  unmodified task4 raw inventory/replay/gate tools, explicitly fixed candidate
  DEV/wire/renderer identities. Semantic status is separate from PENDING geometry
  and BLOCKED live acceptance. The gate deliberately exits1 while these remain.

Raw catalog and language facts are reused only after resource/code identities
match. The final compilation took43.9s, with3135 fact hits and0 misses. Phase
timings and exact compiler/resource identities are in
`generated/r22-production-receipt.json`. No old model, user state, font receipt,
resident handle or agent token is imported. The runtime byte inventory is the
independently verified552-file r14 runtime, not a copied operational session.

This package is for independent review and reversible DEV deployment. It has
not been deployed or publicly released. No reported changed scene is certified
fixed in-game. After code/package review, request only the next needed scene,
starting with the actual cloak already captured; do not ask for a full replay of
every earlier page.

## rev2: independent review blocker and minimal propagation fix

The independent fixed-r22 review rejected the initial candidate. Its expanded
gate correctly detected that a matched conflicting compound constructor could
be bypassed by shorter valid partitions. The earlier semantic PASS covered the
reported positive inputs but did not close this negative. The initial r22 root
and ZIP are preserved and are not approved for deployment.

The rev2 production delta is eight added lines and one replaced line in
`runtime_text.js` and `menu_text.py`: when a complete candidate returns a matched
`invalid_effect_parameter` or `conflicting_effect_member`, `effectUnits` refuses
the enclosing list immediately. Unproved unknown text can still coexist with
independent admitted roles. No conflict gate was removed or generalized.

`tests/fixtures/r22-compiled-conflict-source.json` comes from the independent
reviewer's real MenuTranslator veto fixture. Its counterexample is
`Recover 30% HP/EP, Cure Status Ailments, Cure Stat Debuff` followed by an official
body. The compiler removes the conflicting full constructor and emits blocked
numeric metadata. Before the fix both Python/JS final mode orders translated
shorter roles; after the fix all modes preserve the complete original with no
annotation layers. Valid duplicate-target and compiler-style blocked-template
guards also refuse in all modes. The unknown pure-text tail remains literal
beside the independently translated HP Regen role.

Evidence: `generated/r22-rev2-compiled-conflict-red.json` and `-green.json`,
`generated/r22-rev2-refusal-python-red.log` and `-green.log`,
`generated/r22-rev2-refusal-js-red.log` and `-green.log`, and the fixed production
delta `generated/r22-rev2-shared-refusal-fixed.diff`. The already-passed actual
cloak, captured Arts and CP effect lanes are rechecked against the final wire
and package. The 326-family matrix is not repeated for this propagation delta.

Current-EXE native evidence is taken directly from the independent receipt
`generated/r22-rev2-independent/audit-r22/independent-current-native-correspondence.json`:
CAB62e SHA256 `cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`;
kind1 stat/format/parts and kind4 strength1/2/3, turns/format/concatenation all
match their bounded current instructions and RIP targets. Initializer and
newline exact byte hits are current RVA0x583970 and0x5881e6. Old d8b2911d RVAs
are historical evidence only; the verified local0x850 correspondence is not a
global resolver offset. This receipt proves bounded static correspondence,
not actual setter flow or visible glyph geometry. No additional attachment or
call-graph investigation was performed.

## rev3: native-R context and configured spacing contract

The rev2 review correctly identified native-R context/spacing as an open
functional case. It is now exercised rather than waived as a baseline failure.
The original compiled counterexample and a small readable fixture first fail
on rev2 and then pass on the new source in all three final modes.

`effectLineUnits` protects validated complete native-R spans as unchanged opaque
units, and routes only the outside spans through the existing effect parser.
The exact description's already-compiled context may admit an otherwise
unassociated literal; a matched parameter/conflict refusal still terminates
before any contextual fallback. No new global alias, guessed owner, parameter
whitelist or general split rule is introduced. Malformed/nested R grants no
effect plan. Existing R is not copied into a new auxiliary payload or nested.

External effects and the exact translated body use separate owned anchors.
Even a header containing only native R shares the owned body's lane protocol.
Layout classification recognizes the preserved reading in the primary text
and regards a validated native-R-only line as covered by its original parser.
This retains native advances and allows the existing newline callback to add
the configured gap to its temporary native bottom. No hook or fixed offset
was added.

`tests/fixtures/r22-native-ruby-detail.json` is the readable contract fixture;
`generated/r22-rev3-native-ruby-fixture.json` preserves the independent real
compiled model. `tests/check_r22_native_ruby.js` verifies final modes, no R
duplication, malformed/wrong-context/overflow/unknown-control boundaries.
The production native-agent callback test covers native leading-1/0/15,
measurement and draw, three repetitions, native-R-only and mixed headers,
line_gap6, both single-language modes and disabled restoration. The original
native-R context test now passes: current Python72/72 and JS168/168 are green.

The full indexed production-wire V8 replay retains the prior actual cloak,
Arts and CP gates, adds the real native-R contract and a controlled native-R
case on the production model, and keeps both compound refusal guards. The
326-family matrix is not repeated. Current CAB62e constructor and initializer
bytes are the already-audited receipt; hooks and nested initializer callbacks
are unchanged, with only row classification updated.

Red/green and callback evidence is under `generated/r22-rev3-native-*.log`;
the fixed production delta is `generated/r22-rev3-native-ruby-fixed.diff`.
These checks close the functional context/configured-spacing contract, not
actual scene glyph extents or a visual collision. Final candidate pixels and
the uncaptured CP/Gaia/La Curia setter strings remain unverified.

## rev4: terminal malformed-R refusal

The rev3 incremental audit found a stray `</RCP Regen>` falling through to
description/context translation and widening the production callback bottom.
Final Python render/translate and JS render/resolve now reject malformed R
before ownership, keyed/context or body fallbacks. `effectLineUnits` distinguishes
an invalid range result from a valid source without ruby. The shared range
validator also refuses an invalid opening before a valid R and a closing reading
that borrows the next control tag's `>`.

Eight bounded malformed forms cover orphan open/close, missing close terminator,
nested opening, surplus closing and invalid opening tokens. Two unchanged
positive models, all three final modes and both mode orders preserve exact input
with zero layers. Production callbacks cover cold labels and labels previously
owning valid R; malformed inputs retain native bottom100 with no configured-gap
flag, then recover valid R bottom106 and disabled bottom100. Existing native-R
context/body and compound/parameter refusals remain green. Python72/72 and
Node168/168 pass. No native-agent, hook, schema or resource modification was made.

The fixed delta is `generated/r22-rev4-malformed-fixed.diff`; source, package and
red callback receipts use `generated/r22-rev4-malformed-*`. The full production
V8 replay includes the bounded malformed family. This closes the functional
syntax gate; actual game pixels and glyph bounds still require private DEV
acceptance. The historical 326-family matrix is not repeated.
