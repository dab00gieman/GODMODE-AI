---
name: memory_search
description: Search long-term MEMORY.md and past interactions for relevant context
version: 1.0.0
triggers:
  - remember
  - last time
  - previously
  - do you remember
  - what did we
  - my history
arguments:
  - name: query
    type: string
    required: true
    description: What to search for in memory
---

# Memory Search

Searches GODMODE's long-term memory (MEMORY.md stored in Redis) and
episodic memory (past interaction summaries) for context relevant to the query.
This is the retrieval mechanism that makes the agent feel like it remembers you.
