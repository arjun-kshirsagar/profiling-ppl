import asyncio
from typing import List, Optional

from app.agents.identity_resolution_agent import IdentityAgent
from app.agents.info_extraction_agent import InfoExtractionAgent
from app.agents.query_agent import QueryAgent
from app.agents.summary_agent import SummaryAgent
from app.logger import logger
from app.schemas import ComprehensiveProfileResponse, FinalSourceData, PersonData
from app.services.confidence_service import ConfidenceService
from app.services.page_fetcher import fetch_page
from app.services.search_service import SearchService


class ProfileResearchAgent:
    """
    Orchestrator Agent that ties together the entire profile research pipeline:
    Query Generation -> Web Search -> Identity Resolution -> Page Fetching ->
    Extraction -> Confidence Scoring -> Summarization
    """

    def __init__(self):
        self.query_agent = QueryAgent()
        self.search_service = SearchService()
        self.identity_agent = IdentityAgent()
        self.extraction_agent = InfoExtractionAgent()
        self.confidence_service = ConfidenceService()
        self.summary_agent = SummaryAgent()

    async def research_profile(
        self,
        name: str,
        company: Optional[str] = None,
        designation: Optional[str] = None,
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

        max_retries = 2
        queries = []
        valid_sources = []

        for attempt in range(max_retries):
            # 1. Generate Queries
            if attempt == 0:
                logger.info(
                    f"[Step 1/7] Generating search queries (Attempt {attempt+1}/{max_retries})..."
                )
                query_result = await self.query_agent.generate_search_queries(
                    name=name, company=company, designation=designation
                )
                queries = query_result.queries
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
                queries = query_result.queries

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
            logger.info(
                f"Identity Agent identified {len(valid_sources)} valid sources out of {len(all_search_results)}."
            )

            if valid_sources:
                break
            else:
                logger.warning(
                    f"No conclusive valid sources resolved on attempt {attempt+1}."
                )

        if not valid_sources:
            logger.warning(
                f"Max retries reached. No valid sources resolved for {name}."
            )
            return self._build_empty_response(
                name, company, summary="No conclusive profiles identified online."
            )

        # 4. & 5. Fetch Pages and Extract Info (Concurrent)
        logger.info("[Step 4/7 & 5/7] Fetching pages and extracting signals...")

        async def fetch_and_extract(source):
            url = source.url
            confidence_from_identity = source.confidence

            # Step 4: Fetch Page
            page_data = await asyncio.to_thread(fetch_page, url)
            page_text = page_data.get("text")

            if not page_text or len(page_text.strip()) < 20:
                logger.warning(f"Insufficient text extracted from {url}")
                return None

            # Step 5: Extract structured information from text
            try:
                extraction_res = await self.extraction_agent.extract_info(
                    text=page_text, target_name=name
                )
            except Exception as e:
                logger.error(f"InfoExtractionAgent failed for {url}: {e}")
                return None

            extracted_dict = (
                dict(extraction_res)
                if isinstance(extraction_res, dict)
                else extraction_res.model_dump(exclude_none=True)
            )
            source_type = extracted_dict.get("type", "unknown")

            # Step 6: Confidence Scoring
            final_confidence = self.confidence_service.compute_source_confidence(
                identity_match_score=confidence_from_identity,
                source_type=source_type,
                extraction_result=extracted_dict,
            )

            # Form final source data schema explicitly
            return FinalSourceData(
                url=url,
                type=source_type,
                confidence=final_confidence,
                extracted_data=extracted_dict,
            )

        # Execute concurrent fetch and extract tasks for all valid sources
        extraction_tasks = [fetch_and_extract(src) for src in valid_sources]
        task_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

        final_sources: List[FinalSourceData] = []
        for index, tr in enumerate(task_results):
            if isinstance(tr, Exception):
                logger.error(
                    f"Failed to extract info from {valid_sources[index].url}: {tr}"
                )
            elif tr is not None:
                final_sources.append(tr)

        logger.info(f"Successfully extracted data from {len(final_sources)} sources.")
        # Filter out sources with very low confidence entirely threshold < ~0.4
        final_sources = [s for s in final_sources if s.confidence >= 0.4]

        # 7. Summary Generation
        logger.info("[Step 7/7] Generating final profile summary...")
        summary = "No sufficient data to generate summary."

        if final_sources:
            # Prepare inputs for Summary Agent
            sources_summary_input = [
                {"url": s.url, "type": s.type, "confidence": s.confidence}
                for s in final_sources
            ]
            structured_data_input = [s.extracted_data for s in final_sources]

            summary_result = await self.summary_agent.generate_summary(
                name=name,
                sources=sources_summary_input,
                structured_data=structured_data_input,
            )
            summary = summary_result.profile_summary

        logger.info(f"ProfileResearchAgent pipeline for {name} complete.")

        # Build Final Comprehensive Response Schema
        return ComprehensiveProfileResponse(
            person=PersonData(name=name, company=company),
            sources=final_sources,
            summary=summary,
            total_sources=len(final_sources),
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
        )
