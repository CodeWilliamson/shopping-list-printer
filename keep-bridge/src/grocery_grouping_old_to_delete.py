from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from src.config import OpenAIConfig


@dataclass(frozen=True)
class GrocerySection:
    title: str
    items: list[str]


class GrocerySectionGrouper(Protocol):
    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        ...


class OpenAIGrocerySectionGrouper:
    def __init__(
        self,
        api_key: str,
        model: str,
        store_context: str,
        request_timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI
            # logging for debugging
            self._client = OpenAI(api_key=api_key, timeout=request_timeout_seconds)
            print(f"OpenAI GrocerySectionGrouper initialized with model: {model}, store_context: {store_context}")
        else:
            self._client = client
        self._model = model
        self._store_context = store_context

    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        if not items:
            return []

        prompt = self._build_prompt(list_title=list_title, items=items)

        # log prompt for debugging
        print(f"OpenAI GrocerySectionGrouper prompt:\n{prompt}\n------")

        try:
            response = self._client.responses.create(
                model=self._model,
                input=prompt,
            )
            output_text = self._extract_output_text(response)
            # log raw output for debugging
            print(f"OpenAI GrocerySectionGrouper raw output:\n{output_text}\n------")
            if not output_text:
                return None
            payload = json.loads(output_text)
            # log parsed payload for debugging
            print(f"OpenAI GrocerySectionGrouper parsed payload:\n{payload}\n------")
        except Exception as e:
            print(f"OpenAI GrocerySectionGrouper error: {e}")
            return None

        return self._validate_sections(items=items, payload=payload)

    def _build_prompt(self, list_title: str, items: list[str]) -> str:
        items_block = "\n".join(f"- {item}" for item in items)
        return (
            "You are organizing a shopping list for grocery stores in Ontario, Canada. "
            f"Typical stores: {self._store_context}.\n"
            "Return only JSON with this shape, NO EXTRA CHARACTERS. Your output must parse when run through a JSON parser: "
            '{"sections":[{"title":"Produce","items":["Milk"]}]}.\n'
            "Rules:\n"
            "1) Keep each item text exactly as provided. Do not rename or normalize items.\n"
            "2) Every input item must appear exactly once across all sections.\n"
            "3) Do not invent new items.\n"
            "4) Section titles should be short and practical for in-store navigation.\n"
            "5) Prefer ordering sections in likely walking order through a grocery store.\n"
            f"List title: {list_title}\n"
            "Items:\n"
            f"{items_block}\n"
        )

    def _extract_output_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output_parts = getattr(response, "output", None)
        if not isinstance(output_parts, list):
            return ""

        chunks: list[str] = []
        for part in output_parts:
            content = getattr(part, "content", None)
            if not isinstance(content, list):
                continue
            for c in content:
                text = getattr(c, "text", None)
                if isinstance(text, str):
                    chunks.append(text)

        return "\n".join(chunks).strip()

    def _validate_sections(self, items: list[str], payload: Any) -> list[GrocerySection] | None:
        if not isinstance(payload, dict):
            return None

        raw_sections = payload.get("sections")
        if not isinstance(raw_sections, list):
            return None

        remaining = Counter(items)
        normalized_sections: list[GrocerySection] = []

        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                return None

            title = raw_section.get("title", "")
            raw_items = raw_section.get("items")
            if not isinstance(raw_items, list):
                return None

            if not isinstance(title, str) or not title.strip():
                title = "Other"

            section_items: list[str] = []
            for item in raw_items:
                if not isinstance(item, str):
                    return None
                if remaining[item] <= 0:
                    return None
                remaining[item] -= 1
                section_items.append(item)

            if section_items:
                normalized_sections.append(GrocerySection(title=title.strip(), items=section_items))

        if any(count != 0 for count in remaining.values()):
            return None

        if not normalized_sections:
            return None

        return normalized_sections


class NoopGrocerySectionGrouper:
    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        return None


def create_grocery_section_grouper(config: OpenAIConfig) -> GrocerySectionGrouper:
    if not config.enabled:
        return NoopGrocerySectionGrouper()

    if not config.openai_api_key:
        return NoopGrocerySectionGrouper()

    try:
        return OpenAIGrocerySectionGrouper(
            api_key=config.openai_api_key,
            model=config.openai_model,
            store_context=config.store_context,
            request_timeout_seconds=config.request_timeout_seconds,
        )
    except Exception:
        return NoopGrocerySectionGrouper()
