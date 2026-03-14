from groq import Groq

from app.config import get_settings
from app.llm.base import BaseLLM

settings = get_settings()


class GroqClient(BaseLLM):
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        completion = self.client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""
