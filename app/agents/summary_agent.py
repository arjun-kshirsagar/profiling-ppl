import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class SummaryResult(BaseModel):
    profile_summary: str = Field(
        description=(
            "A cohesive, professional summary of the candidate "
            "based on all provided sources and structured data."
        )
    )


class SummaryAgent(BaseAgent):
    """
    Agent responsible for combining multiple data sources and structured information
    into a cohesive profile summary.
    """

    def __init__(self, provider: str = "gemini", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=20)

    async def generate_summary(
        self,
        name: str,
        sources: List[Dict[str, Any]],
        structured_data: List[Dict[str, Any]],
        is_ambiguous: bool = False,
    ) -> SummaryResult:
        """
        Synthesizes a cohesive professional summary from collected sources and data.
        """
        system_prompt = (
            "You are an expert Talent Intelligence Analyst bridging the gap between raw data and human insight. "
            "Your objective is to combine information from multiple sources and structured extraction results "
            "into a single, unified, highly readable profile summary of a professional."
            "\n\nRules:\n"
            "1. Focus on their current role, past experience, key skills, and major achievements.\n"
            "2. Note the main platforms they are active on (e.g., 'Appears in LinkedIn, GitHub...').\n"
            "3. Do not invent information. If something is not in the input data, do not mention it.\n"
            "4. Keep it concise but comprehensive, typically 3-5 sentences."
        )

        if is_ambiguous:
            system_prompt += (
                "\n\nCRITICAL: The search results for this name are AMBIGUOUS and likely represent multiple people. "
                "YOUR SUMMARY MUST CLEARLY DISTINGUISH BETWEEN THESE IDENTITIES. "
                "Do NOT merge them. Example: 'There are two people with this name: an Architect vs a Sales Manager.'"
            )

        user_prompt = (
            f"Candidate Name: {name}\n\n"
            f"Sources Context:\n{json.dumps(sources, indent=2)}\n\n"
            f"Structured Data Context:\n{json.dumps(structured_data, indent=2)}"
        )

        logger.info(f"Running SummaryAgent for {name}")
        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=SummaryResult,
            )
            return result
        except Exception as e:
            logger.error(f"SummaryAgent failed for {name}: {e}")
            return SummaryResult(
                profile_summary=f"Automated summary generation failed for {name}."
            )
