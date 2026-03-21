from typing import Any, Dict, List, Optional

from app.agents.active_disambiguation_agent import ActiveDisambiguationAgent
from app.agents.follow_up_agent import FollowUpAgent
from app.agents.identity_resolution_agent import IdentityAgent
from app.agents.profile_seed_resolver_agent import ProfileSeedResolverAgent
from app.agents.query_agent import QueryAgent
from app.agents.signal_extraction_agent import SignalExtractionAgent
from app.agents.summary_agent import SummaryAgent
from app.services.confidence_service import ConfidenceService
from app.services.search_service import SearchService
from app.services.source_normalizer import normalize_source_type

search_service = SearchService()
seed_resolver = ProfileSeedResolverAgent()
query_agent = QueryAgent()
identity_agent = IdentityAgent()
disambiguation_agent = ActiveDisambiguationAgent()
extractor = SignalExtractionAgent()
summary_agent = SummaryAgent()
follow_up_agent = FollowUpAgent()
confidence_service = ConfidenceService()


async def resolve_linkedin_seed(linkedin_url: str) -> Dict[str, Any]:
    result = await seed_resolver.resolve_from_linkedin_url(linkedin_url)
    return result.model_dump(exclude_none=True)


async def generate_queries(
    name: str,
    company: Optional[str] = None,
    designation: Optional[str] = None,
) -> Dict[str, Any]:
    result = await query_agent.generate_search_queries(
        name=name, company=company, designation=designation
    )
    return {"queries": result.queries}


async def refine_queries(
    name: str,
    company: Optional[str],
    designation: Optional[str],
    previous_queries: List[str],
    failure_context: str,
) -> Dict[str, Any]:
    result = await query_agent.refine_search_queries(
        name=name,
        company=company,
        designation=designation,
        previous_queries=previous_queries,
        failure_context=failure_context,
    )
    return {"queries": result.queries}


async def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    results = await search_service.search_web(query, max_results)
    return {
        "query": query,
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "source": r.source,
            }
            for r in results
        ],
    }


