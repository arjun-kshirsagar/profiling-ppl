from urllib.parse import urlparse


def normalize_source_type(raw_source_type: str | None, url: str) -> str:
    raw = (raw_source_type or "").strip().lower()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    if "linkedin.com" in domain:
        if "/in/" in path:
            return "linkedin_profile"
        return "linkedin_page"

    if "github.com" in domain:
        path_parts = [part for part in path.split("/") if part]
        if len(path_parts) == 1:
            return "github_profile"
        return "github_repository"

    if "youtube.com" in domain or "youtu.be" in domain:
        if "/channel/" in path or path.startswith("/@") or "/c/" in path:
            return "youtube_channel"
        return "youtube_video"

    if "medium.com" in domain:
        return "medium_post"

    if "twitter.com" in domain:
        return "twitter_profile"

    if "x.com" in domain:
        return "x_profile"

    if "crunchbase.com" in domain:
        return "crunchbase"

    if raw in {"linkedin", "linkedin_profile"}:
        return "linkedin_profile"
    if raw in {"github", "github_profile"}:
        return "github_profile"
    if raw in {"youtube", "youtube_channel", "youtube_video"}:
        return "youtube_video"
    if raw in {"news", "news_article"}:
        return "news_article"
    if raw in {"blog", "personal_blog", "personal_site", "blog_post"}:
        return "personal_blog"

    if raw == "other":
        return "personal_site"

    if domain.startswith("www."):
        domain = domain[4:]

    common_news_markers = ("news", "techcrunch.com", "forbes.com", "fortune.com")
    if any(marker in domain for marker in common_news_markers):
        return "news_article"

    if path in {"", "/"}:
        return "personal_site"

    return "unknown"
