"""
Tool: Calculator
Safe mathematical expression evaluator. Supports +, -, *, /, ^, sqrt, sin, cos, etc.
"""

import math
import re
import logging
from utils.tools import register_tool

logger = logging.getLogger(__name__)

# Allowed names in the eval environment
_SAFE_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "pow": pow, "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "pi": math.pi, "e": math.e,
    "ceil": math.ceil, "floor": math.floor,
    "factorial": math.factorial, "gcd": math.gcd,
    "radians": math.radians, "degrees": math.degrees,
    "exp": math.exp, "log2": math.log2,
}

def _calculate(expression: str) -> str:
    """Evaluate a mathematical expression safely."""
    try:
        # Sanitize: only allow math characters and function names
        cleaned = expression.strip().replace("^", "**")

        # Verify only safe characters
        if not re.match(r'^[\d\s+\-*/().,a-zA-Z_]+$', cleaned):
            return "Error: Invalid characters in expression."

        # Replace function names with math equivalents
        result = eval(cleaned, {"__builtins__": {}}, _SAFE_NAMES)

        # Format result
        if isinstance(result, float):
            if result.is_integer():
                return f"Result: {int(result)}"
            return f"Result: {result:.10g}"
        return f"Result: {result}"

    except ZeroDivisionError:
        return "Error: Division by zero."
    except SyntaxError:
        return f"Error: Invalid expression syntax."
    except Exception as e:
        return f"Error: {str(e)}"

register_tool(
    name="calculator",
    description="Evaluate a mathematical expression. Supports +, -, *, /, sqrt, sin, cos, log, pi, e, etc.",
    args_schema={"expression": "string (math expression, e.g. '2 + 2 * 3', 'sqrt(144)', 'sin(pi/2)')"},
    func=_calculate,
)
