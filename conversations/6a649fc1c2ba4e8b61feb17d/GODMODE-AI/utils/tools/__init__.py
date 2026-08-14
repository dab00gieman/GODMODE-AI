"""
Project GODMODE — Tool Registry
Central registry for all agent tools. Each tool is a callable with
a name, description, and argument schema.
"""

import logging
import json
import re
from typing import Dict, Any, Callable, Optional, List

logger = logging.getLogger(__name__)

# ──────────────────────────── TOOL REGISTRY ────────────────────────────

_TOOLS: Dict[str, Dict] = {}

def register_tool(
    name: str,
    description: str,
    args_schema: Dict[str, str],
    func: Callable,
):
    """Register a tool in the global registry."""
    _TOOLS[name] = {
        "name": name,
        "description": description,
        "args": args_schema,
        "func": func,
    }
    logger.info(f"Registered tool: {name}")

def get_tool(name: str) -> Optional[Dict]:
    """Get a tool by name."""
    return _TOOLS.get(name)

def list_tools() -> List[str]:
    """List all registered tool names."""
    return list(_TOOLS.keys())

def get_tools_description() -> str:
    """Generate a description of all tools for the LLM system prompt."""
    lines = []
    for name, tool in _TOOLS.items():
        args_str = ", ".join(f"{k}: {v}" for k, v in tool["args"].items())
        lines.append(f"- {name}({args_str}) — {tool['description']}")
    return "\n".join(lines)

def execute_tool(name: str, args: Dict[str, Any]) -> Any:
    """Execute a registered tool by name with the given arguments."""
    tool = get_tool(name)
    if not tool:
        raise ValueError(f"Unknown tool: {name}. Available: {list_tools()}")
    return tool["func"](**args)

def parse_tool_call(text: str) -> Optional[Dict]:
    """
    Parse a [TOOL_CALL]...[/TOOL_CALL] block from LLM output.
    Returns {"tool": name, "args": {}} or None if no call found.
    """
    pattern = r'\[TOOL_CALL\]\s*(\{.*?\})\s*\[/TOOL_CALL\]'
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        # Also try to find bare JSON tool calls
        pattern2 = r'```json\s*(\{.*?"tool".*?\})\s*```'
        match2 = re.search(pattern2, text, re.DOTALL)
        if match2:
            match = match2

    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        if "tool" not in data:
            return None
        if "args" not in data:
            data["args"] = {}
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tool call: {e}")
        return None


# ──────────────────────────── AUTO-REGISTER ALL TOOLS ────────────────────────────

def _auto_register():
    """Import all tool modules to trigger their registration."""
    try:
        from utils.tools import web_search
        from utils.tools import calculator
        from utils.tools import code_runner
        from utils.tools import summarizer
        from utils.tools import weather
        from utils.tools import url_fetcher
        from utils.tools import time_tools
        from utils.tools import translator
    except ImportError as e:
        logger.error(f"Failed to load tools: {e}")

_auto_register()
