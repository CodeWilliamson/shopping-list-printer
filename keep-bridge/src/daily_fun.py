from dataclasses import dataclass
import string

from src.ai_client import OpenAIStructuredClient
from src.config import OpenAIConfig, GroceryGroupingConfig

@dataclass(frozen=True)
class DailyFunSection:
    section: str
    content: str
    
class DailyFun:
    def __init__(self, ai_client: OpenAIStructuredClient) -> None:
        self._ai_client = ai_client

    def generate_daily_fun(self) -> list[DailyFunSection] | None:
        prompt = (
            'Return ONLY a valid JSON array. No text before or after. Use only ASCII characters.\n\n'
            'Format:\n'
            '[{"section":"Joke","content":""},{"section":"Fact","content":""},{"section":"Word of the Day","content":""},{"section":"Math Challenge","content":""}]\n\n'
            'Rules:\n'
            '- Fill all content fields with new content\n'
            '- Short, fun, clean (for age 9)\n'
            '- Word of the Day: include definition + sentence\n'
            '- Math Challenge: make it hard for a grade 3 student, only the question, no answer\n'
        )

        raw = self._ai_client.call(prompt)
        print(f"Raw output from OpenAI: {raw}")

        # return parsed json
        return self.validate_daily_fun(raw)
    
    def validate_daily_fun(self, raw: str) -> list[DailyFunSection] | None:
        # validate that raw is in expected format and return list of DailyFunSection
        # if invalid, return None
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("Failed to parse OpenAI response as JSON")
            return None
        
        if not isinstance(data, list):
            print("OpenAI response JSON is not a list")
            return None
        
        items: list[DailyFunSection] = []
        for item in data:
            if not isinstance(item, dict):
                print("OpenAI response JSON item is not a dict")
                return None
            section = item.get("section")
            content = item.get("content")
            if not isinstance(section, str) or not isinstance(content, str):
                print("OpenAI response JSON item missing 'section' or 'content' as strings")
                return None
            items.append(DailyFunSection(section=section.strip(), content=content.strip()))
        
        return items
    
def create_daily_fun(openaiconfig: OpenAIConfig) -> DailyFun:
    try:
        ai_client = OpenAIStructuredClient(
            api_key=openaiconfig.openai_api_key,
            model=openaiconfig.openai_model,
            request_timeout_seconds=openaiconfig.request_timeout_seconds,
        )
        return DailyFun(ai_client=ai_client)
    except Exception:
        print("Failed to create DailyFun, OpenAI may be unavailable")
        raise