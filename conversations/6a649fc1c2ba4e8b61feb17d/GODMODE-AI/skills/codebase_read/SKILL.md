---
name: codebase_read
description: Read source files from Lisa's own codebase on GitHub. Use this to inspect code, understand errors, and diagnose bugs.
version: 1.0.0
author: Lisa
triggers:
  - read code
  - show me the code
  - what does the code look like
  - inspect file
  - read file
  - look at the source
  - check the code
arguments:
  - name: filepath
    type: string
    required: true
    description: The file path to read (e.g. api/webhook.py, utils/config.py)
---

# Codebase Read

Reads a file from Lisa's own GitHub repository (dab00gieman/Lisa) using the GitHub API.
This gives Lisa self-awareness of her own codebase — she can inspect her source files
to understand how she works, diagnose errors, and plan fixes.

Returns the raw file content. Use this when:
- An error occurs and you need to see the relevant code
- You want to understand how a feature works
- You're planning a fix and need to see the current implementation
