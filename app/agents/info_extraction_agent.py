from typing import List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class ExtractionResult(BaseModel):
    role: Optional[str] = Field(
        description="The primary current role or job title of the person."
    )
    company: Optional[str] = Field(
        description="The primary current company the person works at."
    )
    previous_companies: List[str] = Field(
        description="A list of previous companies the person has worked at."
    )
    topics: List[str] = Field(
        description="A list of topics, skills, or domains the person is associated with."
    )
    type: str = Field(
        description=(
            "The type of the source page, e.g., 'linkedin_profile', "
            "'github_profile', 'news_article', 'personal_blog'."
        )
    )
    achievements: List[str] = Field(
        description="A list of notable achievements, awards, or speaking engagements."
    )


class InfoExtractionAgent(BaseAgent):
    """
    Agent responsible for extracting structured signals (role, company, topics, achievements)
    from raw, unstructured text parsed from a web page.
    """

    def __init__(self, provider: str = "groq", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=20)

    async def extract_info(
        self,
        text: str,
        target_name: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Parses raw text and extracts structured information about a person.
        """
        system_prompt = """
        You are an expert Data Extraction AI.

        Your goal is to extract structured professional signals
        from raw, messy text parsed from web pages.

        Rules:
        1. Identify the current role and company of the person described in the text.
        2. Identify any previous companies they have worked at.
        3. Extract key topics, skills, or industries they are associated with.
        4. Extract concrete achievements, such as awards received, projects built,
        or conferences spoken at.
        5. Determine the likely type of the source page
        (e.g., 'linkedin_profile', 'news_article', 'personal_blog').
        6. If a specific piece of information is not present in the text,
        return null or an empty list. Do not hallucinate.
        """

        user_prompt_lines = []
        if target_name:
            user_prompt_lines.append(f"Target Person (if applicable): {target_name}")

        user_prompt_lines.append("Raw Page Text:")
        user_prompt_lines.append(f'"""\n{text}\n"""')

        user_prompt = "\n\n".join(user_prompt_lines)

        logger.info(f"Running InfoExtractionAgent for name='{target_name}'")
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ExtractionResult,
            )
            return result
        except Exception as e:
            logger.error(f"InfoExtractionAgent failed: {e}")
            return ExtractionResult(
                role=None,
                company=None,
                previous_companies=[],
                topics=[],
                type="unknown",
                achievements=[],
            )
