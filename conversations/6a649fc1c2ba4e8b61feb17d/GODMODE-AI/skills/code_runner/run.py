"""
Code Runner Skill — Safe Python evaluation via AST whitelisting.

SECURITY: This skill does NOT use exec() or eval(). Instead, it parses user code
into an AST and evaluates only whitelisted node types. This prevents sandbox-escape
techniques like walking __class__.__base__.__subclasses__() to reach dangerous builtins.

Allowed:
  - Math: +, -, *, /, //, %, **, comparisons
  - Builtins: abs, round, min, max, sum, len, range, sorted, reversed, zip, map, filter, enumerate, any, all
  - Types: int, float, str, bool, list, dict, set, tuple
  - String methods: .upper(), .lower(), .strip(), .split(), .join(), .replace(), .find(), .count(), .startswith(), .endswith(), .format()
  - List/dict methods: .append(), .get(), .keys(), .values(), .items()
  - f-strings and string formatting
  - List comprehensions and generator expressions (with safe ops only)

Blocked:
  - All imports (import, from...import)
  - Attribute access to dunder methods (__class__, __base__, __subclasses__, __builtins__, __globals__, etc.)
  - exec(), eval(), compile(), open(), __import__()
  - Subprocess, sockets, file I/O
  - Lambda (to prevent closures that capture dangerous state)
  - Global/nonlocal statements
"""

import ast
import logging
import math
import statistics

logger = logging.getLogger(__name__)

MAX_CODE_LENGTH = 5000
MAX_OUTPUT = 3000
MAX_EXECUTION_NODES = 5000  # Prevent AST bombs

# Whitelisted builtins (no I/O, no code execution, no introspection)
_SAFE_BUILTINS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "len": len, "range": range, "sorted": sorted, "reversed": reversed,
    "zip": zip, "map": map, "filter": filter, "enumerate": enumerate,
    "any": any, "all": all, "bool": bool, "int": int, "float": float,
    "str": str, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "isinstance": isinstance, "type": type, "repr": repr, "divmod": divmod,
    "pow": pow, "bin": bin, "hex": hex, "oct": oct, "chr": chr, "ord": ord,
    "frozenset": frozenset,
    # Math functions
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "exp": math.exp, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "pi": math.pi, "e": math.e, "ceil": math.ceil, "floor": math.floor,
    "factorial": math.factorial, "gcd": math.gcd, "lcm": math.lcm,
    "radians": math.radians, "degrees": math.degrees,
    # Statistics
    "mean": statistics.mean, "median": statistics.median,
    "mode": statistics.mode, "stdev": statistics.stdev,
    "variance": statistics.variance,
}

# Whitelisted string/list/dict methods
_SAFE_METHODS = {
    str: {
        "upper", "lower", "strip", "lstrip", "rstrip", "split", "rsplit",
        "join", "replace", "find", "rfind", "count", "startswith", "endswith",
        "format", "isdigit", "isalpha", "isalnum", "isspace", "title",
        "capitalize", "swapcase", "zfill", "center", "ljust", "rjust",
        "encode", "index", "rindex", "partition", "rpartition", "removeprefix", "removesuffix",
    },
    list: {
        "append", "extend", "insert", "remove", "pop", "clear",
        "index", "count", "sort", "reverse", "copy",
    },
    dict: {
        "get", "keys", "values", "items", "pop", "update", "setdefault",
        "clear", "copy", "popitem",
    },
    set: {
        "add", "remove", "discard", "pop", "clear", "copy",
        "union", "intersection", "difference", "symmetric_difference",
        "issubset", "issuperset", "isdisjoint",
    },
    tuple: {"count", "index"},
}

