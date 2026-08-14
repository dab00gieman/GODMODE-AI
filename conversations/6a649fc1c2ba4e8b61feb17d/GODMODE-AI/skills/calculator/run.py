"""Calculator Skill — safe math evaluation."""

import math
import re
import logging

logger = logging.getLogger(__name__)

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


def run(expression: str) -> str:
    """Evaluate a mathematical expression safely."""
    try:
        cleaned = expression.strip().replace("^", "**")

        if not re.match(r'^[\d\s+\-*/().,a-zA-Z_]+$', cleaned):
            return "Error: Invalid characters in expression."

        result = eval(cleaned, {"__builtins__": {}}, _SAFE_NAMES)

        if isinstance(result, float):
            if result.is_integer():
                return f"Result: {int(result)}"
            return f"Result: {result:.10g}"
        return f"Result: {result}"

    except ZeroDivisionError:
        return "Error: Division by zero."
    except SyntaxError:
        return "Error: Invalid expression syntax."
    except Exception as e:
        return f"Error: {str(e)}"
