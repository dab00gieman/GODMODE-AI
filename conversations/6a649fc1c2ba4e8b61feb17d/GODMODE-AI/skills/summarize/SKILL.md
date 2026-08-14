---
name: summarize
description: Summarize long text into key points using extractive summarization
version: 1.0.0
triggers:
  - summarize
  - tldr
  - key points
  - shorten this
  - brief summary
arguments:
  - name: text
    type: string
    required: true
    description: The text to summarize
  - name: max_sentences
    type: int
    required: false
    default: "3"
    description: Number of key sentences to extract
---

# Summarizer

Extractive text summarization using word frequency scoring.
Identifies the most important sentences based on keyword density and position.
No API key needed — all computed locally.
