---
name: web_search
description: Search the web for information using DuckDuckGo instant answers
version: 1.0.0
author: GODMODE
triggers:
  - search for
  - find information
  - look up
  - what is
  - who is
  - tell me about
  - research
arguments:
  - name: query
    type: string
    required: true
    description: The search query
  - name: max_results
    type: int
    required: false
    default: "5"
    description: Maximum number of results to return
---

# Web Search

This skill searches the web using DuckDuckGo's free instant answer API.
It returns abstract text, related topics, definitions, and direct answers.
No API key is required.

Use this when the user asks about a topic, person, place, concept, or any factual question you don't already know the answer to.
