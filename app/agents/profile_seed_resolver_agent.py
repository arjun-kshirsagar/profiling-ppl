import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.logger import logger
from app.services.search_service import SearchService


class SeedEvidence(BaseModel):
    url: str
    title: str
    snippet: str
    match_score: float


class SeedResolutionResult(BaseModel):
    name: Optional[str] = None
    possible_companies: list[str] = Field(default_factory=list)
    possible_roles: list[str] = Field(default_factory=list)
    linkedin_slug: Optional[str] = None
    confidence: float = 0.0
    matched_url: Optional[str] = None
    seed_queries: list[str] = Field(default_factory=list)
    evidence: list[SeedEvidence] = Field(default_factory=list)


class ProfileSeedResolverAgent:
    """
    Resolve an initial identity seed from a LinkedIn URL before the broader
    discovery pipeline runs.
    """

    def __init__(self):
        self.search_service = SearchService()

    async def resolve_from_linkedin_url(
        self, linkedin_url: str
    ) -> SeedResolutionResult:
        logger.info(f"Running ProfileSeedResolverAgent for URL: {linkedin_url}")
        normalized_target = self._normalize_linkedin_url(linkedin_url)
        slug = self._extract_username_from_url(linkedin_url)
        seed_queries = self._build_seed_queries(linkedin_url, slug)

        search_results = []
        for query in seed_queries:
            results = await self.search_service.search_web(query=query, max_results=5)
            search_results.extend(results)

        scored_results = []
        seen_urls = set()
        for result in search_results:
            normalized_url = self._normalize_linkedin_url(result.url)
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            score = self._score_result(
                target_url=normalized_target,
                result_url=result.url,
                target_slug=slug,
                title=result.title,
                snippet=result.snippet,
            )
            if score <= 0:
                continue
            scored_results.append(
                SeedEvidence(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet,
                    match_score=round(score, 2),
                )
            )

        scored_results.sort(key=lambda item: item.match_score, reverse=True)
        best_match = scored_results[0] if scored_results else None

        if not best_match:
            return SeedResolutionResult(linkedin_slug=slug, seed_queries=seed_queries)

        name = self._extract_name(best_match.title, best_match.snippet)
        role, company = self._extract_role_company(best_match.title, best_match.snippet)

        return SeedResolutionResult(
            name=name,
            possible_companies=[company] if company else [],
            possible_roles=[role] if role else [],
            linkedin_slug=slug,
            confidence=best_match.match_score,
            matched_url=best_match.url,
            seed_queries=seed_queries,
            evidence=scored_results[:3],
        )

    def _build_seed_queries(self, linkedin_url: str, slug: str) -> list[str]:
        queries = [f'"{linkedin_url}"']
        if slug:
            queries.extend(
                [
                    f'site:linkedin.com/in "{slug}"',
                    f'"{slug}" site:linkedin.com/in',
                    f'"{slug}" linkedin',
                ]
            )
        return queries

    def _score_result(
        self,
        *,
        target_url: str,
        result_url: str,
        target_slug: str,
        title: str,
        snippet: str,
    ) -> float:
        normalized_result = self._normalize_linkedin_url(result_url)
        if normalized_result == target_url:
            return 1.0

        result_slug = self._extract_username_from_url(result_url)
        if target_slug and result_slug and result_slug == target_slug:
            return 0.95

        title_lower = title.lower()
        snippet_lower = snippet.lower()
        compact_slug = target_slug.replace("-", "").lower()

        if target_slug and target_slug.lower() in normalized_result.lower():
            return 0.75

        if compact_slug and compact_slug in re.sub(r"[^a-z0-9]", "", title_lower):
            return 0.65

        if compact_slug and compact_slug in re.sub(r"[^a-z0-9]", "", snippet_lower):
            return 0.55

        return 0.0

    def _extract_name(self, title: str, snippet: str) -> Optional[str]:
        cleaned_title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
        parts = [part.strip() for part in cleaned_title.split(" - ") if part.strip()]
        if parts and self._looks_like_name(parts[0]):
            return parts[0]

        snippet_match = re.search(
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:is|has been|works|worked)",
            snippet,
        )
        if snippet_match:
            return snippet_match.group(1).strip()

        return None

    def _extract_role_company(
        self, title: str, snippet: str
    ) -> tuple[Optional[str], Optional[str]]:
        title_parts = [part.strip() for part in title.split(" - ") if part.strip()]
        for part in title_parts:
            if "@" in part:
                role, company = [item.strip() for item in part.split("@", 1)]
                if role and company:
                    return role, company

        match = re.search(
            r"(?P<role>[A-Z][A-Za-z0-9&/,\-+ ]{2,80})\s+(?:at|with)\s+(?P<company>[A-Z][A-Za-z0-9&.,\- ]{1,80})",
            snippet,
        )
        if match:
            return match.group("role").strip(), match.group("company").strip(" .,")

        return None, None

    def _normalize_linkedin_url(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"

    def _extract_username_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = [part for part in path.split("/") if part]
        if "in" in parts:
            index = parts.index("in")
            if len(parts) > index + 1:
                return parts[index + 1].lower()
        return parts[-1].lower() if parts else ""

    def _looks_like_name(self, value: str) -> bool:
        tokens = [token for token in value.split() if token]
        if not 2 <= len(tokens) <= 4:
            return False
        return all(token[:1].isupper() for token in tokens)