# AST node types that are allowed
_ALLOWED_NODES = (
    # Module and statements
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign,
    ast.AnnAssign,
    # Expressions
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Constant, ast.Name, ast.Load, ast.Store,
    ast.Num, ast.Str, ast.Bytes, ast.NameConstant,  # Python <3.8 compat
    # Data structures
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension,
    # Function calls
    ast.Call,
    # Subscripting
    ast.Subscript, ast.Index, ast.Slice,  # Index for Python <3.9
    # Conditionals and loops (restricted)
    ast.If, ast.For, ast.While,
    ast.Break, ast.Continue, ast.Pass,
    # Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Pow, ast.LShift, ast.RShift, ast.BitOr, ast.BitAnd, ast.Xor,
    ast.Invert, ast.USub, ast.UAdd, ast.Not,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    # f-strings (Python 3.6+)
    ast.JoinedStr, ast.FormattedValue,
    ast.Starred,  # *args unpacking
    ast.IfExp,  # ternary
    ast.Slice,
)

# Operator mapping
_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
    ast.LShift: lambda a, b: a << b,
    ast.RShift: lambda a, b: a >> b,
    ast.BitOr: lambda a, b: a | b,
    ast.BitAnd: lambda a, b: a & b,
    ast.Xor: lambda a, b: a ^ b,
}

_UNARY_OPS = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
    ast.Not: lambda a: not a,
    ast.Invert: lambda a: ~a,
}

_COMPARE_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Is: lambda a, b: a is b,
    ast.IsNot: lambda a, b: a is not b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Names that must never be accessible (even if somehow in scope)
_BLOCKED_NAMES = {
    "__builtins__", "__import__", "exec", "eval", "compile", "open",
    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr",
    "hasattr", "type",  # type() is allowed as a builtin call but not for __class__ access
    "breakpoint", "exit", "quit", "input",
    "memoryview", "property", "classmethod", "staticmethod",
}

# Dunder attributes that are never allowed in attribute access
_BLOCKED_ATTRS = {
    "__class__", "__base__", "__bases__", "__subclasses__", "__mro__",
    "__builtins__", "__globals__", "__dict__", "__code__", "__func__",
    "__module__", "__name__", "__qualname__", "__defaults__", "__closure__",
    "__wrapped__", "__self__", "__init__", "__new__", "__del__",
}


