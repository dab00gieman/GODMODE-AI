"""Memory Search Skill — search long-term and episodic memory."""

import logging
import json

logger = logging.getLogger(__name__)


def run(query: str) -> str:
    """Search MEMORY.md and episodic memory for relevant content."""
    results = []

    # Search MEMORY.md
    try:
        from utils.context import read_memory_md
        memory = read_memory_md()
        if memory:
            query_words = set(query.lower().split())
            memory_lines = memory.split("\n")
            for line in memory_lines:
                if any(word in line.lower() for word in query_words):
                    results.append(f"[MEMORY] {line.strip()}")
    except Exception as e:
        logger.error(f"MEMORY.md search failed: {e}")

    # Search episodic memory
    try:
        from utils.context import search_episodic_memory
        episodes = search_episodic_memory(query, max_results=5)
        for ep in episodes:
            results.append(
                f"[EPISODE {ep.get('timestamp', '')[:10]}] "
                f"Q: {ep.get('query', '')[:100]} | "
                f"A: {ep.get('summary', '')[:200]}"
            )
    except Exception as e:
        logger.error(f"Episodic search failed: {e}")

    if not results:
        return f"No memories found for: '{query}'"

    return "\n".join(results[:10])
