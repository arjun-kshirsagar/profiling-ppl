from typing import Any, Dict

from app.logger import logger
from app.services.source_normalizer import normalize_source_type

# Constants for platform trust
PLATFORM_TRUST_WEIGHTS = {
    "linkedin_profile": 0.95,
    "linkedin_page": 0.80,
    "github_profile": 0.90,
    "github_repository": 0.75,
    "twitter_profile": 0.80,
    "x_profile": 0.80,
    "news_article": 0.75,
    "personal_blog": 0.50,
    "personal_site": 0.55,
    "medium_post": 0.65,
    "youtube_channel": 0.75,
    "youtube_video": 0.65,
    "crunchbase": 0.90,
    "unknown": 0.30,
}


class ConfidenceService:
    """
    Service to calculate the final confidence score for a data source
    by combining agent-provided scores, platform trust heuristics,
    and data extraction consistency.
    """

    def compute_source_confidence(
        self,
        identity_match_score: float,
        source_type: str,
        extraction_result: Dict[str, Any],
    ) -> float:
        """
        Calculates a normalized confidence score (0.0 to 1.0).

        Formula:
        score = (Identity Match * 0.5) + (Platform Trust * 0.3) + (Extraction Consistency * 0.2)
        """
        # 1. Platform Trust Score
        normalized_type = normalize_source_type(
            source_type, extraction_result.get("url", "")
        )
        platform_score = PLATFORM_TRUST_WEIGHTS.get(
            normalized_type.lower(), PLATFORM_TRUST_WEIGHTS["unknown"]
        )

        # 2. Extraction Consistency Score
        # Check how many key fields were successfully extracted
        key_fields = ["role", "company", "previous_companies", "topics", "achievements"]
        fields_found = 0
        for field in key_fields:
            val = extraction_result.get(field)
            if val:
                # Check for non-empty lists or non-null strings
                if isinstance(val, list) and len(val) > 0:
                    fields_found += 1
                elif isinstance(val, str) and len(val.strip()) > 0:
                    fields_found += 1

        consistency_score = fields_found / len(key_fields)

        # 3. Weighted Combination
        # Identity: 50%, Platform: 30%, Consistency: 20%
        final_score = (
            (identity_match_score * 0.5)
            + (platform_score * 0.3)
            + (consistency_score * 0.2)
        )

        # Log for debugging
        logger.info(
            f"Confidence calculated for {normalized_type}: {final_score:.2f} "
            f"(Identity: {identity_match_score}, Platform: {platform_score}, Consistency: {consistency_score:.2f})"
        )

        return round(max(0.0, min(1.0, final_score)), 2)