class ASTEvaluator:
    """
    Recursively evaluates an AST using only whitelisted operations.
    No exec(), no eval(), no arbitrary attribute access.
    """

    def __init__(self):
        self._locals = {}
        self._node_count = 0

    def _check_node(self, node):
        """Check that a node type is allowed and count it."""
        self._node_count += 1
        if self._node_count > MAX_EXECUTION_NODES:
            raise ValueError("Code too complex — exceeded maximum AST node count")

        # Check for blocked attribute access
        if isinstance(node, ast.Attribute):
            if node.attr in _BLOCKED_ATTRS or node.attr.startswith("__"):
                raise ValueError(f"Access to '{node.attr}' is not allowed")

        if not isinstance(node, _ALLOWED_NODES) and not isinstance(node, ast.Attribute):
            raise ValueError(f"Statement type '{type(node).__name__}' is not allowed")

    def _check_name(self, name):
        """Check that a name being accessed is safe."""
        if name in _BLOCKED_NAMES:
            raise ValueError(f"Access to '{name}' is not allowed")

    def eval_node(self, node):
        """Recursively evaluate an AST node."""
        self._check_node(node)

        # ──── Literals ────
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Num):  # Python <3.8
            return node.n
        if isinstance(node, ast.Str):  # Python <3.8
            return node.s
        if isinstance(node, ast.Bytes):
            return node.s
        if isinstance(node, ast.NameConstant):
            return node.value

        # ──── Names ────
        if isinstance(node, ast.Name):
            self._check_name(node.id)
            if node.id in _SAFE_BUILTINS:
                return _SAFE_BUILTINS[node.id]
            if node.id in self._locals:
                return self._locals[node.id]
            if node.id in ("True", "False", "None"):
                return ast.literal_eval(node.id)
            raise NameError(f"Name '{node.id}' is not defined")

        # ──── Binary ops ────
        if isinstance(node, ast.BinOp):
            left = self.eval_node(node.left)
            right = self.eval_node(node.right)
            op_func = _BIN_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"Operator {type(node.op).__name__} not allowed")
            return op_func(left, right)

        # ──── Unary ops ────
        if isinstance(node, ast.UnaryOp):
            operand = self.eval_node(node.operand)
            op_func = _UNARY_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"Unary op {type(node.op).__name__} not allowed")
            return op_func(operand)

        # ──── Boolean ops ────
        if isinstance(node, ast.BoolOp):
            values = [self.eval_node(v) for v in node.values]
            if isinstance(node.op, ast.And):
                result = True
                for v in values:
                    result = result and v
                    if not result:
                        return result
                return result
            else:  # Or
                result = False
                for v in values:
                    result = result or v
                    if result:
                        return result
                return result

        # ──── Comparisons ────
        if isinstance(node, ast.Compare):
            left = self.eval_node(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = self.eval_node(comp)
                op_func = _COMPARE_OPS.get(type(op))
                if not op_func:
                    raise ValueError(f"Comparison {type(op).__name__} not allowed")
                if not op_func(left, right):
                    return False
                left = right
            return True

        # ──── Data structures ────
        if isinstance(node, ast.List):
            return [self.eval_node(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self.eval_node(e) for e in node.elts)
        if isinstance(node, ast.Set):
            return {self.eval_node(e) for e in node.elts}
        if isinstance(node, ast.Dict):
            return {
                self.eval_node(k): self.eval_node(v)
                for k, v in zip(node.keys, node.values)
            }
        if isinstance(node, ast.Starred):
            return self.eval_node(node.value)

        # ──── f-strings ────
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    val = self.eval_node(value.value)
                    conv = value.conversion
                    if conv == 97:  # !s
                        val = str(val)
                    elif conv == 114:  # !r
                        val = repr(val)
                    elif conv == 115:  # !a
                        val = ascii(val)
                    parts.append(str(val))
                elif isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                else:
                    parts.append(str(self.eval_node(value)))
            return "".join(parts)

        # ──── Function calls ────
        if isinstance(node, ast.Call):
            func = self.eval_node(node.func)

            # Check method calls against whitelist
            if isinstance(node.func, ast.Attribute):
                obj = self.eval_node(node.func.value)
                obj_type = type(obj)
                method_name = node.func.attr

                # Find the type hierarchy for method lookup
                safe = False
                for t in type(obj).__mro__:
                    if t in _SAFE_METHODS and method_name in _SAFE_METHODS[t]:
                        safe = True
                        break

                if not safe:
                    raise ValueError(
                        f"Method '{method_name}' is not allowed on {obj_type.__name__}"
                    )

                func = getattr(obj, method_name)

            # Evaluate arguments
            args = [self.eval_node(a) for a in node.args]
            kwargs = {kw.arg: self.eval_node(kw.value) for kw in node.keywords}

            try:
                return func(*args, **kwargs)
            except TypeError as e:
                raise TypeError(f"Error calling function: {e}")

        # ──── Subscripting ────
        if isinstance(node, ast.Subscript):
            obj = self.eval_node(node.value)
            if isinstance(node.slice, ast.Slice):
                lower = self.eval_node(node.slice.lower) if node.slice.lower else None
                upper = self.eval_node(node.slice.upper) if node.slice.upper else None
                step = self.eval_node(node.slice.step) if node.slice.step else None
                return obj[lower:upper:step]
            else:
                # Python 3.9+: slice is the index directly
                # Python <3.9: slice wraps in ast.Index
                if isinstance(node.slice, ast.Index):
                    key = self.eval_node(node.slice.value)
                else:
                    key = self.eval_node(node.slice)
                return obj[key]

        # ──── Attribute access ──── (only for known-safe method calls, handled in Call above)
        if isinstance(node, ast.Attribute):
            # This is only reached if someone accesses an attribute without calling it
            # We don't allow bare attribute access — it must be a method call
            raise ValueError(
                f"Bare attribute access '.{node.attr}' is not allowed. "
                "Only method calls on safe types are supported."
            )

        # ──── If/Elif/Else ────
        if isinstance(node, ast.If):
            result_parts = []
            for stmt in node.body:
                val = self.eval_node(stmt)
                if val is not None:
                    result_parts.append(str(val))
            for stmt in node.orelse:
                val = self.eval_node(stmt)
                if val is not None:
                    result_parts.append(str(val))
            return "\n".join(result_parts) if result_parts else None

        # ──── Ternary ────
        if isinstance(node, ast.IfExp):
            if self.eval_node(node.test):
                return self.eval_node(node.body)
            return self.eval_node(node.orelse)

        # ──── For loops ────
        if isinstance(node, ast.For):
            iterable = self.eval_node(node.iter)
            result_parts = []
            for item in iterable:
                self._assign_target(node.target, item)
                for stmt in node.body:
                    val = self.eval_node(stmt)
                    if val is not None:
                        result_parts.append(str(val))
            return "\n".join(result_parts) if result_parts else None

        # ──── While loops ────
        if isinstance(node, ast.While):
            result_parts = []
            iterations = 0
            MAX_LOOP = 100000
            while self.eval_node(node.test):
                iterations += 1
                if iterations > MAX_LOOP:
                    raise ValueError("Loop exceeded maximum iterations (100000)")
                for stmt in node.body:
                    val = self.eval_node(stmt)
                    if val is not None:
                        result_parts.append(str(val))
            return "\n".join(result_parts) if result_parts else None

        # ──── Assignments ────
        if isinstance(node, ast.Assign):
            val = self.eval_node(node.value)
            for target in node.targets:
                self._assign_target(target, val)
            return None

        # ──── Augmented assignments (+=, -=, etc.) ────
        if isinstance(node, ast.AugAssign):
            current = self.eval_node(node.target)
            val = self.eval_node(node.value)
            op_func = _BIN_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"Augmented op {type(node.op).__name__} not allowed")
            new_val = op_func(current, val)
            self._assign_target(node.target, new_val)
            return None

        # ──── Comprehensions ────
        if isinstance(node, ast.ListComp):
            return self._eval_comprehension(node, "list")

        if isinstance(node, ast.SetComp):
            return self._eval_comprehension(node, "set")

        if isinstance(node, ast.GeneratorExp):
            return self._eval_comprehension(node, "gen")

        if isinstance(node, ast.DictComp):
            return self._eval_comprehension(node, "dict")

        # ──── Expression statement ────
        if isinstance(node, ast.Expr):
            return self.eval_node(node.value)

        # ──── Pass / Break / Continue ────
        if isinstance(node, ast.Pass):
            return None
        if isinstance(node, ast.Break):
            raise StopIteration
        if isinstance(node, ast.Continue):
            return None

        # ──── Module (top level) ────
        if isinstance(node, ast.Module):
            result_parts = []
            for stmt in node.body:
                val = self.eval_node(stmt)
                if val is not None:
                    result_parts.append(str(val))
            return "\n".join(result_parts) if result_parts else "Code executed successfully (no output)."

        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def _assign_target(self, target, value):
        """Assign a value to a target (Name or Subscript)."""
        if isinstance(target, ast.Name):
            self._check_name(target.id)
            self._locals[target.id] = value
        elif isinstance(target, ast.Subscript):
            obj = self.eval_node(target.value)
            if isinstance(target.slice, ast.Index):
                key = self.eval_node(target.slice.value)
            else:
                key = self.eval_node(target.slice)
            obj[key] = value
        elif isinstance(target, ast.Tuple) or isinstance(target, ast.List):
            # Unpacking assignment
            if not hasattr(value, "__iter__"):
                raise TypeError("Cannot unpack non-iterable")
            for t, v in zip(target.elts, value):
                self._assign_target(t, v)
        else:
            raise ValueError(f"Cannot assign to {type(target).__name__}")

    def _eval_comprehension(self, node, comp_type):
        """Evaluate a comprehension (ListComp, SetComp, DictComp, GeneratorExp)."""
        def _recurse(gen_idx, env_snapshot):
            if gen_idx >= len(node.generators):
                if comp_type == "list":
                    return [self.eval_node(node.elt)]
                elif comp_type == "set":
                    return {self.eval_node(node.elt)}
                elif comp_type == "gen":
                    return [self.eval_node(node.elt)]
                elif comp_type == "dict":
                    return [(self.eval_node(node.key), self.eval_node(node.value))]

            gen = node.generators[gen_idx]
            iterable = self.eval_node(gen.iter)
            results = []

            for item in iterable:
                self._assign_target(gen.target, item)
                skip = False
                for cond in gen.ifs:
                    if not self.eval_node(cond):
                        skip = True
                        break
                if skip:
                    continue

                if gen_idx == len(node.generators) - 1:
                    if comp_type == "list" or comp_type == "gen":
                        results.append(self.eval_node(node.elt))
                    elif comp_type == "set":
                        results.append(self.eval_node(node.elt))
                    elif comp_type == "dict":
                        results.append((self.eval_node(node.key), self.eval_node(node.value)))
                else:
                    results.extend(_recurse(gen_idx + 1, dict(self._locals)))

            return results

        results = _recurse(0, dict(self._locals))

        if comp_type == "list" or comp_type == "gen":
            return results
        elif comp_type == "set":
            return set(results)
        elif comp_type == "dict":
            return dict(results)

        return results


def run(code: str) -> str:
    """
    Evaluate Python code safely using AST whitelisting.
    This is NOT exec() — it's a restricted AST evaluator that only allows
    math, data manipulation, and safe builtins.
    """
    if len(code) > MAX_CODE_LENGTH:
        return f"Error: Code too long (max {MAX_CODE_LENGTH} characters)."

    code = code.strip()
    if not code:
        return "Error: Empty code."

    # Step 1: Parse into AST
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax Error: {e.msg} (line {e.lineno})"
    except Exception as e:
        return f"Parse Error: {str(e)[:200]}"

    # Step 2: Pre-validate AST for blocked nodes
    for node in ast.walk(tree):
        # Block import statements
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "Error: Imports are not allowed. Math and data functions are available as builtins."
        # Block lambda
        if isinstance(node, ast.Lambda):
            return "Error: Lambda functions are not allowed."
        # Block global/nonlocal
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return "Error: Global/nonlocal statements are not allowed."
        # Block class definitions
        if isinstance(node, (ast.ClassDef,)):
            return "Error: Class definitions are not allowed."
        # Block function definitions (we only allow expressions, not def)
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            return "Error: Function definitions are not allowed. Use built-in functions."
        # Block delete
        if isinstance(node, ast.Delete):
            return "Error: Delete statements are not allowed."
        # Block with/try
        if isinstance(node, (ast.With, ast.AsyncWith, ast.Try, ast.TryStar)):
            return "Error: With/Try statements are not allowed."
        # Block walrus operator (can be used to assign to complex expressions)
        if isinstance(node, ast.NamedExpr):
            return "Error: Walrus operator ':=' is not allowed."
        # Check for blocked attribute access
        if isinstance(node, ast.Attribute):
            if node.attr in _BLOCKED_ATTRS or node.attr.startswith("__"):
                return f"Error: Access to '{node.attr}' is not allowed."

    # Step 3: Evaluate with the safe AST evaluator
    try:
        evaluator = ASTEvaluator()
        result = evaluator.eval_node(tree)

        if result is None:
            return "Code executed successfully (no output)."

        result_str = str(result)
        if len(result_str) > MAX_OUTPUT:
            result_str = result_str[:MAX_OUTPUT] + "\n... (output truncated)"

        return result_str

    except StopIteration:
        return "Error: 'break' used outside of a loop."
    except ValueError as e:
        return f"Error: {str(e)[:300]}"
    except (TypeError, NameError, ZeroDivisionError, KeyError, IndexError,
            OverflowError, AttributeError, ArithmeticError) as e:
        return f"Error: {type(e).__name__}: {str(e)[:300]}"
    except RecursionError:
        return "Error: Maximum recursion depth exceeded."
    except Exception as e:
        logger.error(f"Code runner unexpected error: {e}", exc_info=True)
        return f"Error: {type(e).__name__}: {str(e)[:200]}"
