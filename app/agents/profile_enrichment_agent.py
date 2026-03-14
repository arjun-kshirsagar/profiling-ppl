import asyncio
import urllib.parse
from typing import List

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.logger import logger
from app.services.search_service import SearchService


class EnrichmentResult(BaseModel):
    name: str = Field(
        description="The full name of the candidate inferred from the search snippets or URL."
    )
    possible_companies: List[str] = Field(
        default_factory=list,
        description="List of companies the candidate might be associated with.",
    )
    possible_roles: List[str] = Field(
        default_factory=list,
        description="List of roles or designations the candidate might hold.",
    )
    confidence: float = Field(
        description="Confidence score (0.0 to 1.0) indicating how certain the inferred details are."
    )


class ProfileEnrichmentAgent(BaseAgent):
    """
    Agent responsible for taking a profile URL (e.g., LinkedIn), performing targeted searches
    using the search API, and extracting basic profile attributes like name, company, and role
    from search snippets, without actually scraping the profile page.
    """

    def __init__(self, provider: str = "gemini", max_retries: int = 2):
        super().__init__(provider=provider, max_retries=max_retries, timeout_seconds=20)
        self.search_service = SearchService()

    def _extract_username_from_url(self, url: str) -> str:
        """
        Naive extraction of username from LinkedIn URLs.
        e.g., https://www.linkedin.com/in/pparashar -> pparashar
        """
        try:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path.strip("/")
            parts = path.split("/")
            if "in" in parts:
                idx = parts.index("in")
                if len(parts) > idx + 1:
                    return parts[idx + 1]
            # Fallback to the last part
            return parts[-1]
        except Exception:
            return ""

    async def enrich_from_linkedin_url(self, linkedin_url: str) -> EnrichmentResult:
        """
        Uses search snippets from LinkedIn to extract candidate details.
        """
        logger.info(f"Running ProfileEnrichmentAgent for URL: {linkedin_url}")

        username = self._extract_username_from_url(linkedin_url)
        # Try multiple query variations for better discovery
        search_queries = [
            f'site:linkedin.com/in "{linkedin_url}"',
        ]
        if username:
            search_queries.append(f'site:linkedin.com/in "{username}"')

        # Also try searching the username broadly if it looks like a name part
        if username and len(username) > 3:
            search_queries.append(f'linkedin "{username}"')

        # Perform the web searches concurrently
        all_search_results = []
        try:
            search_tasks = [
                self.search_service.search_web(query=q, max_results=3)
                for q in search_queries
            ]
            results_lists = await asyncio.gather(*search_tasks)
            for res_list in results_lists:
                all_search_results.extend(res_list)
        except Exception as e:
            logger.error(f"Search failed during enrichment: {e}")

        # Deduplicate results
        seen_urls = set()
        unique_results = []
        for r in all_search_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_results.append(r)

        if not unique_results:
            logger.warning(
                f"No search results found for {linkedin_url} during enrichment."
            )
            return EnrichmentResult(
                name=username or "Unknown",
                possible_companies=[],
                possible_roles=[],
                confidence=0.0,
            )

        # Convert search results to a string context for the LLM
        snippets_context = []
        for res in unique_results:
            snippets_context.append(
                f"Title: {res.title}\nSnippet: {res.snippet}\nURL: {res.url}\n"
            )

        context_str = "\n".join(snippets_context)

        system_prompt = (
            "You are an expert Open Source Intelligence (OSINT) analyst and data extractor. "
            "Your task is to infer a candidate's full name, possible current/past companies, and "
            "possible roles/designations based purely on search engine snippets of their LinkedIn profile. "
            "\n\nRules:\n"
            "1. Extract the 'name' as accurately as possible. It is often at the beginning of the title.\n"
            "2. Extract any mentioned companies and put them in 'possible_companies'.\n"
            "3. Extract any mentioned roles (e.g., Software Engineer) and put them in 'possible_roles'.\n"
            "4. Provide a 'confidence' score (0.0 to 1.0) assessing how explicitly the snippet states these facts.\n"
            "5. If you cannot confidently determine the name, use the username from the URL as a fallback, "
            "but lower the confidence.\n"
            "6. Be careful with titles like 'Priyam Parashar - Roboticist @ Waymo - LinkedIn'. "
            "The name is 'Priyam Parashar'."
        )

        user_prompt = (
            f"Target URL: {linkedin_url}\n"
            f"Extracted Username: {username}\n\n"
            f"Search Snippets Context:\n{context_str}"
        )

        try:
            result = await self.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=EnrichmentResult,
            )
            return result
        except Exception as e:
            logger.error(f"ProfileEnrichmentAgent LLM extraction failed: {e}")
            return EnrichmentResult(
                name=username or "Unknown",
                possible_companies=[],
                possible_roles=[],
                confidence=0.0,
            )
