import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger


class ValidSource(BaseModel):
    url: str = Field(description="The URL of the valid profile or result.")
    title: str = Field(description="The title of the search result.")
    snippet: str = Field(description="The snippet text from the search result.")
    identity_match_score: float = Field(
        description=(
            "Score (0.0 to 1.0) indicating how well this source matches the target's "
            "identity (name, company, role)."
        )
    )
    persona_index: Optional[int] = Field(
        None,
        description="Index of the Persona this source belongs to (if multiple personas found).",
    )
    source_type: str = Field(
        description=(
            "The platform or type of source (e.g., 'github_profile', 'youtube_video', "
            "'linkedin_profile', 'personal_blog', 'news_article', 'other')."
        )
    )
    reason: str = Field(
        description=(
            "Brief explanation of why this source is valid and belongs to the target. "
            "Specifically mention name, company, or role matches."
        )
    )


class Persona(BaseModel):
    name: str = Field(description="The name identified for this persona.")
    company: Optional[str] = Field(
        None, description="The current or main company associated with this persona."
    )
    role: Optional[str] = Field(
        None, description="The role or designation of this persona."
    )
    location: Optional[str] = Field(
        None, description="The location associated with this persona."
    )
    description: str = Field(
        description="A brief description of this persona to help the user distinguish them."
    )
    associated_urls: List[str] = Field(
        description="List of URLs that likely belong to this specific persona."
    )
    overall_match_score: float = Field(
        0.0,
        description="Score (0.0 to 1.0) of how well this persona matches the target input.",
    )


class IdentityResolutionResult(BaseModel):
    valid_sources: List[ValidSource] = Field(
        description="List of verified and highly confident URLs belonging to the target person."
    )
    needs_disambiguation: bool = Field(
        default=False,
        description=(
            "Set to true if multiple plausible but conflicting identities (e.g., different "
            "people with same name) were found."
        ),
    )
    found_personas: List[Persona] = Field(
        default_factory=list,
        description="If needs_disambiguation is true, list the distinct personas discovered.",
    )
    disambiguation_reason: Optional[str] = Field(
        None,
        description=(
            "Reason why disambiguation is needed (e.g., 'Found two engineers with same "
            "name at Different Company A and B')."
        ),
    )


class IdentityAgent(BaseAgent):
    """
    Agent responsible for analyzing generic search results and extracting
    the valid URLs that actually belong to the target person.
    """

    def __init__(self, provider: str = "gemini", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=40)

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
        You are an OSINT analyst. Identify which search results belong to the target person.

        **STRICT IDENTITY VALIDATION**:
        - Use ALL provided metadata (Name, Company, Designation, Location) to filter results.
        - If a 'designation' is provided, REJECT results that significantly contradict it
          (e.g., 'Architect' vs 'Sales Manager' or 'Student').
        - Treat designation mismatch as a hard negative signal, not a minor weakness.
        - Be highly cautious of common names.

        **CRITICAL: Disambiguation**
        If you see multiple people with the same name (even at the same company) and the target is ambiguous, YOU MUST:
        1. Set `needs_disambiguation` to true.
        2. Group results into distinct `Persona` objects.
        3. For each `Persona`, calculate an `overall_match_score` (0.0 to 1.0) based on how well they match input.
           - **CRITICAL SCORING RULE**: If a `designation` is provided in the input, a persona matching that
             designation must receive a high score (e.g., 0.9+).
           - A persona whose existing role/designation contradicts the target designation MUST receive a
             drastically lower score (e.g., < 0.25), even if the name and company match.
           - Exact role contradiction outweighs URL overlap, company overlap, and generic seniority signals.
           - Do not give two conflicting personas similar scores if only one matches the requested designation.
        4. Link each `valid_source` to its corresponding `persona_index`.
        5. Explain the ambiguity in `disambiguation_reason`.

        **Rules**:
        - `identity_match_score`: 1.0 for exact URL match or very strong name/company/role match.
        - `source_type`: linkedin, github, youtube, news, blog, other.
        - Only include highly likely matches in `valid_sources`.
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
            designation = target_person.get("designation")
            if designation and result.found_personas:
                result = self._apply_designation_penalty(result, designation)
            return result
        except Exception as e:
            logger.error(f"IdentityAgent failed for {name}: {e}")
            return IdentityResolutionResult(valid_sources=[])

    @classmethod
    def _apply_designation_penalty(
        cls, result: IdentityResolutionResult, designation: str
    ) -> IdentityResolutionResult:
        target_tokens = cls._role_tokens(designation)
        if not target_tokens:
            return result

        updated_personas: List[Persona] = []
        for persona in result.found_personas:
            alignment = cls._designation_alignment(persona.role, target_tokens)
            adjusted_score = persona.overall_match_score

            if alignment == "match":
                adjusted_score = max(adjusted_score, 0.9)
            elif alignment == "contradiction":
                adjusted_score = min(adjusted_score, 0.2)
            elif alignment == "weak":
                adjusted_score = min(adjusted_score, 0.55)

            updated_personas.append(
                persona.model_copy(update={"overall_match_score": adjusted_score})
            )

        return result.model_copy(update={"found_personas": updated_personas})

    @staticmethod
    def _designation_alignment(
        persona_role: Optional[str], target_tokens: set[str]
    ) -> str:
        role_tokens = IdentityAgent._role_tokens(persona_role)
        if not role_tokens:
            return "unknown"

        overlap = role_tokens & target_tokens
        if overlap:
            return "match"

        seniority_only = {
            "senior",
            "lead",
            "principal",
            "staff",
            "head",
            "manager",
            "director",
            "vp",
            "vice",
            "president",
            "chief",
            "associate",
            "junior",
        }
        non_generic_tokens = role_tokens - seniority_only
        if non_generic_tokens:
            return "contradiction"

        return "weak"

    @staticmethod
    def _role_tokens(value: Optional[str]) -> set[str]:
        if not value:
            return set()

        stop_words = {
            "and",
            "or",
            "of",
            "at",
            "the",
            "a",
            "an",
            "to",
            "for",
        }
        tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", value.lower())
            if len(token) > 1 and token not in stop_words
        }
        return tokens
