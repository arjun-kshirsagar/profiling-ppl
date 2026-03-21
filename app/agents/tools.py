from typing import Any, Dict, List

from app.agents.signal_extraction_agent import SignalExtractionAgent
from app.services.search_service import SearchService

search_service = SearchService()
extractor = SignalExtractionAgent()


async def search_web(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search the web using DuckDuckGo.
    """
    results = await search_service.search_web(query, max_results)
    return [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results]


async def extract_profile_data(title: str, snippet: str, url: str) -> Dict[str, Any]:
    """
    Extracts structured professional signals (role, company, achievements) from a search result snippet.
    """
    res = await extractor.extract_signals(title=title, snippet=snippet, url=url)
    return res.model_dump(exclude_none=True)


TOOLS = {"search_web": search_web, "extract_profile_data": extract_profile_data}

TOOL_DESCRIPTIONS = [
    {
        "name": "search_web",
        "description": (
            "Search the web to find relevant links and snippets. "
            "Use this to find LinkedIn profiles, news, and company pages."
        ),
        "parameters": {
            "query": "string (the search query)",
            "max_results": "integer (optional, default 5)",
        },
    },
    {
        "name": "extract_profile_data",
        "description": (
            "Extracts structured professional signals (role, company, achievements) "
            "from a search result title and snippet. Use this after searching to "
            "structured data from interesting snippets."
        ),
        "parameters": {
            "title": "string (from search result)",
            "snippet": "string (from search result)",
            "url": "string (from search result)",
        },
    },
]
