"""
Project GODMODE — Skill System (OpenClaw/Hermes-inspired)

Each skill is a folder containing:
  SKILL.md  — YAML frontmatter (name, description, triggers, arguments) + natural language instructions
  run.py    — executable function

Skills are auto-discovered from:
  1. skills/ directory (bundled, read-only on Vercel)
  2. Firestore (learned skills created by the reflector)

The SKILL.md content gets injected into the system prompt so the LLM knows what tools exist.
The run.py provides the actual execution.

Uses Firebase Firestore for learned skill persistence (not Redis).

Task 7: Supports native OpenAI-compatible function calling via build_tools_array().
"""

import os
import re
import json
import logging
import importlib
import importlib.util
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")
SOUL_DIR = os.path.join(PROJECT_ROOT, "soul")


# ──────────────────────────── SKILL DATA MODEL ────────────────────────────

class Skill:
    """Represents a single skill with metadata and execution function."""

    def __init__(
        self,
        name: str,
        description: str,
        instructions: str,
        arguments: List[Dict],
        triggers: List[str],
        func: Optional[Callable] = None,
        source: str = "bundled",
        version: str = "1.0.0",
    ):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.arguments = arguments
        self.triggers = triggers
        self.func = func
        self.source = source
        self.version = version

    def to_prompt_text(self) -> str:
        """Generate the text injected into the system prompt for this skill."""
        args_str = ", ".join(
            f'{a["name"]}: {a.get("type", "string")}'
            + (" (required)" if a.get("required") else " (optional)")
            for a in self.arguments
        )
        return f"- {self.name}({args_str}) — {self.description}"

    def to_tool_spec(self) -> str:
        """Full tool specification including instructions."""
        spec = f"### Skill: {self.name}\n"
        spec += f"Description: {self.description}\n"
        spec += f"Source: {self.source}\n"
        if self.arguments:
            spec += "Arguments:\n"
            for arg in self.arguments:
                spec += f"  - {arg['name']}: {arg.get('type', 'string')}"
                if arg.get("required"):
                    spec += " (required)"
                spec += f" — {arg.get('description', '')}\n"
        spec += f"\nInstructions:\n{self.instructions}\n"
        return spec

    def to_openai_tool_spec(self) -> Dict:
        """
        Convert skill metadata to OpenAI-compatible function-calling tool spec.
        Used for native function calling via OpenRouter (Task 7).
        """
        properties = {}
        required = []
        for arg in self.arguments:
            arg_name = arg.get("name", "input")
            arg_type = arg.get("type", "string")
            # Map Python types to JSON schema types
            json_type = "string"
            if arg_type in ("int", "integer", "float", "number"):
                json_type = "number"
            elif arg_type in ("bool", "boolean"):
                json_type = "boolean"
            elif arg_type in ("list", "array"):
                json_type = "array"
            elif arg_type in ("dict", "object"):
                json_type = "object"

            properties[arg_name] = {
                "type": json_type,
                "description": arg.get("description", ""),
            }
            if arg.get("default") is not None:
                properties[arg_name]["default"] = arg["default"]
            if arg.get("required"):
                required.append(arg_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def execute(self, **kwargs) -> Any:
        """Run the skill's function with the given arguments."""
        if not self.func:
            return f"Skill '{self.name}' has no executable function (learned skill with no run.py)."
        return self.func(**kwargs)

    def to_dict(self) -> Dict:
        """Serialize for Firestore storage."""
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "arguments": self.arguments,
            "triggers": self.triggers,
            "source": self.source,
            "version": self.version,
        }


# ──────────────────────────── SKILL REGISTRY ────────────────────────────

_REGISTRY: Dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    """Register a skill in the global registry."""
    _REGISTRY[skill.name] = skill
    logger.info(f"Registered skill [{skill.source}]: {skill.name}")


def get_skill(name: str) -> Optional[Skill]:
    return _REGISTRY.get(name)


def list_skills() -> List[Skill]:
    return list(_REGISTRY.values())


def list_skill_names() -> List[str]:
    return list(_REGISTRY.keys())


# ──────────────────────────── SKILL.md PARSER ────────────────────────────

