import re
from typing import Optional

from pydantic import BaseModel, Field

from app.agents.base import AgentException, BaseAgent
from app.config import get_settings
from app.logger import logger

settings = get_settings()


class SignalExtractionResult(BaseModel):
    person_name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    previous_companies: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    location: Optional[str] = None


class SignalExtractionAgent:
    """
    Hybrid extractor:
    - deterministic parsing for speed and stability
    - LLM repair pass when the snippet is sparse or ambiguous
    """

    TOPIC_PATTERNS = (
        r"expertise in ([^.]+)",
        r"focus(?:es)? on ([^.]+)",
        r"interest(?:ed)? in ([^.]+)",
        r"works on ([^.]+)",
        r"specializ(?:e|es|ed) in ([^.]+)",
        r"building ([^.]+)",
    )
    ACHIEVEMENT_MARKERS = (
        "speaker",
        "spoke",
        "published",
        "founded",
        "award",
        "patent",
        "inventor",
        "author",
        "maintainer",
    )
    LOCATION_PATTERNS = (
        r"\b(?:based in|located in|from)\s+([A-Z][A-Za-z.\- ]{1,40}(?:,\s*[A-Z][A-Za-z.\- ]{1,40})?)"
        r"(?=\.|,|;|$)",
        r"\b([A-Z][A-Za-z.\- ]{1,40},\s*[A-Z][A-Za-z.\- ]{1,40})\b",
    )

    def __init__(self, provider: str = "gemini"):
        self._llm_helper: Optional[BaseAgent] = None
        if any(
            [
                settings.gemini_api_key,
                settings.openai_api_key,
                settings.groq_api_key,
            ]
        ):
            try:
                self._llm_helper = BaseAgent(
                    provider=provider, max_retries=1, timeout_seconds=20
                )
            except AgentException:
                logger.warning(
                    "SignalExtractionAgent LLM fallback unavailable. Using heuristics only."
                )

    async def extract_signals(
        self,
        *,
        title: str,
        snippet: str,
        url: str,
        target_name: Optional[str] = None,
    ) -> SignalExtractionResult:
        text = " ".join(part.strip() for part in [title, snippet] if part).strip()
        heuristic = SignalExtractionResult(
            person_name=self._extract_name_from_title(title) or target_name,
            role=None,
            company=None,
            previous_companies=[],
            topics=[],
            achievements=[],
            location=self._extract_location(snippet),
        )

        heuristic.role, heuristic.company = self._extract_role_company(title, snippet)
        heuristic.previous_companies = self._extract_previous_companies(
            text, heuristic.company
        )
        heuristic.topics = self._extract_topics(text, title, url)
        heuristic.achievements = self._extract_achievements(title, snippet)

        if not self._needs_llm_enrichment(heuristic):
            return heuristic

        llm_result = await self._extract_with_llm(
            title=title, snippet=snippet, url=url, target_name=target_name
        )
        if not llm_result:
            return heuristic

        return self._merge_results(heuristic, llm_result)

    def _needs_llm_enrichment(self, result: SignalExtractionResult) -> bool:
        populated = sum(
            1
            for value in [
                result.person_name,
                result.role,
                result.company,
                result.location,
                result.previous_companies,
                result.topics,
                result.achievements,
            ]
            if value
        )
        return populated < 3 or (not result.role and not result.company)

    async def _extract_with_llm(
        self,
        *,
        title: str,
        snippet: str,
        url: str,
        target_name: Optional[str],
    ) -> Optional[SignalExtractionResult]:
        if not self._llm_helper:
            return None

        system_prompt = (
            "You extract structured professional signals from search results. "
            "Use only the provided title, snippet, and URL. "
            "Do not infer facts that are not directly supported. "
            "Return concise arrays and null for unknown scalars."
        )
        user_prompt = (
            f"Target Name: {target_name or ''}\n"
            f"URL: {url}\n"
            f"Title: {title}\n"
            f"Snippet: {snippet}"
        )

        try:
            return await self._llm_helper.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=SignalExtractionResult,
            )
        except Exception as exc:
            logger.warning("SignalExtractionAgent LLM enrichment failed: %s", exc)
            return None

    def _merge_results(
        self,
        heuristic: SignalExtractionResult,
        llm_result: SignalExtractionResult,
    ) -> SignalExtractionResult:
        topics = self._merge_lists(heuristic.topics, llm_result.topics, limit=6)
        achievements = self._merge_lists(
            heuristic.achievements, llm_result.achievements, limit=4
        )
        previous_companies = self._merge_lists(
            heuristic.previous_companies, llm_result.previous_companies, limit=4
        )
        return SignalExtractionResult(
            person_name=heuristic.person_name or llm_result.person_name,
            role=heuristic.role or llm_result.role,
            company=heuristic.company or llm_result.company,
            previous_companies=previous_companies,
            topics=topics,
            achievements=achievements,
            location=heuristic.location or llm_result.location,
        )

    def _extract_name_from_title(self, title: str) -> Optional[str]:
        cleaned = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\|\s*GitHub.*$", "", cleaned, flags=re.IGNORECASE)
        parts = [
            part.strip()
            for part in re.split(r"\s[-|:]\s", cleaned)
            if part.strip() and len(part.strip()) > 1
        ]
        if not parts:
            return None
        candidate = parts[0]
        return candidate if self._looks_like_person_name(candidate) else None

    def _extract_role_company(
        self, title: str, snippet: str
    ) -> tuple[Optional[str], Optional[str]]:
        title_parts = [part.strip() for part in re.split(r"\s[-|]\s", title) if part.strip()]
        for part in title_parts:
            if "@" in part:
                role, company = [self._clean(item) for item in part.split("@", 1)]
                if role and company:
                    return role, company

        patterns = (
            r"(?P<role>[A-Z][A-Za-z0-9&/,\-+ ]{2,80})\s+@\s+(?P<company>[A-Z][A-Za-z0-9&.,\- ]{1,80})",
            r"(?P<role>[A-Z][A-Za-z0-9&/,\-+ ]{2,80})\s+(?:at|with)\s+(?P<company>[A-Z][A-Za-z0-9&.,\- ]{1,80})",
            r"(?P<role>[A-Z][A-Za-z0-9&/,\-+ ]{2,80}),\s+(?P<company>[A-Z][A-Za-z0-9&.,\- ]{1,80})",
        )
        for text in [title, snippet]:
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return (
                        self._clean(match.group("role")),
                        self._clean(match.group("company")),
                    )

        lowered = title.lower()
        if "linkedin" in lowered and len(title_parts) >= 3:
            role_candidate = self._clean(title_parts[1])
            company_candidate = self._clean(title_parts[2])
            if role_candidate and company_candidate:
                return role_candidate, company_candidate

        return None, None

    def _extract_previous_companies(
        self, text: str, current_company: Optional[str]
    ) -> list[str]:
        matches = re.findall(
            r"(?:previously|before that|prior to [^,.;]+,)\s+(?:worked|was|studied)[^,.;]*?\s+at\s+"
            r"([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,4})"
            r"(?=\s+(?:and|before|after)\b|[.,;]|$)",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = []
        for match in matches:
            company = self._clean(match)
            if company and company != current_company and company not in cleaned:
                cleaned.append(company)
        return cleaned

    def _extract_topics(self, text: str, title: str, url: str) -> list[str]:
        topics: list[str] = []
        for pattern in self.TOPIC_PATTERNS:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                topics.extend(self._split_phrases(match))

        keyword_map = (
            "robotics",
            "ai",
            "machine learning",
            "distributed systems",
            "data engineering",
            "platform engineering",
            "cloud",
            "developer experience",
            "security",
            "backend",
            "frontend",
            "product",
        )
        lowered_text = text.lower()
        for keyword in keyword_map:
            if keyword in lowered_text:
                topics.append(keyword)

        combined_title = f"{title} {url}".lower()
        if "github.com" in combined_title:
            topics.append("software engineering")
        if "medium.com" in combined_title:
            topics.append("writing")
        if "youtube.com" in combined_title or "youtu.be" in combined_title:
            topics.append("public speaking")

        deduped: list[str] = []
        for topic in topics:
            cleaned = self._clean(topic).lower()
            if cleaned and cleaned not in deduped:
                deduped.append(cleaned)
        return deduped[:6]

    def _extract_achievements(self, title: str, snippet: str) -> list[str]:
        text = f"{title}. {snippet}".strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        achievements = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(marker in lowered for marker in self.ACHIEVEMENT_MARKERS):
                cleaned = self._clean(sentence)
                if cleaned:
                    achievements.append(cleaned)
        return achievements[:4]

    def _extract_location(self, snippet: str) -> Optional[str]:
        for pattern in self.LOCATION_PATTERNS:
            match = re.search(pattern, snippet)
            if match:
                return self._clean(match.group(1))
        return None

    def _merge_lists(self, primary: list[str], secondary: list[str], limit: int) -> list[str]:
        merged: list[str] = []
        for value in [*primary, *secondary]:
            cleaned = self._clean(value)
            if cleaned and cleaned not in merged:
                merged.append(cleaned)
        return merged[:limit]

    def _split_phrases(self, value: str) -> list[str]:
        parts = re.split(r",| and |\|", value)
        return [part.strip() for part in parts if part.strip()]

    def _looks_like_person_name(self, value: str) -> bool:
        tokens = [token for token in value.split() if token]
        if not 2 <= len(tokens) <= 4:
            return False
        return all(token[:1].isupper() for token in tokens)

    def _clean(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" -|,.;")
