"""Exact r23 production wire, full final modes and inherited refusal guards."""

import os
import check_r19_production_wire as harness
import check_r22_production_wire as previous

harness.PREFIX = os.environ.get("DEV_VERIFICATION_PREFIX", "r23")
harness.NATIVE = previous.harness.NATIVE.replace(
    "const tr=new RuntimeText(row.fixture_model||globalThis.model),plan=tr.render(row.source,mode,row.key||'',row.scope||'');",
    "const global=new RuntimeText(row.fixture_model||globalThis.model),tr=row.strict_save?global.scoped.save_summary:global,plan=tr.render(row.source,mode,row.key||'',row.scope||'');",
)

if __name__ == "__main__":
    harness.main()
