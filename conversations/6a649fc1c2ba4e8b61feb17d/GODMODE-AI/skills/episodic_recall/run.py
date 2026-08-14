"""Episodic Recall Skill — deep search of past interactions."""

import logging

logger = logging.getLogger(__name__)


def run(query: str = "", max_results: int = 5) -> str:
    """Recall detailed past interactions from episodic memory."""
    try:
        from utils.context import search_episodic_memory

        episodes = search_episodic_memory(query or "", max_results=max_results)

        if not episodes:
            return "No past interactions found."

        lines = [f"Found {len(episodes)} past interaction(s):", ""]
        for ep in episodes:
            lines.append(f"--- {ep.get('timestamp', 'unknown')[:16]} ---")
            lines.append(f"Question: {ep.get('query', '')}")
            lines.append(f"Summary: {ep.get('summary', '')}")
            if ep.get("tools_used"):
                lines.append(f"Tools used: {', '.join(ep['tools_used'])}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Episodic recall failed: {e}")
        return f"Failed to recall: {str(e)}"