def parse_skill_md(filepath: str) -> Dict:
    """
    Parse a SKILL.md file with YAML frontmatter + markdown body.
    Returns {"name", "description", "triggers", "arguments", "instructions", "version"}.
    """
    with open(filepath, "r") as f:
        content = f.read()

    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"No YAML frontmatter found in {filepath}")

    frontmatter_text = fm_match.group(1)
    body = fm_match.group(2).strip()

    # Simple YAML parser (avoids pyyaml dependency)
    meta = {"triggers": [], "arguments": []}
    current_key = None
    in_list = False
    in_args = False
    current_arg = {}

    for line in frontmatter_text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("- ") and in_list:
            item = stripped[2:].strip().strip('"').strip("'")
            if in_args:
                if ":" in item and not item.startswith("{"):
                    k, v = item.split(":", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in ("name", "type", "description", "required", "default"):
                        if k == "required":
                            current_arg[k] = v.lower() in ("true", "yes", "1")
                        elif k == "default":
                            current_arg[k] = v
                        else:
                            current_arg[k] = v
                elif item == "---":
                    if current_arg:
                        meta["arguments"].append(current_arg)
                        current_arg = {}
            else:
                meta[current_key].append(item)
            continue

        if ":" in stripped and not stripped.startswith("- "):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if current_arg and in_args:
                meta["arguments"].append(current_arg)
                current_arg = {}

            if key == "triggers":
                meta["triggers"] = []
                current_key = "triggers"
                in_list = True
                in_args = False
                if value:
                    meta["triggers"].append(value)
            elif key == "arguments":
                meta["arguments"] = []
                current_key = "arguments"
                in_list = True
                in_args = True
            elif key in ("name", "description", "version", "author", "source"):
                meta[key] = value
                in_list = False
                in_args = False
            else:
                meta[key] = value
                in_list = False
                in_args = False

    if current_arg and in_args:
        meta["arguments"].append(current_arg)

    meta["instructions"] = body
    return meta


# ──────────────────────────── LOAD RUN.PY ────────────────────────────

def load_skill_function(skill_dir: str, skill_name: str) -> Optional[Callable]:
    """Load the run() function from a skill's run.py file."""
    run_path = os.path.join(skill_dir, "run.py")
    if not os.path.exists(run_path):
        logger.warning(f"No run.py for skill '{skill_name}' at {run_path}")
        return None

    try:
        spec = importlib.util.spec_from_file_location(f"skills.{skill_name}.run", run_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "run"):
            return module.run
        logger.error(f"run.py for '{skill_name}' has no 'run' function")
        return None
    except Exception as e:
        logger.error(f"Failed to load run.py for '{skill_name}': {e}")
        return None


# ──────────────────────────── AUTO-DISCOVERY ────────────────────────────

def discover_bundled_skills() -> None:
    """Scan the skills/ directory and register all skills with SKILL.md files."""
    if not os.path.isdir(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return

    for entry in os.listdir(SKILLS_DIR):
        skill_dir = os.path.join(SKILLS_DIR, entry)
        skill_md = os.path.join(skill_dir, "SKILL.md")

        if not os.path.isdir(skill_dir) or not os.path.exists(skill_md):
            continue

        try:
            meta = parse_skill_md(skill_md)
            func = load_skill_function(skill_dir, meta.get("name", entry))

            skill = Skill(
                name=meta.get("name", entry),
                description=meta.get("description", ""),
                instructions=meta.get("instructions", ""),
                arguments=meta.get("arguments", []),
                triggers=meta.get("triggers", []),
                func=func,
                source="bundled",
                version=meta.get("version", "1.0.0"),
            )
            register_skill(skill)
        except Exception as e:
            logger.error(f"Failed to load skill '{entry}': {e}")


def load_learned_skills() -> None:
    """Load learned skills from Firestore (created by the reflector)."""
    try:
        from utils.memory import get_all_learned_skills
        skills = get_all_learned_skills()
        for data in skills:
            skill = Skill(
                name=data.get("name", ""),
                description=data.get("description", ""),
                instructions=data.get("instructions", ""),
                arguments=data.get("arguments", []),
                triggers=data.get("triggers", []),
                func=None,
                source="learned",
                version=data.get("version", "1.0.0"),
            )
            if skill.name and skill.name not in _REGISTRY:
                register_skill(skill)
        if skills:
            logger.info(f"Loaded {len(skills)} learned skills from Firestore")
    except Exception as e:
        logger.warning(f"Could not load learned skills: {e}")


def initialize_skills() -> None:
    """Initialize the entire skill registry — bundled + learned."""
    _REGISTRY.clear()
    discover_bundled_skills()
    load_learned_skills()
    bundled_count = sum(1 for s in _REGISTRY.values() if s.source == "bundled")
    learned_count = sum(1 for s in _REGISTRY.values() if s.source == "learned")
    logger.info(f"Skill registry initialized: {len(_REGISTRY)} skills ({bundled_count} bundled, {learned_count} learned)")


# ──────────────────────────── SKILL DESCRIPTIONS ────────────────────────────

def get_skills_prompt_section() -> str:
    """Generate the 'Available Skills' section for the system prompt."""
    if not _REGISTRY:
        return "No tools available."

    lines = ["## Available Skills (Tools)", ""]
    for skill in _REGISTRY.values():
        badge = "📦" if skill.source == "learned" else "🔧"
        lines.append(f"{badge} {skill.to_prompt_text()}")
    return "\n".join(lines)


def get_full_skills_context() -> str:
    """Generate full skill instructions for the system prompt (Hermes-style)."""
    if not _REGISTRY:
        return ""

    lines = ["## Skill Instructions", ""]
    for skill in _REGISTRY.values():
        lines.append(skill.to_tool_spec())
    return "\n".join(lines)


def find_skills_for_message(message: str) -> List[Skill]:
    """Find skills whose triggers match the user's message."""
    msg_lower = message.lower()
    matched = []
    for skill in _REGISTRY.values():
        for trigger in skill.triggers:
            if trigger in msg_lower:
                if skill not in matched:
                    matched.append(skill)
                break
    return matched


# ──────────────────────────── NATIVE FUNCTION CALLING (Task 7) ────────────────────────────

def build_tools_array() -> List[Dict]:
    """
    Build an OpenAI-compatible tools array for native function calling.
    Used in the API request payload's 'tools' parameter.
    """
    tools = []
    for skill in _REGISTRY.values():
        if skill.func:  # Only include skills with executable functions
            tools.append(skill.to_openai_tool_spec())
    return tools


def parse_native_tool_calls(message: Dict) -> List[Dict]:
    """
    Parse native tool calls from an OpenRouter API response message.
    Returns list of {"tool": name, "args": {}} dicts.
    """
    tool_calls = message.get("tool_calls")
    if not tool_calls:
        return []

    parsed = []
    for tc in tool_calls:
        try:
            func_data = tc.get("function", {})
            name = func_data.get("name", "")
            args_str = func_data.get("arguments", "{}")
            args = json.loads(args_str) if args_str else {}
            if name:
                parsed.append({"tool": name, "args": args})
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse native tool call: {e}")
    return parsed


# ──────────────────────────── EXECUTE ────────────────────────────

def execute_skill(name: str, args: Dict[str, Any]) -> Any:
    """Execute a skill by name with the given arguments."""
    skill = get_skill(name)
    if not skill:
        raise ValueError(f"Unknown skill: '{name}'. Available: {list_skill_names()}")
    return skill.execute(**args)


# ──────────────────────────── TOOL CALL PARSING (text fallback) ────────────────────────────

def parse_tool_call(text: str) -> Optional[Dict]:
    """
    Parse a tool/skill call from LLM output text.
    Supports [TOOL_CALL] and ```json formats.
    This is the FALLBACK path for models that don't support native function calling.
    """
    pattern = r'\[TOOL_CALL\]\s*(\{.*?\})\s*\[/TOOL_CALL\]'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        pattern2 = r'```json\s*(\{.*?"tool".*?\})\s*```'
        match = re.search(pattern2, text, re.DOTALL)

    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        if "tool" not in data and "skill" in data:
            data["tool"] = data["skill"]
        if "tool" not in data:
            return None
        if "args" not in data:
            data["args"] = {}
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tool call: {e}")
        return None


# ──────────────────────────── LEARNED SKILL CREATION (Firestore) ────────────────────────────

def create_learned_skill(
    name: str,
    description: str,
    instructions: str,
    triggers: List[str],
    arguments: List[Dict] = None,
) -> bool:
    """Store a newly learned skill in Firestore."""
    try:
        from utils.memory import save_learned_skill
        skill_data = {
            "name": name,
            "description": description,
            "instructions": instructions,
            "arguments": arguments or [],
            "triggers": triggers,
            "source": "learned",
            "version": "1.0.0",
        }

        success = save_learned_skill(name, skill_data)
        if not success:
            logger.warning("Cannot save learned skill — Firestore unavailable")
            return False

        # Also register in the live registry
        skill = Skill(
            name=name,
            description=description,
            instructions=instructions,
            arguments=arguments or [],
            triggers=triggers,
            func=None,
            source="learned",
        )
        register_skill(skill)

        logger.info(f"Learned skill created: {name}")
        return True
    except Exception as e:
        logger.error(f"Failed to create learned skill: {e}")
        return False


def delete_learned_skill(name: str) -> bool:
    """Delete a learned skill from Firestore."""
    try:
        from utils.memory import delete_learned_skill_db
        success = delete_learned_skill_db(name)
        if success and name in _REGISTRY:
            del _REGISTRY[name]
        return success
    except Exception as e:
        logger.error(f"Failed to delete learned skill: {e}")
        return False