async def resolve_identity(
    target_person: Dict[str, Any],
    search_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = await identity_agent.resolve_identity(
        target_person=target_person, search_results=search_results
    )
    return result.model_dump(exclude_none=True)


async def disambiguate_personas(
    target_person: Dict[str, Any],
    personas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = await disambiguation_agent.verify_identity(
        target_person=target_person, personas=personas
    )
    return result.model_dump(exclude_none=True)


async def extract_signals_batch(
    sources: List[Dict[str, Any]],
    target_name: Optional[str] = None,
) -> Dict[str, Any]:
    extracted_sources = []
    for source in sources:
        extracted = await extractor.extract_signals(
            title=source.get("title", ""),
            snippet=source.get("snippet", ""),
            url=source.get("url", ""),
            target_name=target_name,
        )
        extracted_sources.append(
            {
                "url": source.get("url", ""),
                "title": source.get("title", ""),
                "snippet": source.get("snippet", ""),
                "source_type": source.get("source_type")
                or source.get("type")
                or source.get("source", "other"),
                "identity_match_score": source.get("identity_match_score", 0.0),
                "persona_index": source.get("persona_index"),
                "reason": source.get("reason"),
                "extracted_data": extracted.model_dump(exclude_none=True),
            }
        )
    return {"extracted_sources": extracted_sources}


async def score_sources_batch(extracted_sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    final_sources = []
    for source in extracted_sources:
        source_type = normalize_source_type(
            source.get("source_type"), source.get("url", "")
        )
        extracted_data = {
            **(source.get("extracted_data") or {}),
            "title": source.get("title", ""),
            "snippet": source.get("snippet", ""),
            "url": source.get("url", ""),
            "persona_index": source.get("persona_index"),
        }
        confidence = confidence_service.compute_source_confidence(
            identity_match_score=source.get("identity_match_score", 0.0),
            source_type=source_type,
            extraction_result=extracted_data,
        )
        final_sources.append(
            {
                "url": source.get("url", ""),
                "type": source_type,
                "confidence": confidence,
                "extracted_data": extracted_data,
            }
        )
    return {"final_sources": final_sources}


async def generate_profile_summary(
    name: str,
    sources: List[Dict[str, Any]],
    structured_data: List[Dict[str, Any]],
    is_ambiguous: bool = False,
) -> Dict[str, Any]:
    result = await summary_agent.generate_summary(
        name=name,
        sources=sources,
        structured_data=structured_data,
        is_ambiguous=is_ambiguous,
    )
    return {"summary": result.profile_summary}


async def generate_follow_up_questions(
    name: str,
    search_context: List[Dict[str, Any]],
) -> Dict[str, Any]:
    questions = await follow_up_agent.generate_questions(
        name=name, search_context=search_context
    )
    return {"questions": questions}


TOOLS = {
    "resolve_linkedin_seed": resolve_linkedin_seed,
    "generate_queries": generate_queries,
    "refine_queries": refine_queries,
    "search_web": search_web,
    "resolve_identity": resolve_identity,
    "disambiguate_personas": disambiguate_personas,
    "extract_signals_batch": extract_signals_batch,
    "score_sources_batch": score_sources_batch,
    "generate_profile_summary": generate_profile_summary,
    "generate_follow_up_questions": generate_follow_up_questions,
}

TOOL_DESCRIPTIONS = [
    {
        "name": "resolve_linkedin_seed",
        "description": (
            "Resolve an initial identity seed from a LinkedIn URL. Use when "
            "linkedin_url is present to recover name, likely company, role, and slug."
        ),
        "parameters": {"linkedin_url": "string"},
    },
    {
        "name": "generate_queries",
        "description": (
            "Generate a fresh batch of targeted OSINT search queries using the "
            "known name, company, and designation."
        ),
        "parameters": {
            "name": "string",
            "company": "string | null",
            "designation": "string | null",
        },
    },
    {
        "name": "refine_queries",
        "description": (
            "Generate a replacement query set after poor identity matches or "
            "empty results. Provide previous queries and the failure context."
        ),
        "parameters": {
            "name": "string",
            "company": "string | null",
            "designation": "string | null",
            "previous_queries": "string[]",
            "failure_context": "string",
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the public web using DuckDuckGo and return titles, URLs, and snippets."
        ),
        "parameters": {
            "query": "string",
            "max_results": "integer (optional, default 5)",
        },
    },
    {
        "name": "resolve_identity",
        "description": (
            "Analyze aggregated search results, keep only likely matches, and "
            "cluster ambiguous matches into personas."
        ),
        "parameters": {
            "target_person": "object",
            "search_results": "object[]",
        },
    },
    {
        "name": "disambiguate_personas",
        "description": (
            "Run a targeted evidence-gathering pass across ambiguous personas to "
            "pick a winner when identity resolution alone is inconclusive."
        ),
        "parameters": {
            "target_person": "object",
            "personas": "object[]",
        },
    },
    {
        "name": "extract_signals_batch",
        "description": (
            "Extract structured professional signals from candidate source titles "
            "and snippets for one or more sources."
        ),
        "parameters": {
            "sources": "object[]",
            "target_name": "string | null",
        },
    },
    {
        "name": "score_sources_batch",
        "description": (
            "Score extracted sources by combining identity strength, platform "
            "trust, and extraction consistency."
        ),
        "parameters": {"extracted_sources": "object[]"},
    },
    {
        "name": "generate_profile_summary",
        "description": (
            "Synthesize the final profile summary from the vetted, scored sources "
            "and extracted structured data."
        ),
        "parameters": {
            "name": "string",
            "sources": "object[]",
            "structured_data": "object[]",
            "is_ambiguous": "boolean (optional, default false)",
        },
    },
    {
        "name": "generate_follow_up_questions",
        "description": (
            "Generate clarifying questions when multiple personas remain plausible "
            "or no conclusive online identity can be found."
        ),
        "parameters": {
            "name": "string",
            "search_context": "object[]",
        },
    },
]
