from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from src.ai_client import OpenAIStructuredClient
from src.config import OpenAIConfig, GroceryGroupingConfig


@dataclass(frozen=True)
class GrocerySection:
    title: str
    items: list[str]


class GrocerySectionGrouper(Protocol):
    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        ...


class GroceryGroupingTask:
    """Knows how to prompt and validate grocery grouping — nothing else."""

    def __init__(self, store_context: str) -> None:
        self._store_context = store_context

    def _build_prompt(self, list_title: str, items: list[str]) -> str:
        items_block = "\n".join(f"- {item}" for item in items)
        return (
            "You are organizing a shopping list for grocery stores in Ontario, Canada. "
            f"Typical stores: {self._store_context}.\n"
            "Return only JSON with this shape, NO EXTRA CHARACTERS before or after the JSON. Your output must parse when run through a JSON parser: "
            '{"sections":[{"title":"Produce","items":["Milk"]}]}.\n'
            "Rules:\n"
            "1) Keep each item text exactly as provided. Do not rename or normalize items.\n"
            "2) Every input item must appear exactly once across all sections.\n"
            "3) Do not invent new items.\n"
            "4) Section titles should be short and practical for in-store navigation."
            "Try to stay to these groupings: Produce,Meat & Poultry,Seafood,Dairy & Eggs,Bakery,Deli,Prepared Foods,Frozen Foods,Pantry,Beverages,Beer & Wine,Household Supplies,Health & Beauty,Seasonal / General Merchandise\n"
            "5) Prefer ordering sections in likely walking order through a grocery store.\n"
            f"List title: {list_title}\n"
            "Items:\n"
            f"{items_block}\n"
        )

    def validate(self, items: list[str], raw: str) -> list[GrocerySection] | None:
        try:
            payload = json.loads(raw)
        except Exception as e:
            print(f"Failed to parse OpenAI response as JSON: {e}")
            return None

        if not isinstance(payload, dict):
            return None

        raw_sections = payload.get("sections")
        if not isinstance(raw_sections, list):
            return None

        remaining = Counter(items)
        sections: list[GrocerySection] = []

        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                return None
            title = raw_section.get("title", "Other")
            raw_items = raw_section.get("items")
            if not isinstance(raw_items, list):
                return None
            if not isinstance(title, str) or not title.strip():
                title = "Other"

            section_items: list[str] = []
            for item in raw_items:
                if not isinstance(item, str) or remaining[item] <= 0:
                    return None
                remaining[item] -= 1
                section_items.append(item)

            if section_items:
                sections.append(GrocerySection(title=title.strip(), items=section_items))

        if any(count != 0 for count in remaining.values()) or not sections:
            return None

        return sections


class OpenAIGrocerySectionGrouper:
    def __init__(self, client: OpenAIStructuredClient, task: GroceryGroupingTask) -> None:
        self._client = client
        self._task = task

    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        if not items:
            return []
        prompt = self._task._build_prompt(list_title, items)
        raw = self._client.call(prompt)
        # log raw output here
        print(f"Raw output from OpenAI: {raw}")
        if not raw:
            return None
        return self._task.validate(items, raw)


class NoopGrocerySectionGrouper:
    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        return None


def create_grocery_section_grouper(openaiconfig: OpenAIConfig, groupingconfig: GroceryGroupingConfig) -> GrocerySectionGrouper:
    if not groupingconfig.enabled or not openaiconfig.openai_api_key:
        return NoopGrocerySectionGrouper()
    try:
        ai_client = OpenAIStructuredClient(
            api_key=openaiconfig.openai_api_key,
            model=openaiconfig.openai_model,
            request_timeout_seconds=openaiconfig.request_timeout_seconds,
        )
        task = GroceryGroupingTask(store_context=groupingconfig.store_context)
        return OpenAIGrocerySectionGrouper(client=ai_client, task=task)
    except Exception:
        return NoopGrocerySectionGrouper()