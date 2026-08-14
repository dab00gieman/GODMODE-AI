---
name: translate
description: Translate text between languages. Auto-detects source language.
version: 1.0.0
triggers:
  - translate
  - in french
  - in spanish
  - in yoruba
  - in hausa
  - in igbo
  - in german
  - in chinese
  - in arabic
  - in portuguese
arguments:
  - name: text
    type: string
    required: true
    description: Text to translate
  - name: target_lang
    type: string
    required: true
    description: Target language code (en, fr, es, yo, ha, ig, de, zh, ar, pt)
  - name: source_lang
    type: string
    required: false
    default: "auto"
    description: Source language code, or auto for auto-detect
---

# Translator

Translates text using Google Translate's free unofficial API.
Supports 100+ languages including Nigerian languages (Yoruba, Hausa, Igbo).
Auto-detects the source language by default.
