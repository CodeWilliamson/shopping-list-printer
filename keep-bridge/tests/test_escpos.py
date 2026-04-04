from __future__ import annotations

import unittest

from src.escpos import build_escpos_output, build_escpos_payload
from src.grocery_grouping import GrocerySection


class EscPosTests(unittest.TestCase):
    def test_payload_contains_title_and_items(self) -> None:
        payload = build_escpos_payload("Shopping List", ["Milk", "Eggs"])

        self.assertIn(b"Shopping List", payload)
        self.assertIn(b"- Milk\n", payload)
        self.assertIn(b"- Eggs\n", payload)
        self.assertEqual(list(payload), build_escpos_output("Shopping List", ["Milk", "Eggs"]))

    def test_payload_renders_empty_marker(self) -> None:
        payload = build_escpos_payload("Shopping List", [])

        self.assertIn(b"(empty)\n", payload)

    def test_payload_renders_grouped_sections(self) -> None:
        payload = build_escpos_payload(
            "Shopping List",
            ["Milk", "Eggs", "Bread"],
            grouped_sections=[
                GrocerySection(title="Dairy", items=["Milk", "Eggs"]),
                GrocerySection(title="Bakery", items=["Bread"]),
            ],
        )

        self.assertIn(b"Dairy\n", payload)
        self.assertIn(b"Bakery\n", payload)
        self.assertIn(b"- Milk\n", payload)
        self.assertIn(b"- Eggs\n", payload)
        self.assertIn(b"- Bread\n", payload)


if __name__ == "__main__":
    unittest.main()