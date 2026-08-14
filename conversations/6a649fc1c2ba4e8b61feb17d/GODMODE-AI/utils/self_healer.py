"""
Lisa Self-Healer — automatic error diagnosis and codebase repair.

When an error occurs, Lisa:
1. Reads the relevant source file from her GitHub repo
2. Sends the error + code to the LLM for diagnosis
3. Gets a suggested fix
4. Commits the fix to GitHub (triggers Vercel redeploy)
5. Reports what she found and fixed
"""

import os
import re
import json
import logging
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "dab00gieman/Lisa")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DIAGNOSIS_MODEL = "google/gemini-2.5-flash"

# Track recent fixes to avoid infinite loops
_recent_fixes: list = []
MAX_FIXES_PER_HOUR = 3


def _can_fix() -> bool:
    """Check if self-healing is available and not rate-limited."""
    if not GITHUB_TOKEN or not OPENROUTER_API_KEY:
        return False
    # Rate limit: max 3 fixes per hour
    import time
    now = time.time()
    global _recent_fixes
    _recent_fixes = [t for t in _recent_fixes if now - t < 3600]
    return len(_recent_fixes) < MAX_FIXES_PER_HOUR


def _extract_filepath_from_error(error_text: str, traceback_text: str = "") -> Optional[str]:
    """Try to extract the relevant file path from an error message or traceback."""
    # Look for file paths in traceback
    patterns = [
        r'File "([^"]+\.py)"',
        r'File "([^"]+)"',
        r'(\w+/\w+\.py)',
        r'(utils/\w+\.py)',
        r'(api/\w+\.py)',
        r'(skills/\w+/run\.py)',
    ]
    combined = f"{error_text}\n{traceback_text}"
    for pattern in patterns:
        matches = re.findall(pattern, combined)
        if matches:
            # Return the last match (closest to the actual error)
            path = matches[-1]
            # Strip absolute path prefixes
            if "/" in path:
                # Get the relative path (after common prefixes)
                for prefix in ["api/", "utils/", "skills/", "soul/"]:
                    if prefix in path:
                        idx = path.index(prefix)
                        return path[idx:]
            return path
    return None


def _read_github_file(filepath: str) -> Optional[str]:
    """Read a file from the GitHub repo."""
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        content = data.get("content", "")
        if data.get("encoding") == "base64":
            content = base64.b64decode(content).decode("utf-8", errors="replace")
        return content
    except Exception as e:
        logger.error(f"Self-healer: failed to read {filepath}: {e}")
        return None


def _write_github_file(filepath: str, content: str, message: str) -> Tuple[bool, str]:
    """Write a file to the GitHub repo."""
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        # Get current SHA
        resp = requests.get(url, headers=headers, timeout=15)
        sha = None
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload = {"message": message, "content": encoded}
        if sha:
            payload["sha"] = sha
        
        resp = requests.put(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        commit_sha = resp.json().get("commit", {}).get("sha", "?")[:12]
        return True, commit_sha
    except Exception as e:
        return False, str(e)


def _diagnose_and_fix(error_text: str, filepath: str, code_content: str) -> Tuple[Optional[str], str]:
    """
    Send the error + code to the LLM and get a fix.
    Returns (fixed_code, diagnosis_message).
    """
    system_prompt = (
        "You are Lisa, a self-healing AI agent. You've encountered an error in your own code.\n"
        "Analyze the error, identify the root cause, and provide the COMPLETE FIXED file content.\n\n"
        "Rules:\n"
        "1. Return ONLY the fixed Python code, no explanations before or after\n"
        "2. Keep ALL existing functionality intact — only fix the error\n"
        "3. Do NOT remove imports, functions, or features\n"
        "4. If the fix requires a new import, add it\n"
        "5. Make the minimal change needed to fix the error\n"
    )
    
    user_msg = (
        f"Error:\n{error_text}\n\n"
        f"File: {filepath}\n\n"
        f"Current code:\n```\n{code_content}\n```\n\n"
        f"Provide the complete fixed file content. Return ONLY the Python code, no markdown fences, no explanation."
    )
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DIAGNOSIS_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 8000,
    }
    
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        fixed_code = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Strip markdown code fences if present
        fixed_code = re.sub(r'^```python\s*\n', '', fixed_code)
        fixed_code = re.sub(r'^```\s*\n', '', fixed_code)
        fixed_code = re.sub(r'\n```\s*$', '', fixed_code)
        fixed_code = fixed_code.strip()
        
        if not fixed_code or len(fixed_code) < 10:
            return None, "LLM returned empty fix."
        
        if fixed_code == code_content:
            return None, "LLM returned identical code — no fix needed."
        
        return fixed_code, "Fix generated successfully."
    except Exception as e:
        return None, f"Diagnosis failed: {e}"


def attempt_heal(error_text: str, traceback_text: str = "") -> dict:
    """
    Main entry point: attempt to automatically fix an error.
    Returns a dict with results.
    """
    result = {
        "healed": False,
        "filepath": None,
        "commit_sha": None,
        "message": "",
        "diagnosis": "",
    }
    
    if not _can_fix():
        result["message"] = "Self-healing unavailable (no tokens or rate-limited)."
        return result
    
    # Step 1: Find the relevant file
    filepath = _extract_filepath_from_error(error_text, traceback_text)
    if not filepath:
        result["message"] = "Could not identify which file caused the error."
        return result
    
    result["filepath"] = filepath
    
    # Step 2: Read the file from GitHub
    code_content = _read_github_file(filepath)
    if not code_content:
        result["message"] = f"Could not read {filepath} from GitHub."
        return result
    
    # Step 3: Diagnose and generate fix
    fixed_code, diagnosis = _diagnose_and_fix(error_text, filepath, code_content)
    result["diagnosis"] = diagnosis
    if not fixed_code:
        result["message"] = f"Could not generate fix: {diagnosis}"
        return result
    
    # Step 4: Apply the fix
    commit_msg = f"self-heal: fix error in {filepath}\n\nError: {error_text[:200]}"
    success, commit_info = _write_github_file(filepath, fixed_code, commit_msg)
    
    if success:
        import time
        _recent_fixes.append(time.time())
        result["healed"] = True
        result["commit_sha"] = commit_info
        result["message"] = f"Fixed {filepath} (commit {commit_info}). Vercel will redeploy."
        logger.info(f"Self-healer: fixed {filepath} (commit {commit_info})")
    else:
        result["message"] = f"Failed to commit fix: {commit_info}"
    
    return result
