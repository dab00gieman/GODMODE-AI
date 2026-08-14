"""Codebase Fix Skill — write files to Lisa's own GitHub repo."""

import os
import requests
import base64
import json
import logging

logger = logging.getLogger(__name__)


def run(filepath: str, content: str, message: str = "fix: self-healing patch") -> str:
    """Write/update a file in the GitHub repo via the GitHub API."""
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
        # Get current file SHA (needed for update)
        resp = requests.get(url, headers=headers, timeout=15)
        sha = None
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        
        # Encode content
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        
        # Create/update file
        payload = {
            "message": message,
            "content": encoded,
        }
        if sha:
            payload["sha"] = sha
        
        resp = requests.put(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        commit_sha = data.get("commit", {}).get("sha", "?")[:12]
        
        return f"✅ Updated {filepath} (commit {commit_sha}). Vercel will redeploy automatically."
    except requests.exceptions.RequestException as e:
        err_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err_data = e.response.json()
                err_msg = err_data.get("message", err_msg)
            except Exception:
                pass
        return f"Error updating {filepath}: {err_msg}"
