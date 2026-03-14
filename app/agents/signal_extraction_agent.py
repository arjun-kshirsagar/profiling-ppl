import re
from typing import Optional

from pydantic import BaseModel, Field


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
    Lightweight extraction over titles and snippets so downstream scoring and
    summary generation can operate on structured signals.
    """

    TOPIC_PATTERNS = (
        r"expertise in ([^.]+)",
        r"focus(?:es)? on ([^.]+)",
        r"interest(?:ed)? in ([^.]+)",
        r"works on ([^.]+)",
    )
    ACHIEVEMENT_MARKERS = ("speaker", "spoke", "published", "founded", "award")

    async def extract_signals(
        self,
        *,
        title: str,
        snippet: str,
        url: str,
        target_name: Optional[str] = None,
    ) -> SignalExtractionResult:
        del url
        text = " ".join(part.strip() for part in [title, snippet] if part).strip()
        role, company = self._extract_role_company(title, snippet)
        previous_companies = self._extract_previous_companies(text, company)
        topics = self._extract_topics(text)
        achievements = self._extract_achievements(snippet)
        person_name = self._extract_name_from_title(title) or target_name

        return SignalExtractionResult(
            person_name=person_name,
            role=role,
            company=company,
            previous_companies=previous_companies,
            topics=topics,
            achievements=achievements,
        )

    def _extract_name_from_title(self, title: str) -> Optional[str]:
        cleaned = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
        parts = [
            part.strip() for part in re.split(r"\s[-|:]\s", cleaned) if part.strip()
        ]
        if not parts:
            return None
        candidate = parts[0]
        if self._looks_like_person_name(candidate):
            return candidate
        return None

    def _extract_role_company(
        self, title: str, snippet: str
    ) -> tuple[Optional[str], Optional[str]]:
        title_parts = [part.strip() for part in title.split(" - ") if part.strip()]
        if len(title_parts) >= 2 and "@" in title_parts[1]:
            role, company = [self._clean(part) for part in title_parts[1].split("@", 1)]
            return role, company

        for text in [snippet]:
            match = re.search(
                r"(?P<role>[A-Z][A-Za-z0-9&/,\-+ ]{2,80})\s+@\s+(?P<company>[A-Z][A-Za-z0-9&.,\- ]{1,80})",
                text,
            )
            if match:
                return self._clean(match.group("role")), self._clean(
                    match.group("company")
                )

        for text in [snippet]:
            match = re.search(
                r"(?:is|as|currently|working as|works as)\s+(?P<role>[A-Z][A-Za-z0-9&/,\-+ ]{2,80})"
                r"\s+(?:at|with)\s+(?P<company>[A-Z][A-Za-z0-9&.,\- ]{1,80})",
                text,
                flags=re.IGNORECASE,
            )
            if match:
                return self._clean(match.group("role")), self._clean(
                    match.group("company")
                )

        return None, None

    def _extract_previous_companies(
        self, text: str, current_company: Optional[str]
    ) -> list[str]:
        matches = re.findall(
            r"(?:previously|before that|prior to [^,.;]+,)\s+(?:worked|was|studied)[^,.;]*?\s+at\s+"
            r"([A-Z][A-Za-z0-9&.,\- ]+)",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = []
        for match in matches:
            company = self._clean(match)
            if company and company != current_company and company not in cleaned:
                cleaned.append(company)
        return cleaned

    def _extract_topics(self, text: str) -> list[str]:
        topics: list[str] = []
        for pattern in self.TOPIC_PATTERNS:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                topics.extend(self._split_phrases(match))

        if not topics:
            for keyword in (
                "robotics",
                "ai",
                "machine learning",
                "distributed systems",
            ):
                if keyword in text.lower():
                    topics.append(keyword)

        deduped: list[str] = []
        for topic in topics:
            cleaned = self._clean(topic).lower()
            if cleaned and cleaned not in deduped:
                deduped.append(cleaned)
        return deduped[:5]

    def _extract_achievements(self, snippet: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", snippet)
        achievements = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(marker in lowered for marker in self.ACHIEVEMENT_MARKERS):
                cleaned = self._clean(sentence)
                if cleaned:
                    achievements.append(cleaned)
        return achievements[:3]

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
