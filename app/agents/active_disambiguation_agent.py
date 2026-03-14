import asyncio
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.identity_resolution_agent import Persona
from app.logger import logger
from app.services.search_service import SearchResult, SearchService


class PersonaEvidence(BaseModel):
    persona_index: int
    persona_name: str
    persona_company: Optional[str] = None
    persona_role: Optional[str] = None
    persona_urls: List[str] = Field(default_factory=list)
    targeted_queries: List[str] = Field(default_factory=list)
    search_results: List[Dict[str, str]] = Field(default_factory=list)


class DisambiguationResult(BaseModel):
    conclusive_match: bool = Field(
        description="True if the evidence conclusively points to one specific persona."
    )
    best_persona_index: Optional[int] = Field(
        None,
        description="The index of the winning Persona from the provided list, if conclusive.",
    )
    reasoning: str = Field(
        description=(
            "Explanation of exactly what evidence led to this conclusion or why it remains ambiguous."
        )
    )


class ActiveDisambiguationAgent(BaseAgent):
    """
    Actively searches for evidence that links a specific ambiguous persona to the
    requested company and designation, then uses an LLM to make a final selection.
    """

    def __init__(self, provider: str = "gemini", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=60)
        self.search_service = SearchService()

    async def verify_identity(
        self, target_person: Dict[str, Any], personas: List[Persona]
    ) -> DisambiguationResult:
        if len(personas) < 2:
            return DisambiguationResult(
                conclusive_match=False,
                reasoning="Not enough personas were supplied for active disambiguation.",
            )

        name = target_person.get("name", "")
        logger.info("Running ActiveDisambiguationAgent for %s", name)

        persona_queries = [
            (index, self._build_targeted_queries(target_person, persona))
            for index, persona in enumerate(personas)
        ]
        search_tasks = [
            self.search_service.search_web(query=query, max_results=3)
            for _, queries in persona_queries
            for query in queries
        ]

        logger.info(
            "Active disambiguation firing %d targeted queries across %d personas.",
            len(search_tasks),
            len(personas),
        )
        raw_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        persona_evidence: List[PersonaEvidence] = []
        result_cursor = 0
        for persona_index, queries in persona_queries:
            persona = personas[persona_index]
            aggregated_results: List[Dict[str, str]] = []
            seen_urls = set()

            for query in queries:
                query_results = raw_results[result_cursor]
                result_cursor += 1

                if isinstance(query_results, Exception):
                    logger.warning(
                        "Active disambiguation query failed for persona %s: %s",
                        persona_index,
                        query_results,
                    )
                    continue

                for item in query_results:
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)
                    aggregated_results.append(
                        self._serialize_search_result(query=query, result=item)
                    )

            persona_evidence.append(
                PersonaEvidence(
                    persona_index=persona_index,
                    persona_name=persona.name,
                    persona_company=persona.company,
                    persona_role=persona.role,
                    persona_urls=persona.associated_urls,
                    targeted_queries=queries,
                    search_results=aggregated_results,
                )
            )

        system_prompt = """
        You are an OSINT identity verification expert.

        You will receive a target person and multiple ambiguous personas. Each persona has targeted search evidence
        gathered from queries designed to prove or disprove that persona's connection to the requested company
        and designation.

        Decision rules:
        - Prefer explicit evidence that links a persona URL, title, or snippet to the target designation.
        - If the target designation is "Architect", evidence showing "Architect" or a clearly equivalent role
          for one persona and a conflicting role like "Sales", "Account Manager", or "Student" for another
          should be treated as conclusive.
        - Do not choose a persona just because the name and company match if the role contradicts the
          requested designation.
        - Set `conclusive_match` to false when the evidence is weak, indirect, or evenly split.
        - Only return `best_persona_index` when one persona clearly has the strongest evidence.
        """

        user_prompt = (
            f"Target Person:\n{json.dumps(target_person, indent=2)}\n\n"
            f"Personas and Evidence:\n"
            f"{json.dumps([item.model_dump() for item in persona_evidence], indent=2)}"
        )

        try:
            return await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=DisambiguationResult,
            )
        except Exception as exc:
            logger.error("ActiveDisambiguationAgent failed for %s: %s", name, exc)
            return DisambiguationResult(
                conclusive_match=False,
                reasoning=f"Active disambiguation failed: {exc}",
            )

    def _build_targeted_queries(
        self, target_person: Dict[str, Any], persona: Persona
    ) -> List[str]:
        name = target_person.get("name", "").strip()
        company = target_person.get("company", "").strip()
        designation = target_person.get("designation", "").strip()
        persona_role = (persona.role or "").strip()

        candidates = [
            f'"{name}" "{company}" "{designation}"',
            f'"{name}" "{designation}"',
        ]

        if persona_role:
            candidates.append(f'"{name}" "{company}" "{persona_role}" "{designation}"')
            candidates.append(f'"{name}" "{persona_role}" "{designation}"')

        for url in persona.associated_urls[:2]:
            candidates.append(f'"{url}" "{company}" "{designation}"')
            candidates.append(f'"{url}" "{designation}"')

        deduped: List[str] = []
        seen = set()
        for query in candidates:
            normalized = " ".join(query.split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return deduped[:5]

    @staticmethod
    def _serialize_search_result(query: str, result: SearchResult) -> Dict[str, str]:
        return {
            "query": query,
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet,
            "source": result.source,
        }
