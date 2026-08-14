"""
Project GODMODE — Task Planner
Decomposes complex requests into structured execution plans.
Works with the agent loop to determine which tools to use and in what order.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from utils.openrouter import send_message
from utils.tools import get_tools_description, list_tools

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are GODMODE-Planner, a task planning module.

Given a user request, break it down into a structured execution plan.
For each step, determine:
1. What needs to be done
2. Which tool to use (if any)
3. What the expected outcome is

Respond in this JSON format:
{
  "needs_tools": true/false,
  "steps": [
    {
      "step": 1,
      "action": "description of what to do",
      "tool": "tool_name or null",
      "args": {"param": "value"},
      "expected": "what we expect to learn"
    }
  ],
  "complexity": "simple|moderate|complex"
}

If the request is a simple question that doesn't need tools, return:
{"needs_tools": false, "steps": [], "complexity": "simple"}

Available tools:
"""

def plan_task(
    user_message: str,
    history: List[Dict],
    model: str,
) -> Dict:
    """
    Analyze a user request and create an execution plan.
    Returns a structured plan dict.
    """
    tools_desc = get_tools_description()
    system = PLANNER_SYSTEM_PROMPT + "\n" + tools_desc

    messages = [
        {"role": "system", "content": system},
    ]

    # Add recent context
    for msg in history[-5:]:
        messages.append(msg)

    messages.append({
        "role": "user",
        "content": f"Plan this request: {user_message}"
    })

    try:
        response, _ = send_message(
            model=model,
            messages=messages,
            temperature=0.2,  # Low temp for structured planning
            max_tokens=1024,
        )

        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group())
            logger.info(f"Plan created: {plan.get('complexity', 'unknown')}, {len(plan.get('steps', []))} steps")
            return plan

        # Fallback: no structured plan, treat as simple
        return {"needs_tools": False, "steps": [], "complexity": "simple"}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse plan: {e}")
        return {"needs_tools": False, "steps": [], "complexity": "simple"}
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {"needs_tools": False, "steps": [], "complexity": "simple"}


# ──────────────────────────── QUICK CLASSIFIER ────────────────────────────

# Lightweight classifier — determines if agent mode is needed
# without an LLM call (faster path for simple messages)

TOOL_KEYWORDS = {
    "web_search": ["search", "find", "look up", "what is", "who is", "tell me about", "research"],
    "calculator": ["calculate", "compute", "math", "plus", "minus", "times", "divided", "sqrt", "solve"],
    "code_runner": ["run code", "execute", "python", "code:", "```", "print("],
    "summarize": ["summarize", "tldr", "key points", "shorten"],
    "weather": ["weather", "temperature", "forecast", "how hot", "how cold", "raining"],
    "fetch_url": ["fetch", "read url", "read this page", "read this article", "http"],
    "get_time": ["what time", "current time", "what date", "what day", "timezone"],
    "translate": ["translate", "in french", "in spanish", "in yoruba", "in hausa", "in igbo", "in german"],
}

def quick_classify(message: str) -> Tuple[bool, List[str]]:
    """
    Quick heuristic classification of whether tools are needed.
    Returns (needs_tools, list_of_likely_tools).
    """
    msg_lower = message.lower()
    needed_tools = []

    for tool_name, keywords in TOOL_KEYWORDS.items():
        for keyword in keywords:
            if keyword in msg_lower:
                needed_tools.append(tool_name)
                break

    # Math expressions
    import re
    if re.search(r'[\d\)]\s*[+\-*/^]\s*[\d(]', message):
        if "calculator" not in needed_tools:
            needed_tools.append("calculator")

    # URLs
    if "http://" in msg_lower or "https://" in msg_lower:
        if "fetch_url" not in needed_tools:
            needed_tools.append("fetch_url")

    return (len(needed_tools) > 0, list(set(needed_tools)))
