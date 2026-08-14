---
name: calculator
description: Evaluate a mathematical expression. Supports +, -, *, /, sqrt, sin, cos, log, pi, e, etc.
version: 1.0.0
triggers:
  - calculate
  - compute
  - math
  - solve
  - what is 2 plus
  - square root of
arguments:
  - name: expression
    type: string
    required: true
    description: Math expression, e.g. "2 + 2 * 3", "sqrt(144)", "sin(pi/2)"
---

# Calculator

Safe math expression evaluator. Supports basic arithmetic, trigonometry, logarithms, and constants (pi, e).
Does not support variable assignment or non-math operations.
