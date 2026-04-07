from __future__ import annotations
from typing import Any


class OpenAIStructuredClient:
    """Generic OpenAI caller. Returns raw text or None on failure."""

    def __init__(
        self,
        api_key: str,
        model: str,
        request_timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, timeout=request_timeout_seconds)
        else:
            self._client = client
        self._model = model

    def call(self, prompt: str) -> str | None:
        try:
            response = self._client.responses.create(
                model=self._model,
                input=prompt,
            )
            return self._extract_text(response)
        except Exception as e:
            print(f"OpenAIStructuredClient error: {e}")
            return None

    def _extract_text(self, response: Any) -> str | None:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        chunks: list[str] = []
        for part in getattr(response, "output", None) or []:
            for c in getattr(part, "content", None) or []:
                text = getattr(c, "text", None)
                if isinstance(text, str):
                    chunks.append(text)

        result = "\n".join(chunks).strip()
        return result if result else None