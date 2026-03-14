import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class FollowUpResult(BaseModel):
    questions: List[str] = Field(
        description="List of 1-to-3 multiple choice questions to disambiguate the candidate."
    )


class FollowUpAgent(BaseAgent):
    """
    Agent responsible for generating clarifying questions when the system cannot confidently
    identify a candidate from the search results.
    """

    def __init__(self, provider: str = "gemini", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=15)

    async def generate_questions(
        self, name: str, search_context: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Takes raw search results and generates follow-up disambiguation questions.
        """
        system_prompt = (
            "You are an expert recruiter. You tried to search for a candidate but found multiple people "
            "with the same name or couldn't confidently identify them based on the search snippets. "
            "Your task is to generate 1 to 3 targeted multiple-choice follow-up questions "
            "to ask the user in order to disambiguate the candidate.\n"
            "Focus on distinguishing factors like company, city, or specific technical skills.\n"
            "Rules:\n"
            "1. Return only the questions formatted nicely with multiple choice options.\n"
            "2. Ensure options are derived from the raw search results if multiple persons exist.\n"
            "3. If no clues exist, generic questions like asking for current company are fine."
        )

        user_prompt = (
            f"Candidate Name: {name}\n"
            f"Search Results Context:\n{json.dumps(search_context[:5], indent=2)}"
        )

        logger.info(f"Running FollowUpAgent for {name}")
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=FollowUpResult,
            )
            return result.questions
        except Exception as e:
            logger.error(f"FollowUpAgent failed for {name}: {e}")
            return [
                f"Multiple people found for {name}. Could you please confirm their current company?",
            ]
