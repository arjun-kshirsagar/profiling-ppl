import asyncio
from typing import List

from ddgs import DDGS
from pydantic import BaseModel

from app.logger import logger


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str = "duckduckgo"


class SearchService:
    """
    Service responsible for executing web searches via DuckDuckGo.
    Handles URL deduplication and result limiting.
    """

    def __init__(self):
        # We can use the async version for better concurrency later
        pass

    def _search_sync(self, query: str, max_results: int) -> List[SearchResult]:
        fetch_limit = max_results * 2
        unique_results = []
        seen_urls = set()

        try:
            with DDGS() as ddgs:
                results_generator = ddgs.text(query, max_results=fetch_limit)

                if results_generator:
                    for r in results_generator:
                        url = r.get("href", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            unique_results.append(
                                SearchResult(
                                    title=r.get("title", ""),
                                    url=url,
                                    snippet=r.get("body", ""),
                                    source="duckduckgo",
                                )
                            )
                        if len(unique_results) >= max_results:
                            break

            return unique_results
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

    async def search_web(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Executes an asynchronous web search using DuckDuckGo, deduplicates URLs, and returns top results.
        """
        logger.info(f"Executing web search for query: '{query}'")
        return await asyncio.to_thread(self._search_sync, query, max_results)
