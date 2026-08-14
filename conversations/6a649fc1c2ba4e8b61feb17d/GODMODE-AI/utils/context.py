"""
Project GODMODE — Context Builder (OpenClaw/Hermes-style)

Assembles the full system prompt from:
  1. SOUL.md     — personality, values, boundaries (cognitive anchor)
  2. IDENTITY.md — name, avatar, version
  3. USER.md     — user profile (preferences, timezone)
  4. MEMORY.md   — long-term curated memory (relevant snippets)
  5. Skills      — available tools + full instructions
  6. Episodic    — relevant past episodes (cross-session recall)
  7. History     — conversation history (with token budgeting)

Uses Firebase Firestore for persistent storage (MEMORY.md, episodic memory).
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUL_DIR = os.path.join(PROJECT_ROOT, "soul")

# Token budget (approximate: 1 token ≈ 4 chars)
MAX_CONTEXT_CHARS = 120_000
MIN_HISTORY_CHARS = 4_000
MAX_MEMORY_CHARS = 6_000
MAX_SYSTEM_CHARS = 20_000

# ──────────────────────────── FILE READERS ────────────────────────────

_file_cache: Dict[str, str] = {}

def _read_file(path: str) -> str:
    """Read a file with caching."""
    if path in _file_cache:
        return _file_cache[path]
    try:
        with open(path, "r") as f:
            content = f.read()
        _file_cache[path] = content
        return content
    except FileNotFoundError:
        logger.warning(f"File not found: {path}")
        return ""
    except Exception as e:
        logger.error(f"Error reading {path}: {e}")
        return ""


def read_soul() -> str:
    return _read_file(os.path.join(SOUL_DIR, "SOUL.md"))


def read_identity() -> str:
    return _read_file(os.path.join(SOUL_DIR, "IDENTITY.md"))


def read_user_profile(chat_id: int) -> str:
    """Read user profile. Static template first, then overlay with Firestore prefs."""
    template = _read_file(os.path.join(SOUL_DIR, "USER.md"))

    try:
        from utils.memory import get_prefs
        prefs = get_prefs(chat_id)

        if prefs:
            lines = [template, "", "## Detected Preferences", ""]
            if prefs.get("model"):
                from utils.config import get_model_label
                lines.append(f"Preferred model: {get_model_label(prefs['model'])}")
            if prefs.get("temperature") is not None:
                lines.append(f"Creativity: {prefs['temperature']}")
            if prefs.get("agent_enabled") is not None:
                lines.append(f"Agent mode: {'on' if prefs['agent_enabled'] else 'off'}")
            return "\n".join(lines)
    except Exception:
        pass

    return template


# ──────────────────────────── MEMORY RETRIEVAL (Firebase) ────────────────────────────

def read_memory_md() -> str:
    """Read MEMORY.md from Firestore."""
    try:
        from utils.memory import get_memory_md
        return get_memory_md()
    except Exception as e:
        logger.warning(f"Could not read MEMORY.md: {e}")
        return ""


def search_episodic_memory(query: str, max_results: int = 3) -> List[Dict]:
    """Search episodic memory via Firestore."""
    try:
        from utils.memory import search_episodic
        return search_episodic(query, max_results=max_results)
    except Exception as e:
        logger.warning(f"Episodic memory search failed: {e}")
        return []


def format_episodic_memories(episodes: List[Dict]) -> str:
    """Format episodic memories for inclusion in system prompt."""
    if not episodes:
        return ""

    lines = ["## Past Interactions (Relevant)", ""]
    for ep in episodes:
        tools = ", ".join(ep.get("tools_used", [])) if ep.get("tools_used") else "none"
        lines.append(f"- [{ep.get('timestamp', 'unknown')}] Q: {ep.get('query', '')[:100]}")
        lines.append(f"  A: {ep.get('summary', '')[:200]}")
        lines.append(f"  Tools used: {tools}")
    return "\n".join(lines)


# ──────────────────────────── CONTEXT BUILDER ────────────────────────────

def build_context(
    chat_id: int,
    history: List[Dict],
    user_message: str,
    include_skills: bool = True,
    include_episodic: bool = True,
    godmode: bool = False,
) -> List[Dict]:
    """
    Build the full message list for the LLM.
    Returns messages list ready for the OpenRouter API (system prompt first, then history).
    """
    from utils.skills import get_skills_prompt_section, get_full_skills_context

    # ──── Assemble system prompt ────
    system_parts = []

    # 1. SOUL — always injected (the cognitive anchor)
    soul = read_soul()
    if soul:
        system_parts.append(soul)

    # 2. IDENTITY
    identity = read_identity()
    if identity:
        system_parts.append(f"\n---\n\n# IDENTITY\n{identity}")

    # 3. USER PROFILE
    user_profile = read_user_profile(chat_id)
    if user_profile:
        system_parts.append(f"\n---\n\n# USER PROFILE\n{user_profile}")

    # 4. SKILLS — available tools
    if include_skills:
        skills_section = get_skills_prompt_section()
        if skills_section:
            system_parts.append(f"\n---\n\n{skills_section}")

            # Full skill instructions (Hermes-style injection)
            full_instructions = get_full_skills_context()
            if full_instructions and len(full_instructions) < 8000:
                system_parts.append(f"\n{full_instructions}")

    # 5. MEMORY — long-term curated memory
    memory = read_memory_md()
    if memory:
        if len(memory) > MAX_MEMORY_CHARS:
            memory = memory[:MAX_MEMORY_CHARS] + "\n... (memory truncated)"
        system_parts.append(f"\n---\n\n# MEMORY\n{memory}")

    # 6. EPISODIC — relevant past interactions
    if include_episodic:
        episodes = search_episodic_memory(user_message)
        episodic_text = format_episodic_memories(episodes)
        if episodic_text:
            system_parts.append(f"\n---\n\n{episodic_text}")

    # 6.5. GODMODE override — injected when enabled for this user
    if godmode:
        from utils.config import get_godmode_prompt
        system_parts.append(get_godmode_prompt())

    # 7. Tool call instructions
    system_parts.append(
        "\n---\n\n## Tool Use\n"
        "To call a tool, use this format:\n\n"
        "[TOOL_CALL]\n"
        '{"tool": "tool_name", "args": {"param": "value"}}\n'
        "[/TOOL_CALL]\n\n"
        "Call only ONE tool per turn. After receiving tool results, "
        "either call another tool or give your final answer.\n"
        "If no tools are needed, answer directly."
    )

    # Join system prompt
    system_prompt = "\n".join(system_parts)

    # Enforce system prompt size limit
    if len(system_prompt) > MAX_SYSTEM_CHARS:
        system_prompt = system_prompt[:MAX_SYSTEM_CHARS] + "\n... (context truncated)"
        logger.warning(f"System prompt truncated to {MAX_SYSTEM_CHARS} chars")

    # ──── Assemble messages ────
    messages = [{"role": "system", "content": system_prompt}]

    # ──── History with token budgeting ────
    system_chars = len(system_prompt)
    remaining_budget = MAX_CONTEXT_CHARS - system_chars
    history_budget = max(remaining_budget - 4096, MIN_HISTORY_CHARS)

    # Trim history from oldest if needed
    trimmed_history = []
    history_chars = 0
    for msg in reversed(history):
        msg_chars = len(msg.get("content", ""))
        if history_chars + msg_chars > history_budget:
            break
        trimmed_history.insert(0, msg)
        history_chars += msg_chars

    if len(trimmed_history) < len(history):
        logger.info(f"History trimmed: {len(history)} -> {len(trimmed_history)} messages")

    messages.extend(trimmed_history)

    return messages


# ──────────────────────────── EPISODIC STORAGE ────────────────────────────

def store_episode(
    chat_id: int,
    query: str,
    summary: str,
    tools_used: List[str],
    topics: List[str] = None,
) -> bool:
    """Store an interaction in episodic memory via Firestore."""
    try:
        from utils.memory import store_episodic
        return store_episodic(chat_id, query, summary, tools_used, topics)
    except Exception as e:
        logger.error(f"Failed to store episode: {e}")
        return False


# ──────────────────────────── MEMORY.md MANAGEMENT ────────────────────────────

def update_memory_md(new_content: str) -> bool:
    """Update the MEMORY.md content in Firestore."""
    try:
        from utils.memory import set_memory_md
        return set_memory_md(new_content)
    except Exception as e:
        logger.error(f"Failed to update MEMORY.md: {e}")
        return False


def append_to_memory_md(content: str) -> bool:
    """Append to MEMORY.md in Firestore."""
    try:
        from utils.memory import append_memory_md
        return append_memory_md(content)
    except Exception as e:
        logger.error(f"Failed to append to MEMORY.md: {e}")
        return False
