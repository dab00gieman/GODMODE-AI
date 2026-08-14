"""
Google Gemini Image Generation — uses Gemini's native image generation capability.

Uses the Generative Language API with the gemini-2.0-flash-exp model which supports
image generation via responseModalities: ["IMAGE", "TEXT"].
"""

import os
import base64
import requests
import logging
from typing import Tuple, Optional, Dict

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def is_available() -> bool:
    """Check if Google image generation is available (API key configured)."""
    return bool(GOOGLE_API_KEY)


def generate_image(prompt: str) -> Tuple[str, Optional[Dict]]:
    """
    Generate an image using Google Gemini.
    Returns (image_url_or_message, metadata).
    
    Note: Gemini returns base64 image data, not a URL.
    We return a data URI that can be sent via Telegram.
    """
    if not GOOGLE_API_KEY:
        return "Google API key not configured.", None
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"Generate an image: {prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "temperature": 0.9,
        }
    }
    
    url = f"{GEMINI_URL}?key={GOOGLE_API_KEY}"
    
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        
        # Extract image from response
        candidates = data.get("candidates", [])
        if not candidates:
            return "No response from Gemini.", None
        
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            # Check for inline image data
            if "inlineData" in part:
                image_b64 = part["inlineData"].get("data", "")
                mime_type = part["inlineData"].get("mimeType", "image/png")
                
                # Convert to a data URI
                data_uri = f"data:{mime_type};base64,{image_b64}"
                
                # Also try to upload to a hosting service for a real URL
                # For now, return the base64 data — Telegram bot API can handle this
                # by saving to a temp file and sending as a photo
                
                meta = {
                    "model_used": GEMINI_MODEL,
                    "type": "image",
                    "prompt": prompt,
                    "mime_type": mime_type,
                    "image_data": image_b64,  # raw base64 for Telegram
                }
                return data_uri, meta
            
            # Check for text response (sometimes model returns text instead)
            if "text" in part:
                text = part["text"]
                if "sorry" in text.lower() or "can't" in text.lower():
                    return f"Gemini declined: {text[:200]}", None
        
        return "Gemini returned no image in response.", None
    
    except requests.exceptions.Timeout:
        return "Image generation timed out (Gemini).", None
    except requests.exceptions.RequestException as e:
        err_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err_data = e.response.json()
                err_msg = err_data.get("error", {}).get("message", err_msg)
            except Exception:
                err_msg = f"HTTP {e.response.status_code}"
        logger.error(f"Google image generation error: {err_msg}")
        return f"Google image error: {err_msg}", None


def generate_image_with_openrouter_fallback(prompt: str, model: str = "") -> Tuple[str, Optional[Dict]]:
    """
    Try Google Gemini first, fall back to OpenRouter if Google fails.
    """
    if is_available():
        result, meta = generate_image(prompt)
        if result.startswith("data:") or result.startswith("http"):
            return result, meta
        logger.warning(f"Google image gen failed, falling back to OpenRouter: {result}")
    
    # Fallback to OpenRouter
    from utils.openrouter import generate_image as or_generate
    return or_generate(model or "google/imagen-3", prompt)
