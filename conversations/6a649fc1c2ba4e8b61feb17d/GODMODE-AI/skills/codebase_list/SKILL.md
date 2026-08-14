---
name: codebase_list
description: List files and directories in Lisa's own codebase on GitHub. Use this to explore the project structure.
version: 1.0.0
author: Lisa
triggers:
  - list files
  - show project structure
  - what files are there
  - list directory
  - show me the codebase
arguments:
  - name: path
    type: string
    required: false
    description: Directory path to list (default: root)
---

# Codebase List

Lists files and directories in Lisa's GitHub repository.
Useful for exploring the project structure and finding relevant files.
