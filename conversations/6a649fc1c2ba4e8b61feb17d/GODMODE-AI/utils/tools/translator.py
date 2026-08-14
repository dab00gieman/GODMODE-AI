"""
Tool: Translator
Translates text using the free Google Translate unofficial API.
"""

import requests
import logging
import re
from utils.tools import register_tool

logger = logging.getLogger(__name__)

def _translate(text: str, target_lang: str = "en", source_lang: str = "auto") -> str:
    """Translate text using Google Translate's free endpoint."""
    try:
        if not text:
            return "Error: No text provided."

        # Use the free unofficial Google Translate API
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": source_lang,
            "tl": target_lang,
            "dt": "t",
            "q": text,
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Parse response — it's a nested list
        translated_parts = []
        detected_lang = source_lang

        if data and len(data) > 0:
            for part in data[0]:
                if part and len(part) > 0:
                    translated_parts.append(part[0])

        # Detect language from response
        if len(data) > 2 and data[2]:
            detected_lang = data[2]

        translated = "".join(translated_parts)

        if not translated:
            return "Translation failed: no output received."

        result = f"🌐 Translated ({detected_lang} → {target_lang}):\n\n{translated}"
        return result

    except requests.exceptions.Timeout:
        return "Translation timed out. Try shorter text."
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return f"Translation failed: {str(e)}"

register_tool(
    name="translate",
    description="Translate text between languages. Uses Google Translate (free). Supports auto-detect source language.",
    args_schema={
        "text": "string (text to translate)",
        "target_lang": "string (target language code, e.g. 'en', 'fr', 'es', 'yo', 'ha', 'ig')",
        "source_lang": "string (optional, source language code, default 'auto' for auto-detect)",
    },
    func=_translate,
)
