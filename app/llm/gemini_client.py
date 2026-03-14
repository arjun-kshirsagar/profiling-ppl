from google import genai

from app.llm.base import BaseLLM


class GeminiClient(BaseLLM):
    def __init__(self, project: str, location: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"{system_prompt}\n\n{user_prompt}",
        )
        return response.text
