# Retired r26 native item-help tests

These files are retired by the r26 P0 withdrawal of the native ItemHelpIdentities
feature. They retain their original bytes under `.js.txt` so test discovery does
not execute a feature that is no longer in the runtime.

The tests assumed synthetic postload owners and accepted source-only rejection
even where the r25 complete translation already succeeded. Their passes are not
real widget compatibility or gameplay performance evidence. Keep them as failed
approach evidence, not as validation of the recovery.

The original implementation and runnable tests remain at commit
`42219bd865dcb115377fe8c26cb419bd43bf60b6`. Reproduce them only in an isolated
offline checkout with that commit's source. Do not restore the feature into the
recovery branch or attach it to a game.

Current regression: `tests/test_item_help_p0_restoration.js`. The frozen r25/r26
three-mode counterexample is `generated/r26-p0-callback-three-mode.json`.

The two unreferenced producer modules `item_help_contract_data.py` and
`item_help_identity.py` are preserved here byte-for-byte as `.py.txt` files.
They had already been removed from release/reload ownership. Keeping them in
the active production tree broke its dependency/inventory checks; archiving
them completes withdrawal without restoring the rejected native feature or
weakening those checks. Byte receipts: `generated/r26-p0-local-retired-modules.json`.
