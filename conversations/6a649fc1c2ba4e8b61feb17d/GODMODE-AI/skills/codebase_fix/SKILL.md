---
name: codebase_fix
description: Write or update a source file in Lisa's own codebase on GitHub. Use this to fix bugs, update code, and apply patches to her own source files.
version: 1.0.0
author: Lisa
triggers:
  - fix the code
  - update the code
  - patch the file
  - write to the file
  - fix the bug
  - apply the fix
arguments:
  - name: filepath
    type: string
    required: true
    description: The file path to update (e.g. api/webhook.py)
  - name: content
    type: string
    required: true
    description: The new full content of the file
  - name: message
    type: string
    required: false
    description: Commit message for the fix
---

# Codebase Fix

Writes updated content to a file in Lisa's own GitHub repository (dab00gieman/Lisa).
This lets Lisa fix her own bugs by committing code changes directly to her repo,
which triggers a Vercel redeployment automatically.

Use this when:
- You've diagnosed an error and know the fix
- You need to update a configuration
- You're applying a patch to your own code

The content parameter should be the COMPLETE new file content (not a diff).
