"""
Tool: URL Fetcher
Fetches and extracts text content from web pages.
"""

import requests
import re
import logging
from utils.tools import register_tool

logger = logging.getLogger(__name__)

MAX_CONTENT = 5000
TIMEOUT = 15

def _fetch_url(url: str, extract_text: bool = True) -> str:
    """Fetch a URL and return its content (optionally as plain text)."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        response.raise_for_status()

        content = response.text

        if extract_text:
            # Remove script and style tags
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

            # Extract title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "No title"

            # Remove all HTML tags
            content = re.sub(r'<[^>]+>', ' ', content)

            # Clean up whitespace
            content = re.sub(r'\s+', ' ', content).strip()

            # Decode HTML entities
            import html
            content = html.unescape(content)

            result = f"📄 Title: {title}\n\nURL: {url}\n\n"

            if len(content) > MAX_CONTENT:
                content = content[:MAX_CONTENT] + "\n... (content truncated)"

            result += content
            return result

        return content[:MAX_CONTENT]

    except requests.exceptions.Timeout:
        return f"Request timed out fetching {url}"
    except requests.exceptions.ConnectionError:
        return f"Could not connect to {url}"
    except Exception as e:
        logger.error(f"URL fetch error: {e}")
        return f"Failed to fetch URL: {str(e)}"

register_tool(
    name="fetch_url",
    description="Fetch content from a web URL and extract the text. Good for reading articles or pages.",
    args_schema={"url": "string (URL to fetch)", "extract_text": "bool (optional, default true — extracts plain text from HTML)"},
    func=_fetch_url,
)
