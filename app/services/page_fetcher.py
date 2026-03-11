from typing import Dict, Optional

import requests
import tiktoken
from bs4 import BeautifulSoup

from app.logger import logger


def fetch_page(url: str) -> Dict[str, Optional[str]]:
    """
    Fetches a web page, strips HTML and scripts, extracts the main text,
    and limits the text to the first 4000 tokens.
    """
    logger.info(f"Fetching page content for URL: {url}")

    result = {"url": url, "title": None, "text": None, "meta_description": None}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return result

    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract Title
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()

        # Extract Meta Description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            result["meta_description"] = meta_desc["content"].strip()

        # Remove scripts, styles, and usually non-content tags
        for unwanted in soup(
            ["script", "style", "noscript", "nav", "header", "footer", "aside"]
        ):
            unwanted.extract()

        # Extract structural text
        text = soup.get_text(separator="\n", strip=True)

        # Collapse multiple newlines/spaces
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)

        # Limit text to 4000 tokens
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(clean_text)

        if len(tokens) > 4000:
            truncated_tokens = tokens[:4000]
            clean_text = encoding.decode(truncated_tokens)

        result["text"] = clean_text

    except Exception as e:
        logger.error(f"Failed to parse content for {url}: {e}")

    return result
