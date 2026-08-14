"""Codebase List Skill — list files in Lisa's GitHub repo."""

import os
import requests
import logging

logger = logging.getLogger(__name__)


def run(path: str = "") -> str:
    """List files in a directory of the GitHub repo."""
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPO", "dab00gieman/Lisa")
    
    if not token:
        return "Error: GITHUB_TOKEN not configured."
    
    url = f"https://api.github.com/repos/{repo}/contents/{path}" if path else f"https://api.github.com/repos/{repo}/contents/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        items = resp.json()
        
        if not isinstance(items, list):
            return f"Not a directory: {path}"
        
        result = []
        for item in items:
            icon = "📁" if item["type"] == "dir" else "📄"
            result.append(f"{icon} {item['name']}")
        
        return f"📂 {path or '/'}\n\n" + "\n".join(result)
    except requests.exceptions.RequestException as e:
        return f"Error listing {path}: {e}"
