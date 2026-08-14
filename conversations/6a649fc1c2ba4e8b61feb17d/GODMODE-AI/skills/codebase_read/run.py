"""Codebase Read Skill — read files from Lisa's own GitHub repo."""

import os
import requests
import base64
import logging

logger = logging.getLogger(__name__)


def run(filepath: str) -> str:
    """Read a file from the GitHub repo via the GitHub API."""
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPO", "dab00gieman/Lisa")
    
    if not token:
        return "Error: GITHUB_TOKEN not configured."
    
    url = f"https://api.github.com/repos/{repo}/contents/{filepath}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            return f"File not found: {filepath}"
        resp.raise_for_status()
        data = resp.json()
        
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding == "base64":
            content = base64.b64decode(content).decode("utf-8", errors="replace")
        
        # Truncate if too large
        if len(content) > 8000:
            content = content[:8000] + "\n\n... [truncated, file is longer]"
        
        return f"📄 {filepath} ({data.get('size', '?')} bytes)\n\n{content}"
    except requests.exceptions.RequestException as e:
        return f"Error reading {filepath}: {e}"
