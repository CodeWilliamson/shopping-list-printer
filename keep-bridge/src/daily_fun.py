from dataclasses import dataclass
import string

from src.ai_client import OpenAIStructuredClient
from src.config import DailyFunConfig, OpenAIConfig

@dataclass(frozen=True)
class DailyFunSection:
    section: str
    content: str
    
class DailyFun:
    def __init__(self, ai_client: OpenAIStructuredClient, daily_fun_config: DailyFunConfig) -> None:
        self._ai_client = ai_client
        self._daily_fun_config = daily_fun_config

    def email_riddle_answer(self, riddle: str, answer: str) -> None:
        import smtplib
        from email.mime.text import MIMEText
        smtp_host = self._daily_fun_config.smtp_host
        smtp_port = self._daily_fun_config.smtp_port
        smtp_user = self._daily_fun_config.smtp_user
        smtp_password = self._daily_fun_config.smtp_password
        from_addr = self._daily_fun_config.smtp_from_addr
        to_addr = self._daily_fun_config.smtp_to_addr
        subject = "Your Daily Riddle Answer"
        body = f"Riddle: {riddle}\nAnswer: {answer}"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to_addr
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
            print(f"[DailyFun] Riddle answer emailed to {to_addr}")
        except Exception as e:
            print(f"[DailyFun] Failed to send riddle answer email: {e}")
    
    def fetch_random_joke(self) -> str | None:
        import requests
        url = "https://teehee.dev/api/joke"
        try:
            print("[DailyFun] Fetching random joke from API...")
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("question") or not data.get("answer"):
                print("[DailyFun] API returned empty joke")
                return None
            return data
        except Exception as e:
            print(f"[DailyFun] Failed to fetch random joke: {e}")
            return None
    
    def fetch_daily_quote(self) -> str | None:
        import requests
        url = "https://zenquotes.io/api/today"
        try:
            print("[DailyFun] Fetching daily quote from API...")
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            # data is expected to be a list of dicts with keys 'q', 'a', 'h'
            if not isinstance(data, list) or not data:
                print("[DailyFun] API returned non-list or empty list for quote")
                return None
            quote_obj = data[0]
            quote = quote_obj.get("q")
            author = quote_obj.get("a")
            if not quote or not author:
                print("[DailyFun] API returned quote missing 'q' or 'a'")
                return None
            return quote_obj
        except Exception as e:
            print(f"[DailyFun] Failed to fetch daily quote: {e}")
            return None
    
    def fetch_daily_fact(self) -> str | None:
        import requests
        url = "https://uselessfacts.jsph.pl/api/v2/facts/today"
        try:
            print("[DailyFun] Fetching daily fact from API...")
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            fact = data.get("text")
            if not fact:
                print("[DailyFun] API returned empty fact")
                return None
            return fact
        except Exception as e:
            print(f"[DailyFun] Failed to fetch daily fact: {e}")
            return None
    
    def fetch_random_riddle(self) -> str | None:
        import requests
        url = "https://api.apileague.com/retrieve-random-riddle?difficulty=easy"
        try:
            print("[DailyFun] Fetching daily riddle from API...")
            headers = {"x-api-key": self._daily_fun_config.apileague_api_key}
            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            riddle = data.get("riddle")
            answer = data.get("answer")
            if not riddle or not answer:
                print("[DailyFun] API returned riddle missing 'riddle' or 'answer'")
                return None
            # Email the answer
            self.email_riddle_answer(riddle, answer)
            return f"{riddle}"
        except Exception as e:
            print(f"[DailyFun] Failed to fetch daily riddle: {e}")
            return None

    def generate_daily_fun(self) -> list[DailyFunSection] | None:
        # initialize daily_fun array
        daily_fun: list[DailyFunSection] = []
        joke_data = self.fetch_random_joke()
        if isinstance(joke_data, dict) and "question" in joke_data and "answer" in joke_data:
            joke = f"{joke_data['question']}\n{joke_data['answer']}"
        else:
            joke = "No joke available today."

        quote = self.fetch_daily_quote() or "No quote available today."
        if isinstance(quote, dict) and "q" in quote and "a" in quote:
            quote = f'"{quote["q"]}" - {quote["a"]}'
        else:            
            quote = "No quote available today."

        fact = self.fetch_daily_fact() or "No fact available today."
        if isinstance(fact, str):
            fact = fact.strip()
        else:            
            fact = "No fact available today."

        riddle = self.fetch_random_riddle() or "No riddle available today."
        if isinstance(riddle, str):
            riddle = riddle.strip()
        else:
            riddle = "No riddle available today."

        # prompt = (
        #     'Return ONLY a valid JSON array. No text before or after. Use only ASCII characters.\n\n'
        #     'Format:\n'
        #     '[{"section":"Joke","content":""},{"section":"Fact","content":""},{"section":"Word of the Day","content":""},{"section":"Math Challenge","content":""}]\n\n'
        #     'Rules:\n'
        #     '- Fill all content fields with new content\n'
        #     '- Short, fun, clean (for age 9)\n'
        #     '- Word of the Day: include definition + sentence\n'
        #     '- Math Challenge: make it hard for a grade 3 student, only the question, no answer\n'
        # )

        # raw = self._ai_client.call(prompt)
        # print(f"Raw output from OpenAI: {raw}")

        # return parsed json
        # parsed = self.validate_daily_fun(raw)
        # add joke and quote as separate sections
        daily_fun.insert(0, DailyFunSection(section="Joke", content=joke))
        daily_fun.insert(1, DailyFunSection(section="Quote", content=quote))
        daily_fun.insert(2, DailyFunSection(section="Fun Fact", content=fact))
        daily_fun.insert(3, DailyFunSection(section="Riddle", content=riddle))
        return daily_fun
    
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
    
def create_daily_fun(openaiconfig: OpenAIConfig, daily_fun_config: DailyFunConfig) -> DailyFun:
    try:
        ai_client = OpenAIStructuredClient(
            api_key=openaiconfig.openai_api_key,
            model=openaiconfig.openai_model,
            request_timeout_seconds=openaiconfig.request_timeout_seconds,
        )
        return DailyFun(ai_client=ai_client, daily_fun_config=daily_fun_config)
    except Exception:
        print("Failed to create DailyFun, OpenAI may be unavailable")
        raise