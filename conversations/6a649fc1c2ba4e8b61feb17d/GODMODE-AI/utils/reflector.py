"""
Project GODMODE — Reflector (Hermes-inspired Learning Loop)

After completing a complex multi-step task, the agent enters a Reflective Phase:
1. Analyze what worked, what didn't
2. Extract reusable patterns from the tool sequence
3. Determine if a new skill should be created
4. If yes: write a SKILL.md encoding the solution to Firestore

Uses Firebase Firestore for skill and memory persistence.
"""

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_TOOLS_FOR_REFLECTION = 2
MAX_LEARNED_SKILLS = 50

REFLECTION_PROMPT = """You are GODMODE's Reflective Module. Your job is to analyze a completed task and determine if there's a reusable pattern worth saving as a skill.

Task analysis:
- User request: {user_message}
- Tools used (in order): {tools_sequence}
- Iterations: {iterations}
- Outcome: {outcome_summary}

Answer these questions:
1. Was this task complex enough that a similar request might come again?
2. Is there a clear, repeatable pattern in how the tools were used?
3. Would a skill encoding this sequence save time next time?

If YES to all three, create a skill in this JSON format:
{{
  "should_learn": true,
  "skill_name": "short_snake_case_name",
  "description": "One-line description of what this skill does",
  "triggers": ["keyword1", "phrase that would trigger this", ...],
  "instructions": "Natural language instructions for how to handle this type of request",
  "arguments": [
    {{"name": "arg_name", "type": "string", "required": true, "description": "what this arg is"}}
  ]
}}

If NO, respond:
{{"should_learn": false, "reason": "why not"}}

Be conservative — only create skills for genuinely reusable patterns. Don't create skills for one-off questions.
"""


def reflect_on_task(
    user_message: str,
    tool_history: List[Dict],
    iterations: int,
    outcome: str,
    model: str,
) -> Optional[Dict]:
    """
    Analyze a completed task and potentially create a learned skill.
    Returns the reflection result dict or None.
    """
    if len(tool_history) < MIN_TOOLS_FOR_REFLECTION:
        logger.info("Skipping reflection — not enough tools used")
        return None

    from utils.openrouter import send_message

    tools_desc = " -> ".join(
        f"{t['tool']}({json.dumps(t.get('args', {}))})"
        for t in tool_history
    )

    prompt = REFLECTION_PROMPT.format(
        user_message=user_message[:500],
        tools_sequence=tools_desc,
        iterations=iterations,
        outcome_summary=outcome[:500],
    )

    try:
        response, _ = send_message(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
        )

        if not response:
            logger.warning("Reflection failed — no response from model")
            return None

        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            logger.warning("Reflection response had no JSON")
            return None

        result = json.loads(json_match.group())

        if not result.get("should_learn"):
            logger.info(f"Reflection decided not to learn: {result.get('reason', 'no reason')}")
            return result

        # Create the learned skill
        from utils.skills import create_learned_skill, list_skills

        learned_count = sum(1 for s in list_skills() if s.source == "learned")
        if learned_count >= MAX_LEARNED_SKILLS:
            logger.warning(f"Max learned skills ({MAX_LEARNED_SKILLS}) reached")
            return {"should_learn": False, "reason": "skill library full"}

        skill_name = result.get("skill_name", "")
        existing_names = [s.name for s in list_skills()]
        if skill_name in existing_names:
            logger.info(f"Skill '{skill_name}' already exists — skipping")
            return {"should_learn": False, "reason": "skill already exists"}

        success = create_learned_skill(
            name=skill_name,
            description=result.get("description", ""),
            instructions=result.get("instructions", ""),
            triggers=result.get("triggers", []),
            arguments=result.get("arguments", []),
        )

        if success:
            logger.info(f"Learned skill created: {skill_name}")
            return result
        else:
            logger.error("Failed to create learned skill")
            return {"should_learn": False, "reason": "storage failed"}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse reflection: {e}")
        return None
    except Exception as e:
        logger.error(f"Reflection failed: {e}")
        return None


# ──────────────────────────── MEMORY CONSOLIDATION ────────────────────────────

def consolidate_memory(
    user_message: str,
    response: str,
    tool_history: List[Dict],
) -> bool:
    """
    After a task, extract important facts/preferences and append to MEMORY.md.
    Uses Firestore-backed MEMORY.md storage.
    """
    from utils.context import append_to_memory_md
    from datetime import datetime

    if len(user_message) < 20 or len(response) < 50:
        return False

    memory_entry = f"\n## {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}\n"
    memory_entry += f"Q: {user_message[:200]}\n"
    memory_entry += f"A: {response[:300]}\n"
    if tool_history:
        tools = ", ".join(t["tool"] for t in tool_history)
        memory_entry += f"Tools: {tools}\n"

    return append_to_memory_md(memory_entry)
