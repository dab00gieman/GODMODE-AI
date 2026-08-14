"""Web Search Skill — DuckDuckGo instant answers."""

import requests
import logging

logger = logging.getLogger(__name__)


def run(query: str, max_results: int = 5) -> str:
    """Search the web and return formatted results."""
    try:
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

        if data.get("AbstractText"):
            results.append(f"{data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"Source: {data['AbstractURL']}")

        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text']}")
                if topic.get("FirstURL"):
                    results.append(f"  URL: {topic['FirstURL']}")

        if data.get("Answer"):
            results.append(f"Answer: {data['Answer']}")

        if data.get("Definition"):
            results.append(f"Definition: {data['Definition']}")

        if not results:
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            return f"No instant answer found. Try searching: {search_url}"

        return "\n".join(results)

    except requests.exceptions.Timeout:
        return "Search timed out. Try a shorter query."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Search failed: {str(e)}"
