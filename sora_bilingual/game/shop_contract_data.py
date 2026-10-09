"""Reviewed shop choice ownership contracts; sample hashes are provenance only."""

SHOP_FUNCTIONS = {
    "shop_action_copy": {
        "leaf": False,
        "variants": [
            {
                "size": 596,
                "sha256": "45681236b8e1254046d3323af2fe0e6977d0acc32b2633602d70ca70b47f8432",
                "masks": [
                    [22, 4],
                    [53, 4],
                    [71, 4],
                    [76, 4],
                    [274, 4],
                    [295, 4],
                    [300, 4],
                    [311, 4],
                    [321, 4],
                    [342, 4],
                    [347, 4],
                    [358, 4],
                    [368, 4],
                    [384, 4],
                    [409, 4],
                    [422, 4],
                    [434, 4],
                    [454, 4],
                    [478, 4],
                    [491, 4],
                    [503, 4],
                    [569, 4],
                ],
                "points": {"shop_yes_copy_return": 438, "shop_no_copy_return": 507},
                "links": [
                    {"displacement": [53, 4], "next": 57, "function": "set_text", "addend": 0},
                    {"displacement": [76, 4], "next": 80, "function": "shop_key_hash", "addend": 0},
                    {
                        "displacement": [274, 4],
                        "next": 278,
                        "function": "shop_trade_mode",
                        "addend": 0,
                    },
                    {
                        "displacement": [300, 4],
                        "next": 304,
                        "function": "shop_key_hash",
                        "addend": 0,
                    },
                    {
                        "displacement": [321, 4],
                        "next": 325,
                        "function": "shop_create_mode",
                        "addend": 0,
                    },
                    {
                        "displacement": [347, 4],
                        "next": 351,
                        "function": "shop_key_hash",
                        "addend": 0,
                    },
                    {
                        "displacement": [368, 4],
                        "next": 372,
                        "function": "shop_key_hash",
                        "addend": 0,
                    },
                    {"displacement": [409, 4], "next": 413, "function": "text_lookup", "addend": 0},
                    {"displacement": [422, 4], "next": 426, "function": "shop_printf", "addend": 0},
                    {"displacement": [434, 4], "next": 438, "function": "set_text", "addend": 0},
                    {"displacement": [478, 4], "next": 482, "function": "text_lookup", "addend": 0},
                    {"displacement": [491, 4], "next": 495, "function": "shop_printf", "addend": 0},
                    {"displacement": [503, 4], "next": 507, "function": "set_text", "addend": 0},
                ],
                "globals": [
                    {"name": "shop_text_owner_global", "displacement": [384, 4], "next": 388},
                    {"name": "shop_text_owner_global", "displacement": [454, 4], "next": 458},
                ],
                "data_refs": [
                    {
                        "displacement": [71, 4],
                        "next": 75,
                        "size": 18,
                        "sha256": "ba8e0d2567b61b9124b768ab42def4ecc10e9ab2ed251dbac6f58735efc6e199",
                    },
                    {
                        "displacement": [295, 4],
                        "next": 299,
                        "size": 16,
                        "sha256": "e3f09e5438fc3446dd59bf23e3e9ccd5ff08a4ad9e28531cf37a1222ee65a7a5",
                    },
                    {
                        "displacement": [311, 4],
                        "next": 315,
                        "size": 18,
                        "sha256": "47d3e2f7f9d32c34ca9460674ec869c55c53e689a2a7253a233a8dfd37d8cb3e",
                    },
                    {
                        "displacement": [342, 4],
                        "next": 346,
                        "size": 22,
                        "sha256": "4ae6317f8af2731a9ee2d8de42dbc6312da0b0fc62a20badb34e3da7c34c0926",
                    },
                    {
                        "displacement": [358, 4],
                        "next": 362,
                        "size": 19,
                        "sha256": "c75ece2f881f6d249b20b035a5e9badb083dc72e9cf95e8bf44b76746f1b6f07",
                    },
                ],
            }
        ],
    },
    "shop_printf": {
        "leaf": False,
        "variants": [
            {
                "size": 179,
                "sha256": "9f8046fe76df0bc088c49fad6b2aacca5c2d58b50d70f278056718fec1ac2977",
                "masks": [[38, 4], [51, 4], [80, 4], [105, 4], [148, 4]],
                "points": {},
                "links": [
                    {
                        "displacement": [51, 4],
                        "next": 55,
                        "function": "shop_printf_length",
                        "addend": 0,
                    },
                    {
                        "displacement": [80, 4],
                        "next": 84,
                        "function": "shop_printf_copy",
                        "addend": 0,
                    },
                    {
                        "displacement": [105, 4],
                        "next": 109,
                        "function": "shop_printf_options",
                        "addend": 0,
                    },
                    {
                        "displacement": [148, 4],
                        "next": 152,
                        "function": "shop_printf_engine",
                        "addend": 0,
                    },
                ],
                "globals": [],
                "data_refs": [
                    {
                        "displacement": [38, 4],
                        "next": 42,
                        "size": 1,
                        "sha256": "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
                    }
                ],
            }
        ],
    },
    "shop_printf_engine": {
        "leaf": False,
        "variants": [
            {
                "size": 329,
                "sha256": "bf744b659bf1da3c2c7d9d1ef7f599690cada7d5617592c334c914523180fe5e",
                "masks": [
                    [97, 4],
                    [147, 4],
                    [157, 4],
                    [171, 4],
                    [209, 4],
                    [229, 4],
                    [239, 4],
                    [261, 4],
                    [272, 4],
                    [283, 4],
                    [294, 4],
                ],
                "points": {},
                "links": [],
                "globals": [],
            }
        ],
    },
    "shop_text_lookup": {
        "leaf": False,
        "variants": [
            {
                "size": 131,
                "sha256": "2fdfe32bdea95266051f14d34bba174cd10cd1572d3394bd8be0790cdc245b02",
                "masks": [[82, 4]],
                "points": {},
                "links": [],
                "globals": [],
            }
        ],
    },
    "shop_key_hash": {
        "leaf": True,
        "variants": [
            {
                "size": 41,
                "sha256": "d97ceb64e51a71f13deaae6e18fd5c79a516ed0f856478a681a37b63e91b335c",
                "masks": [[16, 4]],
                "points": {},
                "links": [],
                "globals": [],
                "data_refs": [
                    {
                        "displacement": [16, 4],
                        "next": 20,
                        "size": 1024,
                        "sha256": "12f3e0576d447eb37b36d82ba0c1c5481b8f0d12fdc70347ce4a076b229d4c86",
                    }
                ],
            }
        ],
    },
    "shop_trade_mode": {
        "leaf": False,
        "variants": [
            {
                "size": 149,
                "sha256": "85b8617b94b287e4e84c5464493fc0bd829b129215707aa3bed01153624089b3",
                "masks": [[13, 4]],
                "points": {},
                "links": [],
                "globals": [
                    {"name": "shop_text_owner_global", "displacement": [13, 4], "next": 17}
                ],
            }
        ],
    },
    "shop_create_mode": {
        "leaf": False,
        "variants": [
            {
                "size": 804,
                "sha256": "b1bce232992ea2103b22d64bda2deeda8bbb2d53df2d3a97f42e0b8252cd21bc",
                "masks": [
                    [31, 4],
                    [104, 4],
                    [239, 4],
                    [303, 4],
                    [320, 4],
                    [354, 4],
                    [371, 4],
                    [419, 4],
                    [426, 4],
                    [523, 4],
                    [652, 4],
                    [700, 4],
                    [752, 4],
                    [770, 4],
                ],
                "points": {},
                "links": [
                    {
                        "displacement": [320, 4],
                        "next": 324,
                        "function": "font_allocate",
                        "addend": 0,
                    }
                ],
                "globals": [
                    {"name": "shop_text_owner_global", "displacement": [104, 4], "next": 108},
                    {"name": "font_allocator_global", "displacement": [303, 4], "next": 307},
                    {"name": "font_allocator_global", "displacement": [371, 4], "next": 375},
                    {"name": "font_allocator_global", "displacement": [652, 4], "next": 656},
                ],
            }
        ],
    },
    "shop_printf_length": {
        "leaf": True,
        "variants": [
            {
                "size": 633,
                "sha256": "2dd70d4bd83fd68275d9b1f2312de7240f4d2f6ca26427d3dd76f77d93d35278",
                "masks": [[2, 4], [338, 4]],
                "points": {},
                "links": [],
                "globals": [
                    {"name": "shop_strlen_cpu_flags", "displacement": [2, 4], "next": 6},
                    {"name": "shop_strlen_cpu_flags", "displacement": [338, 4], "next": 342},
                ],
            }
        ],
    },
    "shop_printf_copy": {
        "leaf": False,
        "variants": [
            {
                "size": 354,
                "sha256": "86eb27c27f85716d8e1b29deda37aeba2c73ecf10425cfc2d4eb8a1aa59ef5de",
                "masks": [],
                "points": {},
                "links": [],
                "globals": [],
            }
        ],
    },
    "shop_printf_options": {
        "leaf": True,
        "variants": [
            {
                "size": 8,
                "sha256": "42bf2fe8994233d2e2eaf9d217f425ee1530fb5e5d6924672ca17f13bdf43411",
                "masks": [[3, 4]],
                "points": {},
                "links": [],
                "globals": [
                    {"name": "shop_printf_options_global", "displacement": [3, 4], "next": 7}
                ],
            }
        ],
    },
}

SHOP_GLOBAL_SPECS = {
    "shop_text_owner_global": {"alignment": 8, "writable": True},
    "shop_strlen_cpu_flags": {"alignment": 4, "writable": True},
    "shop_printf_options_global": {"alignment": 8, "writable": True},
}
