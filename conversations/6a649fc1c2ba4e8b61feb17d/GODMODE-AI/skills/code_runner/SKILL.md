---
name: code_runner
description: Execute Python code in a restricted sandbox. No file or network access. Max 5000 chars.
version: 1.0.0
triggers:
  - run code
  - execute code
  - python
  - code:
  - run this
  - print(
arguments:
  - name: code
    type: string
    required: true
    description: Python code to execute
---

# Code Runner

Executes Python code in a sandboxed environment with restricted builtins.
No file access, no network access, no subprocess calls.
Output is captured from print statements and returned as text.
Maximum 5000 characters of code.
