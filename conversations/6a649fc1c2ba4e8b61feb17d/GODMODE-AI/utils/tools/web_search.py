"""
Tool: Web Search
Searches the web using DuckDuckGo's instant answer API (free, no API key needed).
"""

import requests
import logging
from utils.tools import register_tool

logger = logging.getLogger(__name__)

def _web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return formatted results."""
    try:
        # DuckDuckGo Instant Answer API
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        results = []

        # Abstract (main answer)
        if data.get("AbstractText"):
            results.append(f"📖 {data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"Source: {data['AbstractURL']}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"• {topic['Text']}")
                if topic.get("FirstURL"):
                    results.append(f"  URL: {topic['FirstURL']}")

        # Answer (if available)
        if data.get("Answer"):
            results.append(f"💡 {data['Answer']}")

        # Definition
        if data.get("Definition"):
            results.append(f"📚 {data['Definition']}")

        if not results:
            # Fallback: try a simple search URL
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            return f"No instant answer found. Try searching: {search_url}"

        return "\n".join(results)

    except requests.exceptions.Timeout:
        return "Search timed out. Try again with a shorter query."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Search failed: {str(e)}"

register_tool(
    name="web_search",
    description="Search the web for information. Returns text results from DuckDuckGo.",
    args_schema={"query": "string (search query)", "max_results": "int (optional, default 5)"},
    func=_web_search,
)
