"""Translator Skill — Google Translate free API."""

import requests
import logging

logger = logging.getLogger(__name__)


def run(text: str, target_lang: str = "en", source_lang: str = "auto") -> str:
    """Translate text using Google Translate's free endpoint."""
    try:
        if not text:
            return "Error: No text provided."

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

        translated_parts = []
        detected_lang = source_lang

        if data and len(data) > 0:
            for part in data[0]:
                if part and len(part) > 0:
                    translated_parts.append(part[0])

        if len(data) > 2 and data[2]:
            detected_lang = data[2]

        translated = "".join(translated_parts)

        if not translated:
            return "Translation failed: no output received."

        return f"Translated ({detected_lang} -> {target_lang}):\n\n{translated}"

    except requests.exceptions.Timeout:
        return "Translation timed out. Try shorter text."
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return f"Translation failed: {str(e)}"
