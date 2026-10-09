"""No process handles: unknown UI types must stay opaque in the collector."""

from argparse import Namespace
from unittest import TestCase
from unittest.mock import Mock

from tools.read_native_layout import (
    Collector,
    LABEL_VTABLE_RVA,
    NODE_CHILDREN_COUNT,
    NODE_CHILDREN_DATA,
    NODE_NAME,
    NODE_PARENT,
)


def options(**changes):
    return Namespace(
        **(
            {
                "source_regex": None,
                "include_node_inventory": True,
                "max_node_types": 2,
                "max_node_examples": 1,
                "max_nodes": 10,
                "max_children_per_node": 10,
                "max_string_bytes": 128,
            }
            | changes
        )
    )


class ReadNativeLayoutTests(TestCase):
    def test_unknown_type_never_reads_text_label_fields(self):
        base, root = 0x10000000, 0x20000000
        allowed = {
            root: base + 123,
            root + NODE_PARENT: 0,
            root + NODE_NAME: 42,
            root + NODE_CHILDREN_DATA: 0,
            root + NODE_CHILDREN_COUNT: 0,
        }
        remote = Mock()
        remote.u64.side_effect = lambda address: allowed[address]
        remote.cstring.return_value = "menu_option"
        collector = Collector(remote, base, options())
        collector.snapshot_label = Mock(side_effect=AssertionError("unknown types are opaque"))
        self.assertEqual(collector.walk_root(root), [])
        row = collector.node_types[base + 123]
        self.assertFalse(row["text_label_fields_proven"])
        self.assertEqual(row["examples"][0]["path"], "menu_option")

    def test_type_and_example_budgets_keep_unknowns_opaque(self):
        collector = Collector(Mock(), 0x1000, options())
        collector.record_node_type(1, 0x1234, "a")
        collector.record_node_type(2, 0x1234, "b")
        collector.record_node_type(3, 0x5678, "c")
        collector.record_node_type(4, 0x9ABC, "d")
        self.assertEqual(len(collector.node_types), 2)
        self.assertEqual(collector.node_types[0x1234]["occurrences"], 2)
        self.assertEqual(len(collector.node_types[0x1234]["examples"]), 1)
        self.assertTrue(collector.errors)
        collector.record_node_type(6, 0xABCD, "f")
        self.assertEqual(len(collector.errors), 1)
        self.assertEqual(collector.node_inventory_omitted_visits, 2)
        collector.record_node_type(5, 0x1234, "e")
        self.assertEqual(collector.node_types[0x1234]["occurrences"], 3)

    def test_inventory_off_and_known_type_contract(self):
        collector = Collector(Mock(), 0x1000, options(include_node_inventory=False))
        collector.record_node_type(1, 0x1234, "a")
        self.assertFalse(collector.node_types)
        collector.args.include_node_inventory = True
        collector.record_node_type(2, 0x1000 + LABEL_VTABLE_RVA, "known")
        self.assertTrue(collector.node_types[0x1000 + LABEL_VTABLE_RVA]["text_label_fields_proven"])
