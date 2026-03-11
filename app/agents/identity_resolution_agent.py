import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class ValidSource(BaseModel):
    url: str = Field(description="The URL of the valid profile or result.")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0.")
    reason: str = Field(
        description="Brief explanation of why this source is valid and belongs to the target."
    )


class IdentityResolutionResult(BaseModel):
    valid_sources: List[ValidSource] = Field(
        description="List of verified and highly confident URLs belonging to the target person."
    )


class IdentityAgent(BaseAgent):
    """
    Agent responsible for analyzing generic search results and extracting
    the valid URLs that actually belong to the target person.
    """

    def __init__(self, provider: str = "groq", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=20)

    async def resolve_identity(
        self,
        target_person: Dict[str, Any],
        search_results: List[Dict[str, Any]],
    ) -> IdentityResolutionResult:
        """
        Analyzes search results to filter out the irrelevant ones and keep only those
        belonging to the target person.
        """

        system_prompt = """
        You are an expert open-source intelligence (OSINT) analyst.
        Your job is to identify which search results actually belong to a specific
        target person. You will be given the target person's known details and a
        list of search results.

        Rules:
        1. Be selective but reasonable. Include a result if it's highly likely to
        be the target based on name, role, or context.
        2. Reject profiles that explicitly state a different company or totally
        unrelated role.
        3. If a result mentions the target's name and related keywords (like
        logistics, engineering) it is likely valid.
        4. Pay special attention to LinkedIn, GitHub, YouTube, and professional
        media mentions.
        5. Provide a confidence score (0.0 to 1.0) and a brief reason for each
        valid source.
        """

        user_prompt = (
            f"Target Person:\n{json.dumps(target_person, indent=2)}\n\n"
            f"Search Results Context:\n{json.dumps(search_results, indent=2)}"
        )

        name = target_person.get("name", "Unknown")
        logger.info(f"Running IdentityAgent for {name}")
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=IdentityResolutionResult,
            )
            return result
        except Exception as e:
            logger.error(f"IdentityAgent failed for {name}: {e}")
            return IdentityResolutionResult(valid_sources=[])
