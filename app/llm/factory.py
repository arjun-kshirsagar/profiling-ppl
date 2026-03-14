from app.llm.base import BaseLLM
from app.llm.claude_client import ClaudeClient
from app.llm.gemini_client import GeminiClient
from app.llm.groq_client import GroqClient
from app.llm.openai_client import OpenAIClient


def get_llm(provider: str, **kwargs) -> BaseLLM:
    if provider == "openai":
        return OpenAIClient(api_key=kwargs["api_key"])
    elif provider == "claude":
        return ClaudeClient(api_key=kwargs["api_key"])
    elif provider == "gemini":
        return GeminiClient(
            project=kwargs["project"],
            location=kwargs["location"],
            model=kwargs.get("model", "gemini-2.5-flash"),
        )
    elif provider == "groq":
        return GroqClient(api_key=kwargs["api_key"])
    else:
        raise ValueError(f"Unsupported provider: {provider}")
