from __future__ import annotations

import json
import unittest

from src.grocery_grouping import OpenAIGrocerySectionGrouper


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponsesApi:
    def __init__(self, output_text: str | None = None, should_raise: bool = False) -> None:
        self._output_text = output_text
        self._should_raise = should_raise

    def create(self, model: str, input: str):
        del model
        del input
        if self._should_raise:
            raise RuntimeError("OpenAI unavailable")
        return _FakeResponse(self._output_text or "")


class _FakeOpenAiClient:
    def __init__(self, output_text: str | None = None, should_raise: bool = False) -> None:
        self.responses = _FakeResponsesApi(output_text=output_text, should_raise=should_raise)


class GroceryGroupingTests(unittest.TestCase):
    def test_grouping_returns_sections_for_valid_json(self) -> None:
        payload = {
            "sections": [
                {"title": "Dairy", "items": ["Milk", "Eggs"]},
                {"title": "Bakery", "items": ["Bread"]},
            ]
        }
        client = _FakeOpenAiClient(output_text=json.dumps(payload))
        grouper = OpenAIGrocerySectionGrouper(
            api_key="test",
            model="gpt-4.1-mini",
            store_context="No Frills and Metro in Ontario, Canada",
            request_timeout_seconds=12,
            client=client,
        )

        sections = grouper.group_items("Shopping List", ["Milk", "Eggs", "Bread"])

        self.assertIsNotNone(sections)
        self.assertEqual("Dairy", sections[0].title)
        self.assertEqual(["Milk", "Eggs"], sections[0].items)
        self.assertEqual("Bakery", sections[1].title)
        self.assertEqual(["Bread"], sections[1].items)

    def test_grouping_rejects_changed_item_text(self) -> None:
        payload = {
            "sections": [
                {"title": "Dairy", "items": ["2% Milk"]},
            ]
        }
        client = _FakeOpenAiClient(output_text=json.dumps(payload))
        grouper = OpenAIGrocerySectionGrouper(
            api_key="test",
            model="gpt-4.1-mini",
            store_context="No Frills and Metro in Ontario, Canada",
            request_timeout_seconds=12,
            client=client,
        )

        sections = grouper.group_items("Shopping List", ["Milk"])

        self.assertIsNone(sections)

    def test_grouping_returns_none_when_openai_fails(self) -> None:
        client = _FakeOpenAiClient(should_raise=True)
        grouper = OpenAIGrocerySectionGrouper(
            api_key="test",
            model="gpt-4.1-mini",
            store_context="No Frills and Metro in Ontario, Canada",
            request_timeout_seconds=12,
            client=client,
        )

        sections = grouper.group_items("Shopping List", ["Milk"])

        self.assertIsNone(sections)


if __name__ == "__main__":
    unittest.main()
