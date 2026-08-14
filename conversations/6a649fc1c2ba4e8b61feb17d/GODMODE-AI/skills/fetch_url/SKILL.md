---
name: fetch_url
description: Fetch content from a web URL and extract the text
version: 1.0.0
triggers:
  - fetch
  - read url
  - read this page
  - read this article
  - get this page
  - open this link
arguments:
  - name: url
    type: string
    required: true
    description: URL to fetch
  - name: extract_text
    type: bool
    required: false
    default: "true"
    description: If true, extracts plain text from HTML
---

# URL Fetcher

Fetches a web page and extracts clean text content.
Strips HTML tags, scripts, and styles. Returns the page title and body text.
Maximum 5000 characters of content returned.
