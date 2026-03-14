from typing import List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class QueryGenerationResult(BaseModel):
    queries: List[str] = Field(
        ...,
        min_items=5,
        max_items=10,
        description=(
            "A list of 5 to 10 highly targeted search queries designed to find "
            "the candidate's professional profiles, talks, code, and mentions."
        ),
    )


class QueryAgent(BaseAgent):
    """
    Agent responsible for generating targeted search queries to discover a candidate's digital footprint.
    """

    def __init__(self, provider: str = "gemini", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=15)

    async def generate_search_queries(
        self,
        name: str,
        company: Optional[str] = None,
        designation: Optional[str] = None,
    ) -> QueryGenerationResult:
        """
        Generates 5-10 optimal search queries based on the candidate's known attributes.
        """
        system_prompt = (
            "You are a talent sourcing expert who excels at boolean searches and "
            "OSINT (Open Source Intelligence). Your objective is to generate highly "
            "targeted search queries to find an individual's digital footprint online. "
            "You want to find their LinkedIn profile, GitHub profile, personal blogs, "
            "talks or interviews on YouTube, and any news or media mentions."
            "\n\nRules:"
            "\n1. Return exactly 5 to 10 distinct queries."
            "\n2. Use combinations of their name, company, and role."
            "\n3. MUST INCLUDE platform-specific queries using 'site:' operator "
            "(e.g., 'site:github.com \"First Last\"', 'site:youtube.com \"First Last\"', "
            "'site:medium.com \"First Last\"', 'site:twitter.com \"First Last\"')."
            "\n4. If the company or designation is missing, focus heavily on their "
            "name and broad tech keywords."
        )

        user_prompt_lines = [f"Name: {name}"]
        if company:
            user_prompt_lines.append(f"Company: {company}")
        if designation:
            user_prompt_lines.append(f"Designation: {designation}")

        user_prompt = "\n".join(user_prompt_lines)

        logger.info(f"Running QueryAgent for candidate: {name}")

        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=QueryGenerationResult,
            )
            return result
        except Exception as e:
            logger.error(f"QueryAgent failed for {name}: {e}")
            # Fallback queries
            fallback = [
                f'site:linkedin.com/in "{name}"',
                f'site:github.com "{name}"',
                f'site:youtube.com "{name}" {company or ""}'.strip(),
                f'site:medium.com "{name}" {designation or ""}'.strip(),
                f'{name} {company or ""} {designation or ""} "interview"'.strip(),
            ]
            # Clean up fallbacks (remove extra spaces if company/designation missing)
            fallback = [" ".join(q.split()) for q in fallback]
            return QueryGenerationResult(queries=fallback)

    async def refine_search_queries(
        self,
        name: str,
        company: Optional[str],
        designation: Optional[str],
        previous_queries: List[str],
        failure_context: str,
    ) -> QueryGenerationResult:
        """
        Generates a new batch of 5-10 distinct search queries based on why the previous ones failed.
        """
        system_prompt = (
            "You are a talent sourcing expert who excels at boolean searches and OSINT. "
            "Your previous search attempts to find the candidate yielded no valid profiles. "
            "You must generate a NEW batch of highly targeted search queries."
            "\n\nRules:"
            "\n1. Do NOT reuse any of the previous queries."
            "\n2. Return exactly 5 to 10 distinct queries."
            "\n3. Try alternative approaches: use nicknames, broader tech terms, drop the company/designation, "
            "or focus on specific platforms like GitHub, Meetup, Medium, or technical conferences."
        )

        user_prompt_lines = [f"Name: {name}"]
        if company:
            user_prompt_lines.append(f"Company: {company}")
        if designation:
            user_prompt_lines.append(f"Designation: {designation}")

        user_prompt_lines.append(
            f"\nPrevious Queries that Failed:\n{'- ' + chr(10) + '- '.join(previous_queries)}"
        )
        user_prompt_lines.append(f"\nFailure Context:\n{failure_context}")

        user_prompt = "\n".join(user_prompt_lines)
        logger.info(f"Refining search queries for candidate: {name}")

        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=QueryGenerationResult,
            )
            return result
        except Exception as e:
            logger.error(f"QueryAgent refinement failed for {name}: {e}")
            fallback = [
                f"{name} developer",
                f"{name} engineer",
                f"{name} tech",
                f"{name} portfolio",
                f"{name} {company or ''}",
            ]
            fallback = [" ".join(q.split()) for q in fallback]
            return QueryGenerationResult(queries=fallback)
