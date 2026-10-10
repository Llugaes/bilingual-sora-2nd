"""Canonical effect refusal rules, also embedded by the JavaScript generator.

Recorded syntax/contract failures are hard by default. Only lack of role
association permits an ordinary independently admitted resource fallback.
"""

EFFECT_REFUSAL_POLICY = {
    "missing_native_join_contract": "unproved",
    "unassociated_effect_unit": "unproved",
    "partial_effect_members": "unproved",
    "hard_line_or_native_ruby": "hard",
    "invalid_separator_style": "hard",
    "member_budget": "hard",
    "empty_effect_member": "hard",
    "partition_budget": "hard",
    "different_partition_targets": "hard",
    "invalid_effect_parameter": "hard",
    "unproven_effect_parameter": "hard",
    "unproven_standalone_constructor": "hard",
    "unproven_direction_parameter": "hard",
    "conflicting_effect_member": "hard",
    "unsupported_effect_controls": "hard",
    "item_help_header_missing_record_body": "hard",
}
