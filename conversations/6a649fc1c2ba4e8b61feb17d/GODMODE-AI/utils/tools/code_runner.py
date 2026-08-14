"""
Tool: Code Runner
Executes Python code in a restricted sandbox. Limited builtins, no file/network access.
"""

import logging
from utils.tools import register_tool

logger = logging.getLogger(__name__)

# Safe builtins for code execution
_SAFE_BUILTINS = {
    "print": print, "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter, "sorted": sorted,
    "reversed": reversed, "sum": sum, "min": min, "max": max,
    "abs": abs, "round": round, "any": any, "all": all,
    "int": int, "float": float, "str": str, "bool": bool, "list": list,
    "dict": dict, "set": set, "tuple": tuple, "type": type,
    "isinstance": isinstance, "repr": repr, "format": format,
    "True": True, "False": False, "None": None,
}

MAX_OUTPUT = 3000
MAX_LINES = 50

def _run_code(code: str) -> str:
    """Execute Python code safely and return stdout/stderr."""
    import io
    import sys

    # Limit code size
    if len(code) > 5000:
        return "Error: Code too long (max 5000 characters)."

    # Block dangerous imports
    blocked = ["import os", "import subprocess", "import sys", "import socket",
               "import urllib", "import requests", "__import__", "eval(",
               "exec(", "open(", "file(", "compile(", "globals()"]
    for b in blocked:
        if b in code:
            return f"Error: Blocked operation '{b}' is not allowed in the sandbox."

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    try:
        # Restricted globals
        safe_globals = {"__builtins__": _SAFE_BUILTINS}

        # Allow basic imports from a whitelist
        exec(code, safe_globals)

        output = sys.stdout.getvalue()
        error = sys.stderr.getvalue()

        if not output and not error:
            return "Code executed successfully (no output)."

        result = ""
        if output:
            result += output[:MAX_OUTPUT]
            if len(output) > MAX_OUTPUT:
                result += "\n... (output truncated)"

        if error:
            result += f"\n[stderr]: {error[:500]}"

        return result.strip() or "Code executed (no output)."

    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:500]}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

register_tool(
    name="code_runner",
    description="Execute Python code in a sandbox. Can print output. No file/network access. Max 5000 chars.",
    args_schema={"code": "string (Python code to execute)"},
    func=_run_code,
)
