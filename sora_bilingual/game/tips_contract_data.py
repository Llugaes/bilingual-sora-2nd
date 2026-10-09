"""Reviewed Tips post-load record capability; adds no hook."""

TIPS_FUNCTIONS = {
    "tips_table_load": {
        "leaf": False,
        "variants": [
            {
                "size": 426,
                "sha256": "24e342274da101bdf5de9d420c08a58f39d4d4d07ca1ca285ad656bb30f5ff92",
                "masks": [[53, 4], [83, 4], [88, 4], [284, 4], [297, 4], [307, 4]],
                "points": {"tips_table_load": 0},
                "links": [
                    {
                        "displacement": [88, 4],
                        "next": 92,
                        "function": "tips_descriptor_compare",
                        "addend": 0,
                    },
                    {
                        "displacement": [307, 4],
                        "next": 311,
                        "function": "diagnostic_report",
                        "addend": 0,
                    },
                ],
                "globals": [{"name": "tips_table_vtable", "displacement": [53, 4], "next": 57}],
                "data_refs": [
                    {
                        "displacement": [83, 4],
                        "next": 87,
                        "size": 14,
                        "sha256": "46bad29750503954df8e499072cb1902183833862c5788c6855d27dd6ffd58da",
                    },
                    {
                        "displacement": [284, 4],
                        "next": 288,
                        "size": 35,
                        "sha256": "fd136885aed292d4934e1d950ae99ad86ae5df4e54adbc1e4058e0ad3cc4d8fb",
                    },
                    {
                        "displacement": [297, 4],
                        "next": 301,
                        "size": 85,
                        "sha256": "3c8a4fb15dd3524103a2427b67f613faa1419b67a40975e8f264c12bc7f418fc",
                    },
                ],
            }
        ],
    },
    "tips_descriptor_compare": {
        "leaf": False,
        "variants": [
            {
                "size": 103,
                "sha256": "424d02467c5f002d61293eddcbe0fc51fc3095e7500c2ba5e24c7802fde1cdf0",
                "masks": [],
                "points": {},
                "links": [],
                "globals": [],
            }
        ],
    },
}

TIPS_GLOBAL_SPECS = {
    "tips_table_vtable": {
        "alignment": 8,
        "rtti": ".?AVTipsTable@datatable@sora@@",
        "writable": False,
    }
}
