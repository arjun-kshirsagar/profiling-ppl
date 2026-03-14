import asyncio
from typing import List, Optional

from app.agents.active_disambiguation_agent import ActiveDisambiguationAgent
from app.agents.follow_up_agent import FollowUpAgent
from app.agents.identity_resolution_agent import IdentityAgent
from app.agents.profile_seed_resolver_agent import ProfileSeedResolverAgent
from app.agents.query_agent import QueryAgent
from app.agents.signal_extraction_agent import SignalExtractionAgent
from app.agents.summary_agent import SummaryAgent
from app.logger import logger
from app.schemas import (
    ComprehensiveProfileResponse,
    FinalSourceData,
    PersonaData,
    PersonData,
)
from app.services.confidence_service import ConfidenceService
from app.services.search_service import SearchService
from app.services.source_normalizer import normalize_source_type


class ProfileResearchAgent:
    """
    Orchestrator Agent that ties together the entire profile research pipeline:
    Query Generation -> Web Search -> Identity Resolution -> Page Fetching ->
    Extraction -> Confidence Scoring -> Summarization
    """

    def __init__(self):
        self.seed_resolver_agent = ProfileSeedResolverAgent()
        self.query_agent = QueryAgent()
        self.search_service = SearchService()
        self.identity_agent = IdentityAgent()
        self.signal_extraction_agent = SignalExtractionAgent()
        self.confidence_service = ConfidenceService()
        self.summary_agent = SummaryAgent()
        self.follow_up_agent = FollowUpAgent()
        self.active_disambiguation_agent = ActiveDisambiguationAgent()

    async def research_profile(
        self,
        name: str,
        company: Optional[str] = None,
        designation: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        max_search_results: int = 15,
    ) -> ComprehensiveProfileResponse:
        """
        Executes the full end-to-end profile research pipeline.
        """
        logger.info(f"Starting ProfileResearchAgent pipeline for {name}")

        person_info = {"name": name}
        if company:
            person_info["company"] = company
        if designation:
            person_info["designation"] = designation
        if linkedin_url:
            person_info["linkedin_url"] = linkedin_url

        all_search_results = []
        follow_up_questions = []
        seed_queries: List[str] = []

        if linkedin_url:
            logger.info(
                f"[Step 0/7] Running ProfileSeedResolverAgent for {linkedin_url}..."
            )
            seed_result = await self.seed_resolver_agent.resolve_from_linkedin_url(
                linkedin_url
            )
            seed_queries = seed_result.seed_queries
            if seed_result.linkedin_slug:
                person_info["linkedin_slug"] = seed_result.linkedin_slug
            if seed_result.name and (
                name == "Unknown Candidate" or seed_result.confidence >= 0.6
            ):
                name = seed_result.name
                person_info["name"] = name
            if not company and seed_result.possible_companies:
                company = seed_result.possible_companies[0]
                person_info["company"] = company
            if not designation and seed_result.possible_roles:
                designation = seed_result.possible_roles[0]
                person_info["designation"] = designation

        max_retries = 2
        queries = []
        valid_sources = []
        found_personas = []
        needs_disambiguation = False
        disambiguation_unresolved = False

        for attempt in range(max_retries):
            # 1. Generate Queries
            if attempt == 0:
                if name == "Unknown Candidate" and seed_queries:
                    logger.info(
                        "[Step 1/7] Using seed queries because the candidate name is unresolved."
                    )
                    queries = seed_queries
                else:
                    logger.info(
                        f"[Step 1/7] Generating search queries (Attempt {attempt+1}/{max_retries})..."
                    )
                    query_result = await self.query_agent.generate_search_queries(
                        name=name, company=company, designation=designation
                    )
                    queries = self._merge_queries(seed_queries, query_result.queries)
            else:
                logger.info(
                    f"[Step 1/7] Refining search queries (Attempt {attempt+1}/{max_retries})..."
                )
                query_result = await self.query_agent.refine_search_queries(
                    name=name,
                    company=company,
                    designation=designation,
                    previous_queries=queries,
                    failure_context="No search results were found that confidently matched the identity profile.",
                )
                queries = self._merge_queries(seed_queries, query_result.queries)

            logger.info(f"Generated {len(queries)} queries.")

            # 2. Search Web across multiple queries (Concurrent)
            logger.info(
                f"[Step 2/7] Searching the web (Attempt {attempt+1}/{max_retries})..."
            )
            search_tasks = [
                self.search_service.search_web(query=q, max_results=5) for q in queries
            ]
            search_results_lists = await asyncio.gather(
                *search_tasks, return_exceptions=True
            )

            # Flatten and deduplicate search results based on URL
            all_search_results = []
            seen_urls = set()
            for res_list in search_results_lists:
                if isinstance(res_list, list):
                    for res in res_list:
                        if res.url not in seen_urls:
                            seen_urls.add(res.url)
                            all_search_results.append(
                                {
                                    "title": res.title,
                                    "url": res.url,
                                    "snippet": res.snippet,
                                    "source": res.source,
                                }
                            )

            # Limit total raw search results to feed into identity agent
            all_search_results = all_search_results[:max_search_results]
            logger.info(f"Aggregated {len(all_search_results)} unique search results.")

            if not all_search_results:
                logger.warning(f"No search results found on attempt {attempt+1}.")
                continue

            # 3. Identity Resolution
            logger.info(
                f"[Step 3/7] Filtering valid sources via Identity Resolution (Attempt {attempt+1}/{max_retries})..."
            )
            identity_result = await self.identity_agent.resolve_identity(
                target_person=person_info, search_results=all_search_results
            )
            valid_sources = identity_result.valid_sources
            found_personas = identity_result.found_personas
            needs_disambiguation = identity_result.needs_disambiguation
            disambiguation_unresolved = False

            logger.info(
                f"Identity Agent identified {len(valid_sources)} valid sources and {len(found_personas)} personas."
            )

            # --- Disambiguation Logic ---
            if needs_disambiguation and found_personas:
                # Rank personas by overall_match_score
                sorted_personas = sorted(
                    found_personas, key=lambda p: p.overall_match_score, reverse=True
                )
                best_persona = sorted_personas[0]
                best_score = best_persona.overall_match_score

                # If there's a clear winner (best score > 0.7 and at least 0.2 higher than next best)
                # or if we only have one persona that matches well
                is_clear_winner = False
                if best_score >= 0.7:
                    if len(sorted_personas) == 1:
                        is_clear_winner = True
                    elif best_score - sorted_personas[1].overall_match_score >= 0.2:
                        is_clear_winner = True

                if is_clear_winner:
                    logger.info(
                        "Clear persona winner found: %s at %s (Score: %f). Filtering sources.",
                        best_persona.role,
                        best_persona.company,
                        best_score,
                    )
                    best_persona_index = found_personas.index(best_persona)
                    valid_sources = [
                        s
                        for s in valid_sources
                        if s.persona_index == best_persona_index
                    ]
                    needs_disambiguation = False
                else:
                    logger.warning(
                        "No clear persona winner found during initial disambiguation. Triggering Active Disambiguation."
                    )
                    disambiguation_result = (
                        await self.active_disambiguation_agent.verify_identity(
                            target_person=person_info, personas=found_personas
                        )
                    )

                    if (
                        disambiguation_result.conclusive_match
                        and disambiguation_result.best_persona_index is not None
                    ):
                        best_persona_index = disambiguation_result.best_persona_index
                        best_persona = found_personas[best_persona_index]
                        logger.info(
                            "Active Disambiguation Agent found conclusive match: %s at %s. Reason: %s",
                            best_persona.role,
                            best_persona.company,
                            disambiguation_result.reasoning,
                        )
                        valid_sources = [
                            s
                            for s in valid_sources
                            if s.persona_index == best_persona_index
                        ]
                        needs_disambiguation = False
                    else:
                        logger.warning(
                            "Active Disambiguation Agent could not find a clear winner. Reason: %s",
                            disambiguation_result.reasoning,
                        )
                        valid_sources = []
                        disambiguation_unresolved = True
            # ----------------------------

            if valid_sources and not needs_disambiguation:
                break
            elif needs_disambiguation:
                # If we filtered down to valid sources for a clear winner, we can break
                if valid_sources:
                    break
                logger.warning(
                    f"Ambiguity detected for {name}. Multiple personas found."
                )
                break
            else:
                logger.warning(
                    f"No conclusive valid sources resolved on attempt {attempt+1}."
                )

        if not valid_sources and not needs_disambiguation:
            logger.warning(
                f"Max retries reached. No valid sources resolved for {name}."
            )
            return self._build_empty_response(
                name, company, summary="No conclusive profiles identified online."
            )

        # 4. Process Results using Search Snippets only (No Scraping/Fetching)
        logger.info("[Step 4/7] Processing search snippets and scoring...")

        final_sources: List[FinalSourceData] = []
        for source in valid_sources:
            snippet = source.snippet
            confidence_from_identity = source.identity_match_score
            source_type = normalize_source_type(source.source_type, source.url)
            url = source.url
            extracted = await self.signal_extraction_agent.extract_signals(
                title=source.title,
                snippet=snippet,
                url=url,
                target_name=name if name != "Unknown Candidate" else None,
            )

            final_confidence = self.confidence_service.compute_source_confidence(
                identity_match_score=confidence_from_identity,
                source_type=source_type,
                extraction_result={
                    **extracted.model_dump(),
                    "title": source.title,
                    "snippet": snippet,
                    "url": url,
                },
            )

            final_sources.append(
                FinalSourceData(
                    url=url,
                    type=source_type,
                    confidence=final_confidence,
                    extracted_data={
                        **extracted.model_dump(exclude_none=True),
                        "snippet": snippet,
                        "title": source.title,
                        "persona_index": source.persona_index,
                    },
                )
            )

        # Filter out sources with low confidence
        final_sources = [s for s in final_sources if s.confidence >= 0.35]
        logger.info(
            f"Successfully processed {len(final_sources)} sources from snippets."
        )

        # 7. Follow-up generation
        if disambiguation_unresolved:
            logger.info("Disambiguation is needed. Generating follow-up questions...")
            follow_up_questions = await self.follow_up_agent.generate_questions(
                name=name, search_context=all_search_results
            )

        # 8. Summary Generation
        logger.info("[Step 8/8] Generating final profile summary...")
        summary = "No sufficient data to generate summary."

        if final_sources:
            # Prepare inputs for Summary Agent
            sources_summary_input = [
                {"url": s.url, "type": s.type, "confidence": s.confidence}
                for s in final_sources
            ]
            structured_data_input = [s.extracted_data for s in final_sources]

            # Determine if we should still treat as ambiguous for the summary
            final_is_ambiguous = False
            if needs_disambiguation:
                if not final_sources:
                    final_is_ambiguous = True
                else:
                    # Check if sources belong to multiple personas
                    persona_indices = {
                        s.extracted_data.get("persona_index")
                        for s in final_sources
                        if s.extracted_data.get("persona_index") is not None
                    }
                    if len(persona_indices) > 1:
                        final_is_ambiguous = True

            summary_result = await self.summary_agent.generate_summary(
                name=name,
                sources=sources_summary_input,
                structured_data=structured_data_input,
                is_ambiguous=final_is_ambiguous,
            )
            summary = summary_result.profile_summary

        logger.info(f"ProfileResearchAgent pipeline for {name} complete.")

        # Build Final Comprehensive Response Schema
        return ComprehensiveProfileResponse(
            person=PersonData(name=name, company=company),
            sources=final_sources,
            summary=summary,
            total_sources=len(final_sources),
            found_personas=[
                PersonaData(
                    name=p.name,
                    company=p.company,
                    role=p.role,
                    location=p.location,
                    description=p.description,
                    associated_urls=p.associated_urls,
                )
                for p in found_personas
            ],
            follow_up_questions=follow_up_questions,
        )

    def _build_empty_response(
        self,
        name: str,
        company: Optional[str] = None,
        summary: str = "Candidate could not be located.",
    ) -> ComprehensiveProfileResponse:
        return ComprehensiveProfileResponse(
            person=PersonData(name=name, company=company),
            sources=[],
            summary=summary,
            total_sources=0,
            follow_up_questions=[],
        )

    def _merge_queries(
        self, seed_queries: List[str], generated_queries: List[str]
    ) -> List[str]:
        merged: List[str] = []
        seen = set()
        for query in [*seed_queries, *generated_queries]:
            normalized = " ".join(query.split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
        return merged[:10]
