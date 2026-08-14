---
name: episodic_recall
description: Recall detailed past interactions and what tools were used
version: 1.0.0
triggers:
  - what did we talk about
  - recall
  - our last conversation
  - show me history
  - past interactions
arguments:
  - name: query
    type: string
    required: false
    description: Optional filter for what to recall
  - name: max_results
    type: int
    required: false
    default: "5"
    description: Maximum number of past interactions to return
---

# Episodic Recall

Deep search of episodic memory. Returns detailed records of past interactions
including the original query, the summary of what happened, and which tools were used.
This is the "I remember when we..." capability.
